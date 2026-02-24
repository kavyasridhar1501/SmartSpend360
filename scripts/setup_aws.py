#!/usr/bin/env python3
"""
SmartSpend360 — AWS Infrastructure Setup Script
Provisions all required AWS resources using boto3.
All resources stay within AWS Free Tier limits.

Usage:
    python scripts/setup_aws.py
    python scripts/setup_aws.py --dry-run
"""

import json
import sys
import time
import argparse
import logging
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BUCKET_NAME = "smartspend360-datalake"
RESULTS_BUCKET = "smartspend360-athena-results"
ATHENA_WORKGROUP = "smartspend360"
ATHENA_DATABASE = "smartspend360_db"
IAM_ROLE_NAME = "SmartSpend360LambdaRole"
IAM_POLICY_NAME = "SmartSpend360Policy"

S3_FOLDERS = [
    "bronze/transactions/",
    "bronze/market/",
    "bronze/fx/",
    "bronze/quarantine/",
    "silver/transactions/",
    "silver/enriched/",
    "gold/metrics/",
    "gold/forecasts/",
    "gold/anomalies/",
    "gold/features/",
    "gold/athena_views/",
    "models/",
    "athena-results/",
]

DYNAMODB_TABLES = [
    {
        "TableName": "ss360-alerts",
        "KeySchema": [
            {"AttributeName": "userId", "KeyType": "HASH"},
            {"AttributeName": "alertId", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "userId", "AttributeType": "S"},
            {"AttributeName": "alertId", "AttributeType": "S"},
        ],
        "TTLAttribute": "ttl",  # Items expire when writers set a unix-epoch ttl
    },
    {
        "TableName": "ss360-metrics",
        "KeySchema": [
            {"AttributeName": "userId", "KeyType": "HASH"},
            {"AttributeName": "date", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "userId", "AttributeType": "S"},
            {"AttributeName": "date", "AttributeType": "S"},
        ],
        "TTLAttribute": "ttl",
    },
    {
        "TableName": "ss360-forecasts",
        "KeySchema": [
            {"AttributeName": "userId", "KeyType": "HASH"},
            {"AttributeName": "forecastDate", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "userId", "AttributeType": "S"},
            {"AttributeName": "forecastDate", "AttributeType": "S"},
        ],
        "TTLAttribute": "ttl",
    },
    {
        "TableName": "ss360-pipeline-runs",
        "KeySchema": [
            {"AttributeName": "stage", "KeyType": "HASH"},
            {"AttributeName": "runId", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "stage", "AttributeType": "S"},
            {"AttributeName": "runId", "AttributeType": "S"},
        ],
        "TTLAttribute": "ttl",
    },
]

IAM_POLICY_DOCUMENT = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "S3LakehouseAccess",
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:PutObject",
                "s3:DeleteObject",
                "s3:ListBucket",
                "s3:GetBucketLocation",
            ],
            "Resource": [
                f"arn:aws:s3:::{BUCKET_NAME}",
                f"arn:aws:s3:::{BUCKET_NAME}/*",
                f"arn:aws:s3:::{RESULTS_BUCKET}",
                f"arn:aws:s3:::{RESULTS_BUCKET}/*",
            ],
        },
        {
            "Sid": "DynamoDBAccess",
            "Effect": "Allow",
            "Action": [
                "dynamodb:GetItem",
                "dynamodb:PutItem",
                "dynamodb:UpdateItem",
                "dynamodb:DeleteItem",
                "dynamodb:Query",
                "dynamodb:Scan",
                "dynamodb:BatchWriteItem",
                "dynamodb:BatchGetItem",
            ],
            "Resource": [
                "arn:aws:dynamodb:*:*:table/ss360-*",
            ],
        },
        {
            "Sid": "AthenaAccess",
            "Effect": "Allow",
            "Action": [
                "athena:StartQueryExecution",
                "athena:GetQueryExecution",
                "athena:GetQueryResults",
                "athena:StopQueryExecution",
                "athena:ListWorkGroups",
                "athena:GetWorkGroup",
            ],
            "Resource": "*",
        },
        {
            "Sid": "GlueForAthena",
            "Effect": "Allow",
            "Action": [
                "glue:GetDatabase",
                "glue:GetTable",
                "glue:GetTables",
                "glue:GetPartitions",
                "glue:CreateTable",
                "glue:CreateDatabase",
                "glue:UpdateTable",
            ],
            "Resource": "*",
        },
    ],
}

