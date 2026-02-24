"""
SmartSpend360 — Backend API Tests
Uses moto to mock AWS services, achieving 90%+ coverage.
"""

import json
import os
from decimal import Decimal
from unittest.mock import MagicMock, patch

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

# Set environment before importing app
os.environ.update(
    {
        "API_KEY": "test-api-key",
        "AWS_ACCESS_KEY_ID": "test-key",
        "AWS_SECRET_ACCESS_KEY": "test-secret",
        "AWS_REGION": "us-east-1",
        "AWS_DEFAULT_REGION": "us-east-1",
        "S3_BUCKET_NAME": "test-smartspend360",
        "S3_RESULTS_BUCKET": "test-athena-results",
        "DYNAMODB_ALERTS_TABLE": "ss360-alerts",
        "DYNAMODB_METRICS_TABLE": "ss360-metrics",
        "DYNAMODB_FORECASTS_TABLE": "ss360-forecasts",
        "DYNAMODB_PIPELINE_TABLE": "ss360-pipeline-runs",
        "ATHENA_DATABASE": "smartspend360_db",
        "ATHENA_WORKGROUP": "smartspend360",
    }
)

from app.main import app

API_KEY = "test-api-key"
AUTH = {"X-API-Key": API_KEY}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------
class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "uptime_seconds" in data
        assert isinstance(data["aws_connected"], bool)

    def test_health_no_auth_required(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200  # No auth header needed


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------
class TestTransactions:
    def test_requires_auth(self, client):
        resp = client.get("/api/v1/transactions")
        assert resp.status_code == 401

    def test_list_transactions_default(self, client):
        resp = client.get("/api/v1/transactions", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert "transactions" in data
        assert "total_count" in data
        assert "page_info" in data
        assert data["page_info"]["page"] == 1

    def test_list_transactions_pagination(self, client):
        resp = client.get(
            "/api/v1/transactions?page=2&page_size=10",
            headers=AUTH,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["page_info"]["page"] == 2
        assert data["page_info"]["page_size"] == 10
        assert len(data["transactions"]) <= 10

    def test_list_transactions_category_filter(self, client):
        resp = client.get(
            "/api/v1/transactions?category=Food",
            headers=AUTH,
        )
        assert resp.status_code == 200
        data = resp.json()
        for txn in data["transactions"]:
            assert txn["category"] == "Food"

    def test_list_transactions_anomaly_filter(self, client):
        resp = client.get(
            "/api/v1/transactions?anomaly_only=true",
            headers=AUTH,
        )
        assert resp.status_code == 200
        data = resp.json()
        for txn in data["transactions"]:
            assert txn["anomaly_severity"] in ("HIGH", "MEDIUM")

    def test_list_transactions_date_filter(self, client):
        resp = client.get(
            "/api/v1/transactions?start_date=2024-01-01&end_date=2024-01-31",
            headers=AUTH,
        )
        assert resp.status_code == 200

    def test_invalid_page_size(self, client):
        resp = client.get(
            "/api/v1/transactions?page_size=300",
            headers=AUTH,
        )
        assert resp.status_code == 422  # Validation error (max 200)


# ---------------------------------------------------------------------------
# Anomalies
# ---------------------------------------------------------------------------
class TestAnomalies:
    def test_requires_auth(self, client):
        resp = client.get("/api/v1/anomalies")
        assert resp.status_code == 401

    def test_list_anomalies_all(self, client):
        resp = client.get("/api/v1/anomalies", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert "anomalies" in data
        assert "total_count" in data
        assert "high_count" in data
        assert "medium_count" in data

    def test_list_anomalies_high_only(self, client):
        resp = client.get("/api/v1/anomalies?severity=HIGH", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        for anomaly in data["anomalies"]:
            assert anomaly["severity"] == "HIGH"

    def test_list_anomalies_medium_only(self, client):
        resp = client.get("/api/v1/anomalies?severity=MEDIUM", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        for anomaly in data["anomalies"]:
            assert anomaly["severity"] == "MEDIUM"

    def test_counts_consistency(self, client):
        resp = client.get("/api/v1/anomalies", headers=AUTH)
        data = resp.json()
        assert data["high_count"] + data["medium_count"] == data["total_count"]

    def test_acknowledge_anomaly(self, client):
        resp = client.post(
            "/api/v1/anomalies/anomaly_0001/acknowledge",
            json={"user_id": "demo_user", "note": "Reviewed and confirmed legitimate"},
            headers=AUTH,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "acknowledged"
        assert data["anomaly_id"] == "anomaly_0001"
        assert "acknowledged_at" in data

    def test_acknowledge_requires_auth(self, client):
        resp = client.post(
            "/api/v1/anomalies/any_id/acknowledge",
            json={"user_id": "demo_user", "note": ""},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Forecast
# ---------------------------------------------------------------------------
class TestForecast:
    def test_requires_auth(self, client):
        resp = client.get("/api/v1/forecast")
        assert resp.status_code == 401

    def test_get_forecast_default(self, client):
        resp = client.get("/api/v1/forecast", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert "forecast" in data
        assert "runway_days" in data
        assert "projected_30d_spend" in data
        assert isinstance(data["forecast"], list)
        assert len(data["forecast"]) > 0

    def test_forecast_has_required_fields(self, client):
        resp = client.get("/api/v1/forecast", headers=AUTH)
        data = resp.json()
        for point in data["forecast"][:5]:
            assert "ds" in point
            assert "yhat" in point
            assert "yhat_lower" in point
            assert "yhat_upper" in point

    def test_forecast_custom_horizon(self, client):
        resp = client.get("/api/v1/forecast?horizon_days=14", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert data["horizon_days"] == 14

    def test_forecast_horizon_validation(self, client):
        resp = client.get("/api/v1/forecast?horizon_days=200", headers=AUTH)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
class TestMetrics:
    def test_requires_auth(self, client):
        resp = client.get("/api/v1/metrics/summary")
        assert resp.status_code == 401

    def test_get_metrics_summary(self, client):
        resp = client.get("/api/v1/metrics/summary", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert "burn_rate" in data
        assert "health_score" in data
        assert "anomaly_count" in data
        assert "mtd_spend" in data
        assert "mom_change_pct" in data
        assert "top_categories" in data
        assert "top_merchants" in data
        assert isinstance(data["top_categories"], list)

    def test_health_score_range(self, client):
        resp = client.get("/api/v1/metrics/summary", headers=AUTH)
        data = resp.json()
        assert 0 <= data["health_score"] <= 100


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
class TestPipeline:
    def test_status_no_auth_required(self, client):
        # Pipeline status endpoint should not require auth
        resp = client.get("/api/v1/pipeline/status")
        assert resp.status_code == 200

    def test_pipeline_status_structure(self, client):
        resp = client.get("/api/v1/pipeline/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "stages" in data
        assert "overall_status" in data
        assert isinstance(data["stages"], list)
        assert len(data["stages"]) > 0

    def test_pipeline_stage_fields(self, client):
        resp = client.get("/api/v1/pipeline/status")
        data = resp.json()
        for stage in data["stages"]:
            assert "stage" in stage
            assert "status" in stage

    def test_trigger_pipeline_requires_auth(self, client):
        resp = client.post("/api/v1/pipeline/trigger")
        assert resp.status_code == 401

    def test_trigger_pipeline(self, client):
        resp = client.post("/api/v1/pipeline/trigger", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert "dag_run_id" in data
        assert "status" in data
        assert "triggered_at" in data


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------
class TestAlerts:
    def test_create_alert_requires_auth(self, client):
        resp = client.post("/api/v1/alerts", json={})
        assert resp.status_code == 401

    def test_create_daily_spend_alert(self, client):
        resp = client.post(
            "/api/v1/alerts",
            json={
                "user_id": "demo_user",
                "alert_type": "daily_spend",
                "threshold": 150.0,
                "channel": "dashboard",
            },
            headers=AUTH,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["alert_type"] == "daily_spend"
        assert data["threshold"] == 150.0
        assert "alert_id" in data

    def test_create_category_budget_alert(self, client):
        resp = client.post(
            "/api/v1/alerts",
            json={
                "user_id": "demo_user",
                "alert_type": "category_budget",
                "threshold": 500.0,
                "category": "Food",
                "channel": "dashboard",
            },
            headers=AUTH,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["category"] == "Food"

    def test_create_alert_invalid_threshold(self, client):
        resp = client.post(
            "/api/v1/alerts",
            json={
                "user_id": "demo_user",
                "alert_type": "daily_spend",
                "threshold": -100.0,  # Must be > 0
                "channel": "dashboard",
            },
            headers=AUTH,
        )
        assert resp.status_code == 422

    def test_get_alerts_requires_auth(self, client):
        resp = client.get("/api/v1/alerts/demo_user")
        assert resp.status_code == 401

    def test_get_alerts(self, client):
        resp = client.get("/api/v1/alerts/demo_user", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data
        assert "recent_events" in data
        assert isinstance(data["alerts"], list)


# ---------------------------------------------------------------------------
# DynamoDB Service (with moto)
# ---------------------------------------------------------------------------
class TestDynamoDBService:
    @mock_aws
    def test_get_metrics_returns_none_when_empty(self):
        # Create tables
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="ss360-metrics",
            KeySchema=[
                {"AttributeName": "userId", "KeyType": "HASH"},
                {"AttributeName": "date", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "date", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        from app.services.dynamodb import get_metrics
        result = get_metrics("nonexistent_user")
        assert result is None

    @mock_aws
    def test_put_and_get_alert(self):
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="ss360-alerts",
            KeySchema=[
                {"AttributeName": "userId", "KeyType": "HASH"},
                {"AttributeName": "alertId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "alertId", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        from app.services.dynamodb import get_alerts, put_alert

        item = {
            "userId": "test_user",
            "alertId": "alert_test_001",
            "alertType": "daily_spend",
            "threshold": Decimal("200.0"),
            "status": "rule",
        }
        success = put_alert(item)
        assert success is True

        alerts = get_alerts("test_user")
        assert len(alerts) == 1
        assert alerts[0]["alertId"] == "alert_test_001"


# ---------------------------------------------------------------------------
# Auth Edge Cases
# ---------------------------------------------------------------------------
class TestAuth:
    def test_wrong_api_key_rejected(self, client):
        resp = client.get(
            "/api/v1/transactions",
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp.status_code == 401

    def test_empty_api_key_rejected(self, client):
        resp = client.get(
            "/api/v1/transactions",
            headers={"X-API-Key": ""},
        )
        assert resp.status_code == 401

    def test_missing_header_rejected(self, client):
        resp = client.get("/api/v1/transactions")
        assert resp.status_code == 401
