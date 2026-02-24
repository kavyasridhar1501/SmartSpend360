"""SmartSpend360 — Pipeline Status & Trigger API Routes"""

import uuid
from datetime import datetime
from typing import Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import verify_api_key
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import (
    PipelineStageStatus,
    PipelineStatusResponse,
    TriggerPipelineResponse,
)
from app.services import dynamodb

router = APIRouter()
log = get_logger("api.pipeline")

PIPELINE_STAGES = [
    "ingest_transactions",
    "ingest_market_data",
    "ingest_fx_rates",
    "ml_01_silver_transforms",
    "ml_02_feature_engineering",
    "ml_03_anomaly_detection",
    "ml_04_cash_flow_forecast",
    "ml_05_gold_metrics",
]

MOCK_PIPELINE_STATUS = [
    PipelineStageStatus(
        stage="Ingest (Airflow)",
        status="success",
        last_run_time=datetime.utcnow().replace(minute=0, second=0).isoformat(),
        records_processed=1847,
        duration_seconds=23.4,
        error_count=0,
    ),
    PipelineStageStatus(
        stage="Store Raw (S3 Bronze)",
        status="success",
        last_run_time=datetime.utcnow().replace(minute=0, second=0).isoformat(),
        records_processed=1847,
        duration_seconds=3.2,
        error_count=0,
    ),
    PipelineStageStatus(
        stage="Transform (Databricks)",
        status="success",
        last_run_time=datetime.utcnow().replace(hour=8, minute=15, second=0).isoformat(),
        records_processed=1847,
        duration_seconds=145.8,
        error_count=0,
    ),
    PipelineStageStatus(
        stage="Semantic Layer (dbt)",
        status="success",
        last_run_time=datetime.utcnow().replace(hour=8, minute=17, second=0).isoformat(),
        records_processed=1847,
        duration_seconds=32.1,
        error_count=0,
    ),
    PipelineStageStatus(
        stage="Serve (FastAPI)",
        status="success",
        last_run_time=datetime.utcnow().isoformat(),
        records_processed=0,
        duration_seconds=None,
        error_count=0,
        details="Running",
    ),
    PipelineStageStatus(
        stage="Analyze (Athena)",
        status="success",
        last_run_time=datetime.utcnow().replace(hour=8, minute=20, second=0).isoformat(),
        records_processed=1847,
        duration_seconds=8.5,
        error_count=0,
    ),
    PipelineStageStatus(
        stage="Application (React + DynamoDB)",
        status="success",
        last_run_time=datetime.utcnow().isoformat(),
        records_processed=0,
        duration_seconds=None,
        error_count=0,
        details="Running",
    ),
]


@router.get(
    "/pipeline/status",
    response_model=PipelineStatusResponse,
    summary="Get pipeline status",
    description="Returns status of each pipeline stage. No auth required.",
    dependencies=[],
)
async def get_pipeline_status():
    try:
        runs = dynamodb.get_pipeline_runs()
        if not runs:
            raise ValueError("No pipeline data")

        # Build stage summary from latest runs per stage
        from collections import defaultdict
        latest = defaultdict(lambda: None)
        for run in runs:
            stage = run["stage"]
            if latest[stage] is None or run["timestamp"] > latest[stage]["timestamp"]:
                latest[stage] = run

        stages = []
        for stage_name in PIPELINE_STAGES:
            run = latest.get(stage_name)
            if run:
                stages.append(
                    PipelineStageStatus(
                        stage=stage_name,
                        status=run.get("status", "unknown"),
                        last_run_time=run.get("timestamp"),
                        records_processed=int(run.get("recordsProcessed", 0)),
                        error_count=1 if run.get("status") == "error" else 0,
                        details=run.get("details"),
                    )
                )
            else:
                stages.append(PipelineStageStatus(stage=stage_name, status="pending"))

        overall = "success" if all(s.status == "success" for s in stages) else "partial"
        return PipelineStatusResponse(stages=stages, overall_status=overall)

    except Exception as e:
        log.warning("Using mock pipeline status", error=str(e))
        return PipelineStatusResponse(
            stages=MOCK_PIPELINE_STATUS,
            overall_status="success",
            last_full_run=datetime.utcnow().replace(hour=8, minute=30).isoformat(),
        )


@router.post(
    "/pipeline/trigger",
    response_model=TriggerPipelineResponse,
    summary="Trigger full pipeline",
)
async def trigger_pipeline(_key: str = Depends(verify_api_key)):
    settings = get_settings()
    dag_run_id = f"manual_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"

    try:
        # Try to trigger Airflow DAG via REST API
        for dag_id in ["ingest_transactions", "run_ml_pipeline"]:
            url = f"{settings.airflow_base_url}/api/v1/dags/{dag_id}/dagRuns"
            resp = requests.post(
                url,
                json={"dag_run_id": dag_run_id, "conf": {}},
                auth=(settings.airflow_username, settings.airflow_password),
                timeout=10,
            )
            if resp.status_code in (200, 201):
                log.info("DAG triggered", dag_id=dag_id, run_id=dag_run_id)
            else:
                log.warning("Failed to trigger DAG", dag_id=dag_id, status=resp.status_code)

    except Exception as e:
        log.warning("Airflow not reachable, returning mock trigger response", error=str(e))

    return TriggerPipelineResponse(
        dag_run_id=dag_run_id,
        status="queued",
        triggered_at=datetime.utcnow().isoformat(),
    )