IAM_TRUST_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"Service": ["ec2.amazonaws.com", "lambda.amazonaws.com"]},
            "Action": "sts:AssumeRole",
        }
    ],
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def get_account_id(sts_client) -> str:
    return sts_client.get_caller_identity()["Account"]


def bucket_exists(s3_client, bucket_name: str) -> bool:
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        return True
    except ClientError:
        return False


def table_exists(ddb_client, table_name: str) -> bool:
    try:
        ddb_client.describe_table(TableName=table_name)
        return True
    except ClientError:
        return False


# ---------------------------------------------------------------------------
# Resource creators
# ---------------------------------------------------------------------------

def create_s3_bucket(s3_client, bucket_name: str, region: str, dry_run: bool) -> bool:
    if bucket_exists(s3_client, bucket_name):
        log.info("S3 bucket already exists: %s", bucket_name)
        return True

    log.info("Creating S3 bucket: %s (region=%s)", bucket_name, region)
    if dry_run:
        return True

    try:
        kwargs = {"Bucket": bucket_name}
        if region != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
        s3_client.create_bucket(**kwargs)

        # Block all public access
        s3_client.put_public_access_block(
            Bucket=bucket_name,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )

        # Enable versioning
        s3_client.put_bucket_versioning(
            Bucket=bucket_name,
            VersioningConfiguration={"Status": "Enabled"},
        )

        # Enable server-side encryption
        s3_client.put_bucket_encryption(
            Bucket=bucket_name,
            ServerSideEncryptionConfiguration={
                "Rules": [
                    {
                        "ApplyServerSideEncryptionByDefault": {
                            "SSEAlgorithm": "AES256"
                        }
                    }
                ]
            },
        )

        log.info("S3 bucket created: %s", bucket_name)
        return True
    except ClientError as e:
        log.error("Failed to create S3 bucket: %s", e)
        return False


def apply_s3_lifecycle(s3_client, bucket_name: str, dry_run: bool) -> bool:
    """Apply lifecycle rules to control S3 storage costs.

    - Datalake bucket: expire noncurrent (old) versions after 30 days and
      abort stale multipart uploads after 7 days.
    - Athena results bucket: expire query-result objects after 7 days so they
      don't accumulate indefinitely.
    """
    log.info("Applying S3 lifecycle policy: %s", bucket_name)
    if dry_run:
        return True

    if bucket_name == RESULTS_BUCKET:
        # Athena result files are transient — wipe them after 7 days
        rules = [
            {
                "ID": "expire-query-results",
                "Status": "Enabled",
                "Filter": {"Prefix": ""},
                "Expiration": {"Days": 7},
                "NoncurrentVersionExpiration": {"NoncurrentDays": 7},
                "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1},
            }
        ]
    else:
        # Datalake: keep current objects indefinitely, but clean up old
        # versions (created by overwrites) after 30 days
        rules = [
            {
                "ID": "expire-noncurrent-versions",
                "Status": "Enabled",
                "Filter": {"Prefix": ""},
                "NoncurrentVersionExpiration": {"NoncurrentDays": 30},
                "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7},
            }
        ]

    try:
        s3_client.put_bucket_lifecycle_configuration(
            Bucket=bucket_name,
            LifecycleConfiguration={"Rules": rules},
        )
        log.info("S3 lifecycle policy applied: %s", bucket_name)
        return True
    except ClientError as e:
        log.error("Failed to apply S3 lifecycle policy for %s: %s", bucket_name, e)
        return False


def create_s3_folders(s3_client, bucket_name: str, dry_run: bool):
    log.info("Creating S3 folder structure...")
    for folder in S3_FOLDERS:
        log.info("  Creating folder: %s", folder)
        if not dry_run:
            s3_client.put_object(Bucket=bucket_name, Key=folder, Body=b"")
    log.info("S3 folders created: %d", len(S3_FOLDERS))


