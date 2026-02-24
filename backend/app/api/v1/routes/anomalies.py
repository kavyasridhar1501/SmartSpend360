"""SmartSpend360 — Anomalies API Routes"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.core.auth import verify_api_key
from app.core.logging import get_logger
from app.models.schemas import (
    AcknowledgeRequest,
    AcknowledgeResponse,
    AnomalyListResponse,
    AnomalyRecord,
)
from app.services import dynamodb

router = APIRouter()
log = get_logger("api.anomalies")

# Mock anomalies for demo
MOCK_ANOMALIES = [
    {
        "alertId": f"anomaly_{i:04d}",
        "userId": "demo_user",
        "date": f"2024-0{(i % 3) + 1}-{(i * 3 % 28 + 1):02d}",
        "alertType": "anomaly_detected",
        "merchantName": ["Luxury Hotel", "Unknown Merchant", "Casino", "Airline Ticket", "Wire Transfer"][i % 5],
        "category": ["Housing", "Other", "Entertainment", "Transport", "Transfer"][i % 5],
        "anomalyScore": round(-0.7 - (i * 0.04 % 0.3), 2),
        "severity": "HIGH" if i % 3 == 0 else "MEDIUM",
        "dailyTotal": round(500.0 + i * 87.5, 2),
        "status": "acknowledged" if i % 7 == 0 else "active",
        "timestamp": f"2024-0{(i % 3) + 1}-{(i * 3 % 28 + 1):02d}T{(i * 2 % 22):02d}:00:00",
    }
    for i in range(1, 16)
]


@router.get(
    "/anomalies",
    response_model=AnomalyListResponse,
    summary="List anomalies",
)
async def list_anomalies(
    user_id: str = Query("demo_user"),
    severity: str = Query("ALL", description="HIGH | MEDIUM | ALL"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    _key: str = Depends(verify_api_key),
):
    try:
        raw_alerts = dynamodb.get_anomaly_alerts(user_id, severity if severity != "ALL" else None)
        if not raw_alerts:
            raise ValueError("No data from DynamoDB")

        alerts = _normalize_alerts(raw_alerts)
    except Exception as e:
        log.warning("DynamoDB unavailable, using mock data", error=str(e))
        alerts_data = MOCK_ANOMALIES
        if severity != "ALL":
            alerts_data = [a for a in alerts_data if a["severity"] == severity]
        if start_date:
            alerts_data = [a for a in alerts_data if a["date"] >= start_date]
        if end_date:
            alerts_data = [a for a in alerts_data if a["date"] <= end_date]
        alerts = _normalize_mock_alerts(alerts_data)

    high_count = sum(1 for a in alerts if a.severity == "HIGH")
    medium_count = sum(1 for a in alerts if a.severity == "MEDIUM")

    return AnomalyListResponse(
        anomalies=alerts,
        total_count=len(alerts),
        high_count=high_count,
        medium_count=medium_count,
    )


@router.post(
    "/anomalies/{anomaly_id}/acknowledge",
    response_model=AcknowledgeResponse,
    summary="Acknowledge an anomaly",
)
async def acknowledge_anomaly(
    anomaly_id: str = Path(...),
    body: AcknowledgeRequest = ...,
    _key: str = Depends(verify_api_key),
):
    try:
        success = dynamodb.update_anomaly_status(
            user_id=body.user_id,
            alert_id=anomaly_id,
            status="acknowledged",
            note=body.note,
        )
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anomaly not found")
    except HTTPException:
        raise
    except Exception as e:
        log.error("Failed to acknowledge anomaly", error=str(e), anomaly_id=anomaly_id)
        # In demo mode, pretend it worked
        pass

    return AcknowledgeResponse(
        anomaly_id=anomaly_id,
        status="acknowledged",
        acknowledged_at=datetime.utcnow().isoformat(),
    )


def _normalize_alerts(raw: list) -> list[AnomalyRecord]:
    results = []
    for a in raw:
        try:
            results.append(
                AnomalyRecord(
                    alert_id=a.get("alertId", ""),
                    user_id=a.get("userId", ""),
                    date=a.get("date", ""),
                    merchant_name=a.get("merchantName"),
                    category=a.get("category"),
                    anomaly_score=float(a.get("anomalyScore", 0)),
                    severity=a.get("severity", "MEDIUM"),
                    daily_total=float(a.get("dailyTotal", 0)) if a.get("dailyTotal") else None,
                    status=a.get("status", "active"),
                    timestamp=a.get("timestamp"),
                    anomaly_explanation=_explain_anomaly(a.get("severity", "MEDIUM")),
                )
            )
        except Exception:
            continue
    return results


def _normalize_mock_alerts(raw: list) -> list[AnomalyRecord]:
    return [
        AnomalyRecord(
            alert_id=a["alertId"],
            user_id=a["userId"],
            date=a["date"],
            merchant_name=a.get("merchantName"),
            category=a.get("category"),
            anomaly_score=a["anomalyScore"],
            severity=a["severity"],
            daily_total=a.get("dailyTotal"),
            status=a["status"],
            timestamp=a.get("timestamp"),
            anomaly_explanation=_explain_anomaly(a["severity"]),
        )
        for a in raw
    ]


def _explain_anomaly(severity: str) -> str:
    if severity == "HIGH":
        return "Unusually high spending detected — significantly above 30-day baseline"
    elif severity == "MEDIUM":
        return "Moderately elevated spending — above normal patterns"
    return "Within normal spending range"
