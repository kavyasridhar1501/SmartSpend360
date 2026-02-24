"""
SmartSpend360 — Airflow DAG: ingest_transactions
Fetches Plaid sandbox transactions → validates → converts to Parquet → S3

Schedule: every 15 minutes
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta
from io import BytesIO

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
import requests
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from botocore.exceptions import ClientError

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
S3_BUCKET = os.getenv("S3_BUCKET_NAME", "smartspend360-datalake")
PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID", "")
PLAID_SECRET = os.getenv("PLAID_SECRET", "")
PLAID_ENV = os.getenv("PLAID_ENV", "sandbox")
PLAID_ACCESS_TOKEN = os.getenv("PLAID_ACCESS_TOKEN", "")
PLAID_BASE_URL = f"https://{PLAID_ENV}.plaid.com"

REQUIRED_FIELDS = {"transaction_id", "amount", "date", "merchant_name", "category"}
ERROR_RATE_THRESHOLD = 0.05  # 5%

DYNAMODB_TABLE = os.getenv("DYNAMODB_ALERTS_TABLE", "ss360-alerts")

# ---------------------------------------------------------------------------
# DAG default args
# ---------------------------------------------------------------------------
default_args = {
    "owner": "smartspend360",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "execution_timeout": timedelta(minutes=10),
}

dag = DAG(
    dag_id="ingest_transactions",
    default_args=default_args,
    description="Fetch Plaid transactions → S3 bronze → validate → silver Parquet",
    schedule_interval="*/15 * * * *",
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["ingestion", "plaid", "transactions"],
)


# ---------------------------------------------------------------------------
# Task 1: Fetch Plaid Transactions
# ---------------------------------------------------------------------------
def fetch_plaid_transactions(**context):
    start_ts = time.time()
    now = datetime.utcnow()
    end_date = now.strftime("%Y-%m-%d")
    start_date = (now - timedelta(days=90)).strftime("%Y-%m-%d")

    log.info("Fetching Plaid transactions: %s to %s", start_date, end_date)

    s3 = boto3.client("s3")

    # If no real Plaid credentials, use mock data
    if not PLAID_CLIENT_ID or not PLAID_ACCESS_TOKEN:
        log.warning("No Plaid credentials found — generating mock data")
        transactions = _generate_mock_transactions(now, 90)
    else:
        transactions = _fetch_from_plaid(start_date, end_date)

    elapsed = time.time() - start_ts
    record_count = len(transactions)
    log.info("Fetched %d transactions in %.2fs", record_count, elapsed)

    # Save to S3 bronze layer
    key = (
        f"bronze/transactions/{now.year}/{now.month:02d}/"
        f"{now.day:02d}/{now.hour:02d}/raw.json"
    )
    payload = {
        "ingested_at": now.isoformat(),
        "record_count": record_count,
        "api_response_time_ms": round(elapsed * 1000, 2),
        "transactions": transactions,
    }

    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(payload, default=str).encode("utf-8"),
        ContentType="application/json",
    )
    log.info("Saved raw data to s3://%s/%s", S3_BUCKET, key)

    # Push to XCom for downstream tasks
    context["ti"].xcom_push(key="bronze_s3_key", value=key)
    context["ti"].xcom_push(key="record_count", value=record_count)
    context["ti"].xcom_push(key="transactions", value=transactions)

    return {"s3_key": key, "record_count": record_count}


def _fetch_from_plaid(start_date: str, end_date: str) -> list:
    headers = {"Content-Type": "application/json"}
    payload = {
        "client_id": PLAID_CLIENT_ID,
        "secret": PLAID_SECRET,
        "access_token": PLAID_ACCESS_TOKEN,
        "start_date": start_date,
        "end_date": end_date,
    }

    all_transactions = []
    offset = 0
    while True:
        payload["options"] = {"count": 500, "offset": offset}
        resp = requests.post(
            f"{PLAID_BASE_URL}/transactions/get",
            json=payload,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("transactions", [])
        all_transactions.extend(batch)
        if len(all_transactions) >= data.get("total_transactions", 0):
            break
        offset += len(batch)

    return all_transactions


def _generate_mock_transactions(now: datetime, days: int = 90) -> list:
    """Generate realistic mock transactions for demo/testing purposes."""
    import random

    merchants = [
        ("Whole Foods Market", "Food and Drink", 45.0, 180.0),
        ("Starbucks", "Food and Drink", 4.5, 12.0),
        ("Netflix", "Entertainment", 15.49, 15.49),
        ("Spotify", "Entertainment", 9.99, 9.99),
        ("Amazon", "Shopping", 20.0, 250.0),
        ("Shell Gas Station", "Transportation", 35.0, 80.0),
        ("Uber", "Transportation", 8.0, 45.0),
        ("CVS Pharmacy", "Healthcare", 12.0, 85.0),
        ("Planet Fitness", "Healthcare", 10.0, 25.0),
        ("Con Edison", "Housing", 80.0, 160.0),
        ("Rent Payment", "Housing", 1500.0, 1500.0),
        ("Chase Mortgage", "Housing", 1200.0, 2500.0),
        ("Trader Joe's", "Food and Drink", 25.0, 90.0),
        ("Target", "Shopping", 30.0, 150.0),
        ("T-Mobile", "Utilities", 45.0, 80.0),
        ("Chipotle", "Food and Drink", 10.0, 22.0),
        ("Apple App Store", "Entertainment", 0.99, 9.99),
        ("New York Times", "Entertainment", 4.0, 17.0),
        ("Payroll Deposit", "Income", -3000.0, -6000.0),
        ("Freelance Payment", "Income", -500.0, -2500.0),
        ("ATM Withdrawal", "Transfer", 100.0, 300.0),
    ]

    transactions = []
    txn_date = now - timedelta(days=days)
    anomaly_days = sorted(
        random.sample(range(1, days), min(10, days - 1))
    )

    while txn_date <= now:
        day_count = random.randint(3, 8)
        is_anomaly_day = (now - txn_date).days in anomaly_days

        for _ in range(day_count):
            merchant_info = random.choice(merchants)
            name, category, min_amt, max_amt = merchant_info
            amount = round(random.uniform(min_amt, max_amt), 2)

            if is_anomaly_day and random.random() < 0.4:
                amount = round(amount * random.uniform(5, 20), 2)

            transactions.append(
                {
                    "transaction_id": f"txn_{uuid.uuid4().hex[:16]}",
                    "account_id": "acc_demo_checking",
                    "amount": amount,
                    "date": txn_date.strftime("%Y-%m-%d"),
                    "merchant_name": name,
                    "name": name,
                    "category": [category],
                    "category_id": f"cat_{category.replace(' ', '_').lower()}",
                    "payment_channel": random.choice(["in store", "online"]),
                    "pending": False,
                    "iso_currency_code": "USD",
                    "location": {
                        "city": random.choice(["New York", "San Francisco", "Chicago"]),
                        "country": "US",
                    },
                }
            )
        txn_date += timedelta(days=1)

    return transactions


# ---------------------------------------------------------------------------
# Task 2: Validate Schema
# ---------------------------------------------------------------------------
def validate_schema(**context):
    ti = context["ti"]
    transactions = ti.xcom_pull(key="transactions", task_ids="fetch_plaid_transactions")

    if not transactions:
        raise ValueError("No transactions received from previous task")

    valid = []
    quarantine = []

    for txn in transactions:
        missing = REQUIRED_FIELDS - set(txn.keys())
        if missing:
            txn["_quarantine_reason"] = f"Missing fields: {missing}"
            quarantine.append(txn)
        elif not isinstance(txn.get("amount"), (int, float)):
            txn["_quarantine_reason"] = "Invalid amount type"
            quarantine.append(txn)
        elif not txn.get("date"):
            txn["_quarantine_reason"] = "Missing date"
            quarantine.append(txn)
        else:
            valid.append(txn)

    total = len(transactions)
    error_rate = len(quarantine) / total if total > 0 else 0

    log.info(
        "Validation: %d valid, %d quarantined (error_rate=%.2f%%)",
        len(valid), len(quarantine), error_rate * 100,
    )

    # Save quarantined records
    if quarantine:
        s3 = boto3.client("s3")
        now = datetime.utcnow()
        q_key = f"bronze/quarantine/{now.strftime('%Y/%m/%d/%H')}/quarantine.json"
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=q_key,
            Body=json.dumps(quarantine, default=str).encode("utf-8"),
            ContentType="application/json",
        )
        log.info("Quarantined %d records to s3://%s/%s", len(quarantine), S3_BUCKET, q_key)

    # Alert if error rate exceeds threshold
    if error_rate > ERROR_RATE_THRESHOLD:
        _send_alert(
            alert_type="schema_error_rate",
            message=f"Transaction schema error rate {error_rate:.1%} exceeds {ERROR_RATE_THRESHOLD:.1%} threshold",
            severity="HIGH",
        )

    ti.xcom_push(key="valid_transactions", value=valid)
    ti.xcom_push(key="error_rate", value=error_rate)

    return {"valid_count": len(valid), "quarantine_count": len(quarantine)}


def _send_alert(alert_type: str, message: str, severity: str = "MEDIUM"):
    try:
        ddb = boto3.client("dynamodb")
        now = datetime.utcnow()
        ddb.put_item(
            TableName=DYNAMODB_TABLE,
            Item={
                "userId": {"S": "system"},
                "alertId": {"S": f"alert_{uuid.uuid4().hex[:8]}"},
                "alertType": {"S": alert_type},
                "message": {"S": message},
                "severity": {"S": severity},
                "timestamp": {"S": now.isoformat()},
                "status": {"S": "active"},
            },
        )
    except Exception as e:
        log.error("Failed to send alert to DynamoDB: %s", e)


# ---------------------------------------------------------------------------
# Task 3: Convert to Parquet
# ---------------------------------------------------------------------------
def convert_to_parquet(**context):
    ti = context["ti"]
    valid_transactions = ti.xcom_pull(
        key="valid_transactions", task_ids="validate_schema"
    )

    if not valid_transactions:
        log.warning("No valid transactions to convert")
        return {"rows": 0, "file_size_bytes": 0}

    s3 = boto3.client("s3")
    now = datetime.utcnow()

    # Normalize to flat structure
    rows = []
    for txn in valid_transactions:
        category = txn.get("category", ["Other"])
        rows.append(
            {
                "transaction_id": txn.get("transaction_id", ""),
                "account_id": txn.get("account_id", ""),
                "amount": float(txn.get("amount", 0.0)),
                "date": txn.get("date", ""),
                "merchant_name": txn.get("merchant_name") or txn.get("name", "Unknown"),
                "category": category[0] if isinstance(category, list) else category,
                "category_id": txn.get("category_id", ""),
                "payment_channel": txn.get("payment_channel", ""),
                "pending": bool(txn.get("pending", False)),
                "iso_currency_code": txn.get("iso_currency_code", "USD"),
                "ingested_at": now.isoformat(),
            }
        )

    # Build PyArrow table
    schema = pa.schema(
        [
            ("transaction_id", pa.string()),
            ("account_id", pa.string()),
            ("amount", pa.float64()),
            ("date", pa.string()),
            ("merchant_name", pa.string()),
            ("category", pa.string()),
            ("category_id", pa.string()),
            ("payment_channel", pa.string()),
            ("pending", pa.bool_()),
            ("iso_currency_code", pa.string()),
            ("ingested_at", pa.string()),
        ]
    )
    table = pa.Table.from_pylist(rows, schema=schema)

    # Write Parquet to buffer
    buf = BytesIO()
    pq.write_table(table, buf, compression="snappy")
    buf.seek(0)
    parquet_bytes = buf.read()

    # Upload to silver layer
    silver_key = f"silver/transactions/{now.strftime('%Y-%m-%d')}.parquet"
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=silver_key,
        Body=parquet_bytes,
        ContentType="application/octet-stream",
    )

    file_size = len(parquet_bytes)
    log.info(
        "Parquet written: s3://%s/%s (%d rows, %.1f KB)",
        S3_BUCKET, silver_key, len(rows), file_size / 1024,
    )

    # Log metadata
    _record_pipeline_run(
        stage="ingest_transactions",
        status="success",
        records=len(rows),
        details={"silver_key": silver_key, "file_size_bytes": file_size},
    )

    return {"rows": len(rows), "file_size_bytes": file_size, "s3_key": silver_key}


def _record_pipeline_run(stage: str, status: str, records: int, details: dict):
    try:
        ddb = boto3.client("dynamodb")
        now = datetime.utcnow()
        ddb.put_item(
            TableName="ss360-pipeline-runs",
            Item={
                "stage": {"S": stage},
                "runId": {"S": f"run_{now.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"},
                "status": {"S": status},
                "recordsProcessed": {"N": str(records)},
                "timestamp": {"S": now.isoformat()},
                "details": {"S": json.dumps(details)},
                "ttl": {"N": str(int(time.time()) + 7 * 86400)},  # 7-day TTL
            },
        )
    except Exception as e:
        log.warning("Failed to record pipeline run: %s", e)


# ---------------------------------------------------------------------------
# Wire up tasks
# ---------------------------------------------------------------------------
task_fetch = PythonOperator(
    task_id="fetch_plaid_transactions",
    python_callable=fetch_plaid_transactions,
    dag=dag,
)

task_validate = PythonOperator(
    task_id="validate_schema",
    python_callable=validate_schema,
    dag=dag,
)

task_parquet = PythonOperator(
    task_id="convert_to_parquet",
    python_callable=convert_to_parquet,
    dag=dag,
)

task_fetch >> task_validate >> task_parquet
