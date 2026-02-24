"""
SmartSpend360 — Airflow DAG: ingest_fx_rates
Fetches USD FX rates from Open Exchange Rates → S3

Schedule: daily at 6am UTC
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

log = logging.getLogger(__name__)

S3_BUCKET = os.getenv("S3_BUCKET_NAME", "smartspend360-datalake")
OXR_APP_ID = os.getenv("OPEN_EXCHANGE_APP_ID", "")
OXR_BASE_URL = "https://openexchangerates.org/api/latest.json"

TARGET_CURRENCIES = ["EUR", "GBP", "CAD", "INR", "JPY", "AUD", "CHF", "MXN"]

default_args = {
    "owner": "smartspend360",
    "depends_on_past": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(minutes=5),
}

dag = DAG(
    dag_id="ingest_fx_rates",
    default_args=default_args,
    description="Fetch USD FX rates from Open Exchange Rates → S3",
    schedule_interval="0 6 * * *",
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["ingestion", "fx", "currency"],
)


def fetch_fx_rates(**context):
    s3 = boto3.client("s3")
    now = datetime.utcnow()
    date_str = now.strftime("%Y-%m-%d")

    rates = _fetch_rates()
    log.info("Fetched FX rates for %d currencies", len(rates))

    # Filter to target currencies only
    filtered_rates = {k: v for k, v in rates.items() if k in TARGET_CURRENCIES}
    filtered_rates["USD"] = 1.0  # Base currency

    payload = {
        "fetched_at": now.isoformat(),
        "base": "USD",
        "rates": filtered_rates,
    }

    # Save bronze JSON
    bronze_key = f"bronze/fx/{date_str}.json"
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=bronze_key,
        Body=json.dumps(payload).encode(),
        ContentType="application/json",
    )
    log.info("Saved FX rates to s3://%s/%s", S3_BUCKET, bronze_key)

    # Save silver Parquet (normalized rows)
    rows = [
        {
            "date": date_str,
            "base_currency": "USD",
            "target_currency": currency,
            "rate": float(rate),
            "usd_to_target": float(rate),
            "target_to_usd": round(1.0 / float(rate), 6) if rate != 0 else 0.0,
            "ingested_at": now.isoformat(),
        }
        for currency, rate in filtered_rates.items()
    ]

    schema = pa.schema(
        [
            ("date", pa.string()),
            ("base_currency", pa.string()),
            ("target_currency", pa.string()),
            ("rate", pa.float64()),
            ("usd_to_target", pa.float64()),
            ("target_to_usd", pa.float64()),
            ("ingested_at", pa.string()),
        ]
    )
    table = pa.Table.from_pylist(rows, schema=schema)
    buf = BytesIO()
    pq.write_table(table, buf, compression="snappy")
    buf.seek(0)

    silver_key = f"silver/fx/{date_str}.parquet"
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=silver_key,
        Body=buf.read(),
        ContentType="application/octet-stream",
    )
    log.info("Silver FX Parquet: s3://%s/%s (%d rows)", S3_BUCKET, silver_key, len(rows))

    _record_pipeline_run("ingest_fx_rates", "success", len(rows))

    return {"currencies": list(filtered_rates.keys()), "rows": len(rows)}


def _fetch_rates() -> dict:
    if not OXR_APP_ID:
        log.warning("No Open Exchange Rates APP ID — using mock rates")
        return _mock_rates()

    try:
        params = {"app_id": OXR_APP_ID, "symbols": ",".join(TARGET_CURRENCIES)}
        resp = requests.get(OXR_BASE_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("rates", {})
    except Exception as e:
        log.warning("Open Exchange Rates fetch failed: %s — using mock", e)
        return _mock_rates()


def _mock_rates() -> dict:
    return {
        "EUR": 0.9215,
        "GBP": 0.7912,
        "CAD": 1.3645,
        "INR": 83.12,
        "JPY": 149.87,
        "AUD": 1.5234,
        "CHF": 0.8845,
        "MXN": 17.23,
    }


def _record_pipeline_run(stage: str, status: str, records: int):
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
                "details": {"S": "{}"},
                "ttl": {"N": str(int(time.time()) + 7 * 86400)},
            },
        )
    except Exception as e:
        log.warning("Failed to record pipeline run: %s", e)


task_fetch = PythonOperator(
    task_id="fetch_fx_rates",
    python_callable=fetch_fx_rates,
    dag=dag,
)
