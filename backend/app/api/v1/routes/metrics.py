"""SmartSpend360 — Metrics Summary API Routes"""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.core.auth import verify_api_key
from app.core.logging import get_logger
from app.models.schemas import MetricsSummaryResponse
from app.services import dynamodb

router = APIRouter()
log = get_logger("api.metrics")

MOCK_METRICS = {
    "userId": "demo_user",
    "date": datetime.utcnow().strftime("%Y-%m-%d"),
    "monthlyBurnRate": 2847.50,
    "healthScore": 72,
    "anomalyCount": 8,
    "highAnomalyCount": 3,
    "mtdSpend": 1423.75,
    "lastMonthSpend": 2915.20,
    "momChangePct": -3.2,
    "avgDailySpend": 94.92,
    "runwayDays": 45,
    "projected30dSpend": 2847.50,
    "topCategories": [
        {"category": "Housing", "amount_abs": 1500.0, "percentage": 38.5, "mom_change": 0.0},
        {"category": "Food", "amount_abs": 612.3, "percentage": 15.7, "mom_change": -4.2},
        {"category": "Transport", "amount_abs": 380.5, "percentage": 9.8, "mom_change": 12.1},
        {"category": "Entertainment", "amount_abs": 215.0, "percentage": 5.5, "mom_change": 8.3},
        {"category": "Healthcare", "amount_abs": 145.0, "percentage": 3.7, "mom_change": -15.0},
    ],
    "topMerchants": [
        {"merchant_normalized": "rent payment", "total_spend": 1500.0, "txn_count": 1},
        {"merchant_normalized": "whole foods market", "total_spend": 312.5, "txn_count": 8},
        {"merchant_normalized": "amazon", "total_spend": 245.0, "txn_count": 12},
        {"merchant_normalized": "con edison", "total_spend": 142.0, "txn_count": 1},
        {"merchant_normalized": "uber", "total_spend": 128.5, "txn_count": 15},
    ],
    "largestTransactions": [
        {"date": "2024-01-02", "merchant_name": "Chase Mortgage", "category": "Housing", "amount_abs": 2100.0},
        {"date": "2024-01-01", "merchant_name": "Rent Payment", "category": "Housing", "amount_abs": 1500.0},
        {"date": "2024-01-15", "merchant_name": "Delta Airlines", "category": "Transport", "amount_abs": 480.0},
        {"date": "2024-01-08", "merchant_name": "Best Buy", "category": "Other", "amount_abs": 350.0},
    ],
    "lastUpdated": datetime.utcnow().isoformat(),
}


@router.get(
    "/metrics/summary",
    response_model=MetricsSummaryResponse,
    summary="Get metrics summary",
)
async def get_metrics_summary(
    user_id: str = Query("demo_user"),
    _key: str = Depends(verify_api_key),
):
    try:
        record = dynamodb.get_metrics(user_id)
        if not record:
            raise ValueError("No metrics in DynamoDB")

        def _f(key: str, default=0.0):
            v = record.get(key, default)
            try:
                return float(v) if v is not None else default
            except (TypeError, ValueError):
                return default

        def _parse_json(key: str, default=None):
            v = record.get(key)
            if isinstance(v, str):
                try:
                    return json.loads(v)
                except Exception:
                    return default or []
            return v or default or []

        return MetricsSummaryResponse(
            user_id=user_id,
            date=str(record.get("date", "")),
            burn_rate=_f("monthlyBurnRate"),
            health_score=int(_f("healthScore")),
            anomaly_count=int(_f("anomalyCount")),
            high_anomaly_count=int(_f("highAnomalyCount")),
            mtd_spend=_f("mtdSpend"),
            last_month_spend=_f("lastMonthSpend"),
            mom_change_pct=_f("momChangePct"),
            avg_daily_spend=_f("avgDailySpend"),
            top_categories=_parse_json("topCategories"),
            top_merchants=_parse_json("topMerchants"),
            runway_days=int(_f("runwayDays")),
            last_updated=str(record.get("lastUpdated", "")),
        )

    except Exception as e:
        log.warning("DynamoDB unavailable, using mock metrics", error=str(e))
        m = MOCK_METRICS
        return MetricsSummaryResponse(
            user_id=user_id,
            date=m["date"],
            burn_rate=m["monthlyBurnRate"],
            health_score=m["healthScore"],
            anomaly_count=m["anomalyCount"],
            high_anomaly_count=m["highAnomalyCount"],
            mtd_spend=m["mtdSpend"],
            last_month_spend=m["lastMonthSpend"],
            mom_change_pct=m["momChangePct"],
            avg_daily_spend=m["avgDailySpend"],
            top_categories=m["topCategories"],
            top_merchants=m["topMerchants"],
            runway_days=m["runwayDays"],
            last_updated=m["lastUpdated"],
        )
