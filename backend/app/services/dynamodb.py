"""SmartSpend360 — DynamoDB Service"""

import json
from datetime import datetime
from typing import Any, Optional

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("dynamodb")


def _get_resource():
    settings = get_settings()
    kwargs = {"region_name": settings.aws_region}
    if settings.aws_access_key_id:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    return boto3.resource("dynamodb", **kwargs)


def _get_client():
    settings = get_settings()
    kwargs = {"region_name": settings.aws_region}
    if settings.aws_access_key_id:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    return boto3.client("dynamodb", **kwargs)


def get_metrics(user_id: str, date: Optional[str] = None) -> Optional[dict]:
    """Fetch latest metrics for a user from DynamoDB."""
    settings = get_settings()
    try:
        dynamodb = _get_resource()
        table = dynamodb.Table(settings.dynamodb_metrics_table)

        if date:
            response = table.get_item(Key={"userId": user_id, "date": date})
            return response.get("Item")
        else:
            # Get latest record
            response = table.query(
                KeyConditionExpression=Key("userId").eq(user_id),
                ScanIndexForward=False,
                Limit=1,
            )
            items = response.get("Items", [])
            return items[0] if items else None
    except ClientError as e:
        log.error("DynamoDB get_metrics failed", error=str(e), user_id=user_id)
        return None


def get_forecast(user_id: str, forecast_date: Optional[str] = None) -> Optional[dict]:
    """Fetch latest forecast for a user."""
    settings = get_settings()
    try:
        dynamodb = _get_resource()
        table = dynamodb.Table(settings.dynamodb_forecasts_table)

        if forecast_date:
            response = table.get_item(Key={"userId": user_id, "forecastDate": forecast_date})
            return response.get("Item")
        else:
            response = table.query(
                KeyConditionExpression=Key("userId").eq(user_id),
                ScanIndexForward=False,
                Limit=1,
            )
            items = response.get("Items", [])
            return items[0] if items else None
    except ClientError as e:
        log.error("DynamoDB get_forecast failed", error=str(e), user_id=user_id)
        return None


def get_alerts(user_id: str) -> list[dict]:
    """Fetch all alerts for a user."""
    settings = get_settings()
    try:
        dynamodb = _get_resource()
        table = dynamodb.Table(settings.dynamodb_alerts_table)
        response = table.query(
            KeyConditionExpression=Key("userId").eq(user_id),
            ScanIndexForward=False,
            Limit=100,
        )
        return response.get("Items", [])
    except ClientError as e:
        log.error("DynamoDB get_alerts failed", error=str(e), user_id=user_id)
        return []


def put_alert(item: dict) -> bool:
    """Save a new alert configuration."""
    settings = get_settings()
    try:
        dynamodb = _get_resource()
        table = dynamodb.Table(settings.dynamodb_alerts_table)
        table.put_item(Item=item)
        return True
    except ClientError as e:
        log.error("DynamoDB put_alert failed", error=str(e))
        return False


def update_anomaly_status(user_id: str, alert_id: str, status: str, note: str) -> bool:
    """Update anomaly acknowledgment status."""
    settings = get_settings()
    try:
        dynamodb = _get_resource()
        table = dynamodb.Table(settings.dynamodb_alerts_table)
        table.update_item(
            Key={"userId": user_id, "alertId": alert_id},
            UpdateExpression="SET #s = :status, acknowledgeNote = :note, acknowledgedAt = :ts",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":status": status,
                ":note": note,
                ":ts": datetime.utcnow().isoformat(),
            },
        )
        return True
    except ClientError as e:
        log.error("DynamoDB update_anomaly_status failed", error=str(e))
        return False


def get_pipeline_runs(stage: Optional[str] = None) -> list[dict]:
    """Fetch recent pipeline run records."""
    settings = get_settings()
    try:
        dynamodb = _get_resource()
        table = dynamodb.Table(settings.dynamodb_pipeline_table)

        if stage:
            response = table.query(
                KeyConditionExpression=Key("stage").eq(stage),
                ScanIndexForward=False,
                Limit=5,
            )
            return response.get("Items", [])
        else:
            # Scan for all stages (small table)
            response = table.scan(Limit=100)
            return response.get("Items", [])
    except ClientError as e:
        log.error("DynamoDB get_pipeline_runs failed", error=str(e))
        return []


def get_anomaly_alerts(user_id: str, severity: Optional[str] = None) -> list[dict]:
    """Fetch anomaly alerts, optionally filtered by severity."""
    alerts = get_alerts(user_id)
    anomaly_alerts = [a for a in alerts if a.get("alertType") == "anomaly_detected"]
    if severity and severity != "ALL":
        anomaly_alerts = [a for a in anomaly_alerts if a.get("severity") == severity]
    return anomaly_alerts