def create_dynamodb_table(ddb_client, table_config: dict, dry_run: bool) -> bool:
    table_name = table_config["TableName"]
    if table_exists(ddb_client, table_name):
        log.info("DynamoDB table already exists: %s", table_name)
        return True

    log.info("Creating DynamoDB table: %s", table_name)
    if dry_run:
        return True

    try:
        ddb_client.create_table(
            TableName=table_name,
            KeySchema=table_config["KeySchema"],
            AttributeDefinitions=table_config["AttributeDefinitions"],
            BillingMode="PAY_PER_REQUEST",  # On-demand — no cost if unused
            Tags=[
                {"Key": "Project", "Value": "SmartSpend360"},
                {"Key": "Environment", "Value": "production"},
            ],
        )

        # Wait for table to be active
        waiter = ddb_client.get_waiter("table_exists")
        waiter.wait(TableName=table_name)
        log.info("DynamoDB table active: %s", table_name)

        # Enable TTL on any table that declares a TTLAttribute
        ttl_attr = table_config.get("TTLAttribute")
        if ttl_attr:
            ddb_client.update_time_to_live(
                TableName=table_name,
                TimeToLiveSpecification={"Enabled": True, "AttributeName": ttl_attr},
            )
        return True
    except ClientError as e:
        log.error("Failed to create DynamoDB table %s: %s", table_name, e)
        return False


def create_iam_role(iam_client, account_id: str, dry_run: bool) -> str | None:
    log.info("Creating IAM role: %s", IAM_ROLE_NAME)
    if dry_run:
        return f"arn:aws:iam::{account_id}:role/{IAM_ROLE_NAME}"

    try:
        # Create or get policy
        policy_arn = None
        try:
            response = iam_client.create_policy(
                PolicyName=IAM_POLICY_NAME,
                PolicyDocument=json.dumps(IAM_POLICY_DOCUMENT),
                Description="Least-privilege policy for SmartSpend360",
            )
            policy_arn = response["Policy"]["Arn"]
            log.info("IAM policy created: %s", policy_arn)
        except ClientError as e:
            if e.response["Error"]["Code"] == "EntityAlreadyExists":
                policy_arn = f"arn:aws:iam::{account_id}:policy/{IAM_POLICY_NAME}"
                log.info("IAM policy already exists: %s", policy_arn)
            else:
                raise

        # Create or get role
        role_arn = None
        try:
            response = iam_client.create_role(
                RoleName=IAM_ROLE_NAME,
                AssumeRolePolicyDocument=json.dumps(IAM_TRUST_POLICY),
                Description="SmartSpend360 application role",
                Tags=[{"Key": "Project", "Value": "SmartSpend360"}],
            )
            role_arn = response["Role"]["Arn"]
            log.info("IAM role created: %s", role_arn)
        except ClientError as e:
            if e.response["Error"]["Code"] == "EntityAlreadyExists":
                role_arn = iam_client.get_role(RoleName=IAM_ROLE_NAME)["Role"]["Arn"]
                log.info("IAM role already exists: %s", role_arn)
            else:
                raise

        # Attach policy
        iam_client.attach_role_policy(RoleName=IAM_ROLE_NAME, PolicyArn=policy_arn)
        log.info("Policy attached to role")
        return role_arn

    except ClientError as e:
        log.error("Failed to create IAM role: %s", e)
        return None


def create_athena_workgroup(athena_client, region: str, dry_run: bool) -> bool:
    log.info("Creating Athena workgroup: %s", ATHENA_WORKGROUP)
    if dry_run:
        return True

    try:
        athena_client.create_work_group(
            Name=ATHENA_WORKGROUP,
            Configuration={
                "ResultConfiguration": {
                    "OutputLocation": f"s3://{RESULTS_BUCKET}/query-results/",
                    "EncryptionConfiguration": {"EncryptionOption": "SSE_S3"},
                },
                "EnforceWorkGroupConfiguration": True,
                "PublishCloudWatchMetricsEnabled": False,
                "BytesScannedCutoffPerQuery": 1_073_741_824,  # 1 GB safety limit
            },
            Description="SmartSpend360 Athena workgroup",
            Tags=[{"Key": "Project", "Value": "SmartSpend360"}],
        )
        log.info("Athena workgroup created: %s", ATHENA_WORKGROUP)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "InvalidRequestException":
            log.info("Athena workgroup already exists: %s", ATHENA_WORKGROUP)
            return True
        log.error("Failed to create Athena workgroup: %s", e)
        return False


