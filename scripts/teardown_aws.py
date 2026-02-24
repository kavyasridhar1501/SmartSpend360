#!/usr/bin/env python3
"""
SmartSpend360 — AWS Infrastructure Teardown Script
Deletes all provisioned AWS resources to stay within Free Tier limits.

WARNING: This is destructive. All data in S3 and DynamoDB will be deleted.

Usage:
    python scripts/teardown_aws.py
    python scripts/teardown_aws.py --dry-run
    python scripts/teardown_aws.py --skip-confirm
"""

import sys
import time
import argparse
import logging

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

BUCKET_NAME = "smartspend360-datalake"
RESULTS_BUCKET = "smartspend360-athena-results"
ATHENA_WORKGROUP = "smartspend360"
ATHENA_DATABASE = "smartspend360_db"
IAM_ROLE_NAME = "SmartSpend360LambdaRole"
IAM_POLICY_NAME = "SmartSpend360Policy"

DYNAMODB_TABLES = [
    "ss360-alerts",
    "ss360-metrics",
    "ss360-forecasts",
    "ss360-pipeline-runs",
]


def empty_and_delete_bucket(s3_client, bucket_name: str, dry_run: bool) -> bool:
    log.info("Deleting S3 bucket: %s", bucket_name)
    if dry_run:
        return True

    try:
        # Delete all object versions (handles versioned bucket)
        paginator = s3_client.get_paginator("list_object_versions")
        try:
            for page in paginator.paginate(Bucket=bucket_name):
                objects_to_delete = []
                for version in page.get("Versions", []):
                    objects_to_delete.append(
                        {"Key": version["Key"], "VersionId": version["VersionId"]}
                    )
                for marker in page.get("DeleteMarkers", []):
                    objects_to_delete.append(
                        {"Key": marker["Key"], "VersionId": marker["VersionId"]}
                    )
                if objects_to_delete:
                    s3_client.delete_objects(
                        Bucket=bucket_name,
                        Delete={"Objects": objects_to_delete},
                    )
                    log.info("  Deleted %d object versions", len(objects_to_delete))
        except ClientError:
            # Bucket may not have versioning; delete regular objects
            paginator2 = s3_client.get_paginator("list_objects_v2")
            for page in paginator2.paginate(Bucket=bucket_name):
                if "Contents" in page:
                    s3_client.delete_objects(
                        Bucket=bucket_name,
                        Delete={
                            "Objects": [{"Key": obj["Key"]} for obj in page["Contents"]]
                        },
                    )

        s3_client.delete_bucket(Bucket=bucket_name)
        log.info("S3 bucket deleted: %s", bucket_name)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchBucket":
            log.info("S3 bucket does not exist: %s", bucket_name)
            return True
        log.error("Failed to delete S3 bucket %s: %s", bucket_name, e)
        return False


def delete_dynamodb_table(ddb_client, table_name: str, dry_run: bool) -> bool:
    log.info("Deleting DynamoDB table: %s", table_name)
    if dry_run:
        return True

    try:
        ddb_client.delete_table(TableName=table_name)
        # Wait for deletion
        waiter = ddb_client.get_waiter("table_not_exists")
        waiter.wait(TableName=table_name)
        log.info("DynamoDB table deleted: %s", table_name)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            log.info("DynamoDB table does not exist: %s", table_name)
            return True
        log.error("Failed to delete DynamoDB table %s: %s", table_name, e)
        return False


def delete_athena_workgroup(athena_client, dry_run: bool) -> bool:
    log.info("Deleting Athena workgroup: %s", ATHENA_WORKGROUP)
    if dry_run:
        return True

    try:
        # Delete workgroup and recursively delete its contents
        athena_client.delete_work_group(
            WorkGroup=ATHENA_WORKGROUP,
            RecursiveDeleteOption=True,
        )
        log.info("Athena workgroup deleted: %s", ATHENA_WORKGROUP)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "InvalidRequestException":
            log.info("Athena workgroup does not exist: %s", ATHENA_WORKGROUP)
            return True
        log.error("Failed to delete Athena workgroup: %s", e)
        return False


