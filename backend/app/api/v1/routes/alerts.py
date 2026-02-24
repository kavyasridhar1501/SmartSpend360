"""SmartSpend360 — Alerts API Routes"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query

from app.core.auth import verify_api_key
from app.core.logging import get_logger
from app.models.schemas import AlertListResponse, AlertRecord, CreateAlertRequest
from app.services import dynamodb

router = APIRouter()
log = get_logger("api.alerts")

MOCK_ALERTS = [
    AlertRecord(
        user_id="demo_user",
        alert_id="alert_0001",
        alert_type="daily_spend",
        threshold=200.0,
        channel="dashboard",
        enabled=True,
        created_at="2024-01-01T00:00:00",
        triggered_count=3,
        last_triggered="2024-01-14T18:30:00",
    ),
    AlertRecord(
        user_id="demo_user",
        alert_id="alert_0002",
        alert_type="single_transaction",
        threshold=500.0,
        channel="dashboard",
        enabled=True,
        created_at="2024-01-05T00:00:00",
        triggered_count=1,
        last_triggered="2024-01-22T14:15:00",
    ),
    AlertRecord(
        user_id="demo_user",
        alert_id="alert_0003",
        alert_type="category_budget",
        threshold=300.0,
        category="Food",
        channel="dashboard",
        enabled=False,
        created_at="2024-01-10T00:00:00",
        triggered_count=0,
        last_triggered=None,
    ),
]

MOCK_EVENTS = [
    {
        "alert_id": "alert_0001",
        "alert_type": "daily_spend",
        "triggered_at": "2024-01-14T18:30:00",
        "actual_value": 245.30,
        "threshold": 200.0,
        "message": "Daily spend $245.30 exceeded limit $200.00",
    },
    {
        "alert_id": "alert_0002",
        "alert_type": "single_transaction",
        "triggered_at": "2024-01-22T14:15:00",
        "actual_value": 680.0,
        "threshold": 500.0,
        "message": "Transaction $680.00 at Delta Airlines exceeded $500.00 limit",
    },
]


@router.post(
    "/alerts",
    response_model=AlertRecord,
    summary="Create a new alert rule",
    status_code=201,
)
async def create_alert(
    body: CreateAlertRequest,
    _key: str = Depends(verify_api_key),
):
    now = datetime.utcnow().isoformat()
    alert_id = f"alert_{uuid.uuid4().hex[:8]}"

    item = {
        "userId": body.user_id,
        "alertId": alert_id,
        "alertType": body.alert_type,
        "threshold": float(body.threshold),
        "category": body.category or "",
        "channel": body.channel,
        "enabled": body.enabled,
        "triggeredCount": 0,
        "createdAt": now,
        "status": "rule",
    }

    try:
        dynamodb.put_alert(item)
    except Exception as e:
        log.warning("Could not save alert to DynamoDB", error=str(e))

    return AlertRecord(
        user_id=body.user_id,
        alert_id=alert_id,
        alert_type=body.alert_type,
        threshold=body.threshold,
        category=body.category,
        channel=body.channel,
        enabled=body.enabled,
        created_at=now,
        triggered_count=0,
    )


@router.get(
    "/alerts/{user_id}",
    response_model=AlertListResponse,
    summary="Get all alerts for a user",
)
async def get_alerts(
    user_id: str = Path(...),
    _key: str = Depends(verify_api_key),
):
    try:
        raw = dynamodb.get_alerts(user_id)
        rule_alerts = [a for a in raw if a.get("status") == "rule"]

        if not rule_alerts:
            raise ValueError("No rules found")

        alerts = [
            AlertRecord(
                user_id=a.get("userId", user_id),
                alert_id=a.get("alertId", ""),
                alert_type=a.get("alertType", ""),
                threshold=float(a.get("threshold", 0)),
                category=a.get("category") or None,
                channel=a.get("channel", "dashboard"),
                enabled=bool(a.get("enabled", True)),
                created_at=str(a.get("createdAt", "")),
                triggered_count=int(a.get("triggeredCount", 0)),
                last_triggered=a.get("lastTriggered"),
            )
            for a in rule_alerts
        ]

        # Recent events from anomaly alerts
        events_raw = [a for a in raw if a.get("alertType") == "anomaly_detected"]
        events = [
            {
                "alert_id": e.get("alertId", ""),
                "alert_type": e.get("alertType", ""),
                "triggered_at": e.get("timestamp", ""),
                "actual_value": float(e.get("dailyTotal", 0)),
                "threshold": 0,
                "message": f"Anomaly detected (severity: {e.get('severity', 'unknown')})",
            }
            for e in events_raw[:20]
        ]

        return AlertListResponse(alerts=alerts, recent_events=events)

    except Exception as e:
        log.warning("Using mock alerts", error=str(e))
        return AlertListResponse(alerts=MOCK_ALERTS, recent_events=MOCK_EVENTS)