def create_athena_database(athena_client, dry_run: bool) -> bool:
    log.info("Creating Athena database: %s", ATHENA_DATABASE)
    if dry_run:
        return True

    query = f"""
    CREATE DATABASE IF NOT EXISTS {ATHENA_DATABASE}
    COMMENT 'SmartSpend360 data lakehouse database'
    """
    try:
        response = athena_client.start_query_execution(
            QueryString=query,
            WorkGroup=ATHENA_WORKGROUP,
            ResultConfiguration={
                "OutputLocation": f"s3://{RESULTS_BUCKET}/ddl-results/"
            },
        )
        query_id = response["QueryExecutionId"]

        # Poll for completion
        for _ in range(30):
            time.sleep(2)
            result = athena_client.get_query_execution(QueryExecutionId=query_id)
            state = result["QueryExecution"]["Status"]["State"]
            if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
                break

        if state == "SUCCEEDED":
            log.info("Athena database created: %s", ATHENA_DATABASE)
            return True
        log.error("Athena database creation failed, state: %s", state)
        return False
    except ClientError as e:
        log.error("Failed to create Athena database: %s", e)
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Setup SmartSpend360 AWS infrastructure")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without creating resources")
    parser.add_argument("--region", default="us-east-1", help="AWS region (default: us-east-1)")
    parser.add_argument("--skip-iam", action="store_true", help="Skip IAM role creation (requires admin perms)")
    args = parser.parse_args()

    if args.dry_run:
        log.info("DRY RUN mode — no resources will be created")

    session = boto3.Session(region_name=args.region)
    s3 = session.client("s3")
    ddb = session.client("dynamodb")
    iam = session.client("iam")
    athena = session.client("athena")
    sts = session.client("sts")

    try:
        account_id = get_account_id(sts)
        log.info("AWS Account ID: %s | Region: %s", account_id, args.region)
    except ClientError as e:
        log.error("Cannot authenticate with AWS: %s", e)
        log.error("Ensure AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are set in .env")
        sys.exit(1)

    results = {}

    # S3 buckets
    log.info("=== S3 SETUP ===")
    results["datalake_bucket"] = create_s3_bucket(s3, BUCKET_NAME, args.region, args.dry_run)
    results["results_bucket"] = create_s3_bucket(s3, RESULTS_BUCKET, args.region, args.dry_run)
    results["datalake_lifecycle"] = apply_s3_lifecycle(s3, BUCKET_NAME, args.dry_run)
    results["results_lifecycle"] = apply_s3_lifecycle(s3, RESULTS_BUCKET, args.dry_run)
    if results["datalake_bucket"]:
        create_s3_folders(s3, BUCKET_NAME, args.dry_run)

    # DynamoDB tables
    log.info("=== DYNAMODB SETUP ===")
    for table_config in DYNAMODB_TABLES:
        results[f"table_{table_config['TableName']}"] = create_dynamodb_table(
            ddb, table_config, args.dry_run
        )

    # IAM
    if not args.skip_iam:
        log.info("=== IAM SETUP ===")
        results["iam_role"] = create_iam_role(iam, account_id, args.dry_run)

    # Athena
    log.info("=== ATHENA SETUP ===")
    results["athena_workgroup"] = create_athena_workgroup(athena, args.region, args.dry_run)
    if results["athena_workgroup"]:
        results["athena_database"] = create_athena_database(athena, args.dry_run)

    # Summary
    log.info("=== SETUP COMPLETE ===")
    success = all(v for v in results.values() if v is not None)
    for resource, ok in results.items():
        status = "OK" if ok else "FAILED"
        log.info("  [%s] %s", status, resource)

    if not success:
        log.error("Some resources failed to create. Check logs above.")
        sys.exit(1)

    log.info("")
    log.info("SmartSpend360 infrastructure ready!")
    log.info("Next steps:")
    log.info("  1. Copy .env.template to .env and fill in credentials")
    log.info("  2. Run: python data/seed/generate_mock_data.py")
    log.info("  3. Start backend: cd backend && uvicorn app.main:app --reload")
    log.info("  4. Start frontend: cd frontend && npm run dev")


if __name__ == "__main__":
    main()
