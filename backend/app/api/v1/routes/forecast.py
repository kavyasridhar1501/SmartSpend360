"""SmartSpend360 — Forecast API Routes"""

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from app.core.auth import verify_api_key
from app.core.logging import get_logger
from app.models.schemas import ForecastPoint, ForecastResponse
from app.services import dynamodb

router = APIRouter()
log = get_logger("api.forecast")


def _generate_mock_forecast(horizon: int = 30) -> dict:
    """Generate realistic mock forecast data."""
    import math
    from datetime import datetime, timedelta

    base_spend = 95.0
    points = []
    today = datetime.utcnow()

    # 60 days historical + horizon future
    for i in range(-60, horizon):
        date = today + timedelta(days=i)
        is_future = i >= 0
        day_of_week = date.weekday()
        is_weekend = day_of_week >= 5

        seasonal = 10 * math.sin(2 * math.pi * i / 7)  # Weekly seasonality
        trend = -0.1 * i  # Slight downward trend (good!)
        noise = 5 * math.sin(i * 0.7)

        yhat = max(0, base_spend + seasonal + trend + noise)
        if is_weekend:
            yhat *= 1.3

        band_80 = 20 + abs(i) * 0.3 if is_future else 10
        band_95 = 35 + abs(i) * 0.5 if is_future else 15

        points.append(
            {
                "ds": date.strftime("%Y-%m-%d"),
                "yhat": round(yhat, 2),
                "yhat_lower": round(max(0, yhat - band_80), 2),
                "yhat_upper": round(yhat + band_80, 2),
                "yhat_lower_95": round(max(0, yhat - band_95), 2),
                "yhat_upper_95": round(yhat + band_95, 2),
                "trend": round(base_spend + trend, 2),
                "is_future": is_future,
            }
        )

    projected_30d = sum(p["yhat"] for p in points if p["is_future"])

    return {
        "user_id": "demo_user",
        "run_date": today.strftime("%Y-%m-%d"),
        "horizon_days": horizon,
        "runway_days": 45,
        "projected_30d_spend": round(projected_30d, 2),
        "mean_daily_spend": round(base_spend, 2),
        "health_score": 72,
        "forecast": points,
    }


@router.get(
    "/forecast",
    response_model=ForecastResponse,
    summary="Get cash flow forecast",
)
async def get_forecast(
    user_id: str = Query("demo_user"),
    horizon_days: int = Query(30, ge=7, le=90),
    _key: str = Depends(verify_api_key),
):
    try:
        record = dynamodb.get_forecast(user_id)
        if not record:
            raise ValueError("No forecast data in DynamoDB")

        forecast_json = record.get("forecastJson", "[]")
        forecast_points = json.loads(forecast_json) if isinstance(forecast_json, str) else forecast_json

        # Limit to requested horizon
        future_points = [p for p in forecast_points if p.get("is_future")][:horizon_days]
        historical_points = [p for p in forecast_points if not p.get("is_future")]

        all_points = [ForecastPoint(**p) for p in (historical_points + future_points)]

        return ForecastResponse(
            user_id=user_id,
            run_date=record.get("forecastDate", ""),
            horizon_days=horizon_days,
            runway_days=int(record.get("runwayDays", 30)),
            projected_30d_spend=float(record.get("projected30dSpend", 0)),
            mean_daily_spend=float(record.get("meanDailySpend", 0)),
            forecast=all_points,
        )

    except Exception as e:
        log.warning("DynamoDB unavailable, using mock forecast", error=str(e))
        mock = _generate_mock_forecast(horizon_days)
        return ForecastResponse(
            user_id=mock["user_id"],
            run_date=mock["run_date"],
            horizon_days=mock["horizon_days"],
            runway_days=mock["runway_days"],
            projected_30d_spend=mock["projected_30d_spend"],
            mean_daily_spend=mock["mean_daily_spend"],
            health_score=mock.get("health_score"),
            forecast=[ForecastPoint(**p) for p in mock["forecast"]],
        )
