"""SmartSpend360 — Application Configuration"""

import json
import os
from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_name: str = "SmartSpend360"
    app_version: str = "1.0.0"
    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # Security
    api_key: str = os.getenv("API_KEY", "dev-secret-key-change-in-production")
    api_key_name: str = "X-API-Key"

    # CORS
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "https://smartspend360-app-pink.vercel.app",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> object:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # AWS
    aws_access_key_id: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    aws_secret_access_key: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    aws_region: str = os.getenv("AWS_REGION", "us-east-1")

    # S3
    s3_bucket_name: str = os.getenv("S3_BUCKET_NAME", "smartspend360-datalake")
    s3_results_bucket: str = os.getenv("S3_RESULTS_BUCKET", "smartspend360-athena-results")

    # DynamoDB
    dynamodb_alerts_table: str = os.getenv("DYNAMODB_ALERTS_TABLE", "ss360-alerts")
    dynamodb_metrics_table: str = os.getenv("DYNAMODB_METRICS_TABLE", "ss360-metrics")
    dynamodb_forecasts_table: str = os.getenv("DYNAMODB_FORECASTS_TABLE", "ss360-forecasts")
    dynamodb_pipeline_table: str = os.getenv("DYNAMODB_PIPELINE_TABLE", "ss360-pipeline-runs")

    # Athena
    athena_workgroup: str = os.getenv("ATHENA_WORKGROUP", "smartspend360")
    athena_database: str = os.getenv("ATHENA_DATABASE", "smartspend360_db")
    athena_output_location: str = os.getenv(
        "ATHENA_OUTPUT_LOCATION",
        "s3://smartspend360-athena-results/query-results/",
    )
    athena_poll_interval: float = 1.0
    athena_max_wait: int = 60

    # Airflow
    airflow_base_url: str = os.getenv("AIRFLOW_BASE_URL", "http://localhost:8080")
    airflow_username: str = os.getenv("AIRFLOW_WWW_USER_USERNAME", "admin")
    airflow_password: str = os.getenv("AIRFLOW_WWW_USER_PASSWORD", "admin")

    # Server
    port: int = int(os.getenv("PORT", "8000"))

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