def delete_iam_role(iam_client, account_id: str, dry_run: bool) -> bool:
    log.info("Deleting IAM role: %s", IAM_ROLE_NAME)
    if dry_run:
        return True

    try:
        # Detach managed policies first
        attached = iam_client.list_attached_role_policies(RoleName=IAM_ROLE_NAME)
        for policy in attached.get("AttachedPolicies", []):
            iam_client.detach_role_policy(
                RoleName=IAM_ROLE_NAME,
                PolicyArn=policy["PolicyArn"],
            )
            log.info("  Detached policy: %s", policy["PolicyArn"])

        # Delete inline policies
        inline = iam_client.list_role_policies(RoleName=IAM_ROLE_NAME)
        for policy_name in inline.get("PolicyNames", []):
            iam_client.delete_role_policy(
                RoleName=IAM_ROLE_NAME,
                PolicyName=policy_name,
            )

        iam_client.delete_role(RoleName=IAM_ROLE_NAME)
        log.info("IAM role deleted: %s", IAM_ROLE_NAME)
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchEntity":
            log.info("IAM role does not exist: %s", IAM_ROLE_NAME)
        else:
            log.error("Failed to delete IAM role: %s", e)
            return False

    # Delete the customer-managed policy
    policy_arn = f"arn:aws:iam::{account_id}:policy/{IAM_POLICY_NAME}"
    try:
        # Delete non-default policy versions first
        versions = iam_client.list_policy_versions(PolicyArn=policy_arn)
        for v in versions.get("Versions", []):
            if not v["IsDefaultVersion"]:
                iam_client.delete_policy_version(
                    PolicyArn=policy_arn, VersionId=v["VersionId"]
                )
        iam_client.delete_policy(PolicyArn=policy_arn)
        log.info("IAM policy deleted: %s", policy_arn)
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchEntity":
            log.info("IAM policy does not exist: %s", policy_arn)
        else:
            log.error("Failed to delete IAM policy: %s", e)
            return False

    return True


def main():
    parser = argparse.ArgumentParser(description="Teardown SmartSpend360 AWS infrastructure")
    parser.add_argument("--dry-run", action="store_true", help="Preview deletions without executing")
    parser.add_argument("--skip-confirm", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    parser.add_argument("--skip-iam", action="store_true", help="Skip IAM role/policy deletion")
    args = parser.parse_args()

    if args.dry_run:
        log.info("DRY RUN mode — no resources will be deleted")
    elif not args.skip_confirm:
        print("\n" + "=" * 60)
        print("WARNING: This will permanently delete ALL SmartSpend360")
        print("AWS resources including all data in S3 and DynamoDB!")
        print("=" * 60)
        confirm = input("\nType 'DELETE' to confirm: ")
        if confirm != "DELETE":
            log.info("Teardown cancelled.")
            sys.exit(0)

    session = boto3.Session(region_name=args.region)
    s3 = session.client("s3")
    ddb = session.client("dynamodb")
    iam = session.client("iam")
    athena = session.client("athena")
    sts = session.client("sts")

    try:
        account_id = sts.get_caller_identity()["Account"]
        log.info("AWS Account ID: %s | Region: %s", account_id, args.region)
    except ClientError as e:
        log.error("Cannot authenticate with AWS: %s", e)
        sys.exit(1)

    results = {}

    log.info("=== ATHENA CLEANUP ===")
    results["athena_workgroup"] = delete_athena_workgroup(athena, args.dry_run)

    log.info("=== DYNAMODB CLEANUP ===")
    for table_name in DYNAMODB_TABLES:
        results[f"table_{table_name}"] = delete_dynamodb_table(ddb, table_name, args.dry_run)

    log.info("=== S3 CLEANUP ===")
    results["datalake_bucket"] = empty_and_delete_bucket(s3, BUCKET_NAME, args.dry_run)
    results["results_bucket"] = empty_and_delete_bucket(s3, RESULTS_BUCKET, args.dry_run)

    if not args.skip_iam:
        log.info("=== IAM CLEANUP ===")
        results["iam"] = delete_iam_role(iam, account_id, args.dry_run)

    log.info("=== TEARDOWN COMPLETE ===")
    for resource, ok in results.items():
        status = "OK" if ok else "FAILED"
        log.info("  [%s] %s", status, resource)

    success = all(results.values())
    if not success:
        log.error("Some resources failed to delete. Check AWS Console.")
        sys.exit(1)
    else:
        log.info("All SmartSpend360 resources deleted successfully.")


if __name__ == "__main__":
    main()
