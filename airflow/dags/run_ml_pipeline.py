"""
SmartSpend360 — Airflow DAG: run_ml_pipeline
Triggers Databricks Community Edition notebooks via REST API

Schedule: daily at 8am UTC
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta

import boto3
import requests
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

log = logging.getLogger(__name__)

DATABRICKS_HOST = os.getenv("DATABRICKS_HOST", "https://community.cloud.databricks.com")
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN", "")
DATABRICKS_CLUSTER_ID = os.getenv("DATABRICKS_CLUSTER_ID", "")
DATABRICKS_NOTEBOOK_BASE = os.getenv(
    "DATABRICKS_NOTEBOOK_BASE", "/Users/user@example.com/smartspend360"
)

NOTEBOOKS = [
    "01_silver_transforms",
    "02_feature_engineering",
    "03_anomaly_detection",
    "04_cash_flow_forecast",
    "05_gold_metrics",
]

POLL_INTERVAL_SECONDS = 30
MAX_WAIT_SECONDS = 3600  # 1 hour max

default_args = {
    "owner": "smartspend360",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
    "execution_timeout": timedelta(hours=2),
}

dag = DAG(
    dag_id="run_ml_pipeline",
    default_args=default_args,
    description="Trigger Databricks ML notebooks sequentially",
    schedule_interval="0 8 * * *",
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["ml", "databricks", "pipeline"],
)


class DatabricksClient:
    def __init__(self, host: str, token: str):
        self.host = host.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def run_notebook(self, notebook_path: str, cluster_id: str, params: dict = None) -> str:
        """Submit a notebook run and return the run_id."""
        payload = {
            "run_name": f"smartspend360_{os.path.basename(notebook_path)}",
            "existing_cluster_id": cluster_id,
            "notebook_task": {
                "notebook_path": notebook_path,
                "base_parameters": params or {},
            },
        }
        resp = requests.post(
            f"{self.host}/api/2.0/jobs/runs/submit",
            headers=self.headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return str(resp.json()["run_id"])

    def get_run_state(self, run_id: str) -> dict:
        resp = requests.get(
            f"{self.host}/api/2.0/jobs/runs/get",
            headers=self.headers,
            params={"run_id": run_id},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        state = data.get("state", {})
        return {
            "life_cycle_state": state.get("life_cycle_state", "UNKNOWN"),
            "result_state": state.get("result_state", ""),
            "state_message": state.get("state_message", ""),
        }

    def wait_for_completion(self, run_id: str, timeout: int = MAX_WAIT_SECONDS) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            state = self.get_run_state(run_id)
            life_cycle = state["life_cycle_state"]
            log.info("Run %s state: %s", run_id, life_cycle)

            if life_cycle == "TERMINATED":
                result = state["result_state"]
                if result == "SUCCESS":
                    log.info("Run %s completed successfully", run_id)
                    return True
                log.error("Run %s failed: %s | %s", run_id, result, state["state_message"])
                return False
            elif life_cycle in ("INTERNAL_ERROR", "SKIPPED"):
                log.error("Run %s errored: %s", run_id, state["state_message"])
                return False

            time.sleep(POLL_INTERVAL_SECONDS)

        log.error("Run %s timed out after %ds", run_id, timeout)
        return False


def _make_task(notebook_name: str):
    """Factory that creates a PythonOperator task for each notebook."""

    def run_notebook(**context):
        now = datetime.utcnow()
        date_str = now.strftime("%Y-%m-%d")

        if not DATABRICKS_TOKEN or not DATABRICKS_CLUSTER_ID:
            log.warning(
                "No Databricks credentials — simulating notebook run for %s", notebook_name
            )
            time.sleep(2)  # Simulate work
            _record_pipeline_run(notebook_name, "success", 0, simulated=True)
            return {"notebook": notebook_name, "simulated": True, "status": "success"}

        client = DatabricksClient(DATABRICKS_HOST, DATABRICKS_TOKEN)
        notebook_path = f"{DATABRICKS_NOTEBOOK_BASE}/{notebook_name}"

        log.info("Submitting notebook: %s", notebook_path)
        params = {"run_date": date_str, "s3_bucket": os.getenv("S3_BUCKET_NAME", "smartspend360-datalake")}

        try:
            run_id = client.run_notebook(notebook_path, DATABRICKS_CLUSTER_ID, params)
            log.info("Notebook submitted, run_id=%s", run_id)

            success = client.wait_for_completion(run_id)
            status = "success" if success else "failed"

            _record_pipeline_run(notebook_name, status, 0)

            if not success:
                raise RuntimeError(f"Databricks notebook {notebook_name} failed")

            return {"notebook": notebook_name, "run_id": run_id, "status": status}

        except Exception as e:
            _record_pipeline_run(notebook_name, "error", 0, error=str(e))
            raise

    run_notebook.__name__ = f"run_{notebook_name}"
    return run_notebook


def _record_pipeline_run(
    stage: str, status: str, records: int, simulated: bool = False, error: str = ""
):
    try:
        ddb = boto3.client("dynamodb")
        now = datetime.utcnow()
        ddb.put_item(
            TableName="ss360-pipeline-runs",
            Item={
                "stage": {"S": f"ml_{stage}"},
                "runId": {"S": f"run_{now.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"},
                "status": {"S": status},
                "recordsProcessed": {"N": str(records)},
                "timestamp": {"S": now.isoformat()},
                "details": {"S": json.dumps({"simulated": simulated, "error": error})},
                "ttl": {"N": str(int(time.time()) + 7 * 86400)},
            },
        )
    except Exception as e:
        log.warning("Failed to record pipeline run: %s", e)


# Build tasks and chain them
previous_task = None
for notebook in NOTEBOOKS:
    task = PythonOperator(
        task_id=f"run_{notebook}",
        python_callable=_make_task(notebook),
        dag=dag,
    )
    if previous_task:
        previous_task >> task
    previous_task = task
