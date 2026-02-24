"""SmartSpend360 — Pydantic Request/Response Models"""

from datetime import datetime
from typing import Any, List, Optional, Union
from decimal import Decimal

from pydantic import BaseModel, Field, validator


# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------
class PageInfo(BaseModel):
    page: int
    page_size: int
    total_count: int
    total_pages: int


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------
class Transaction(BaseModel):
    transaction_id: str
    user_id: str
    date: str
    merchant_name: str
    category: str
    amount_abs: float
    is_debit: bool
    is_weekend: Optional[bool] = None
    anomaly_score: Optional[float] = None
    anomaly_severity: Optional[str] = None
    rolling_30d_mean: Optional[float] = None
    payment_channel: Optional[str] = None


class TransactionListResponse(BaseModel):
    transactions: List[Transaction]
    total_count: int
    page_info: PageInfo


# ---------------------------------------------------------------------------
# Anomalies
# ---------------------------------------------------------------------------
class AnomalyRecord(BaseModel):
    alert_id: str
    user_id: str
    date: str
    merchant_name: Optional[str] = None
    category: Optional[str] = None
    anomaly_score: float
    severity: str  # HIGH | MEDIUM
    daily_total: Optional[float] = None
    status: str = "active"  # active | acknowledged
    anomaly_explanation: Optional[str] = None
    timestamp: Optional[str] = None


class AnomalyListResponse(BaseModel):
    anomalies: List[AnomalyRecord]
    total_count: int
    high_count: int
    medium_count: int


class AcknowledgeRequest(BaseModel):
    user_id: str
    note: str = ""


class AcknowledgeResponse(BaseModel):
    anomaly_id: str
    status: str
    acknowledged_at: str


# ---------------------------------------------------------------------------
# Forecast
# ---------------------------------------------------------------------------
class ForecastPoint(BaseModel):
    ds: str
    yhat: float
    yhat_lower: float
    yhat_upper: float
    yhat_lower_95: Optional[float] = None
    yhat_upper_95: Optional[float] = None
    trend: Optional[float] = None
    is_future: bool = False


class ForecastResponse(BaseModel):
    user_id: str
    run_date: str
    horizon_days: int
    runway_days: int
    projected_30d_spend: float
    mean_daily_spend: float
    health_score: Optional[float] = None
    forecast: List[ForecastPoint]


# ---------------------------------------------------------------------------
# Metrics Summary
# ---------------------------------------------------------------------------
class CategorySummary(BaseModel):
    category: str
    amount_abs: float
    percentage: float
    mom_change: Optional[float] = None


class MerchantSummary(BaseModel):
    merchant_normalized: str
    total_spend: float
    txn_count: int


class MetricsSummaryResponse(BaseModel):
    user_id: str
    date: str
    burn_rate: float
    health_score: int
    anomaly_count: int
    high_anomaly_count: int
    mtd_spend: float
    last_month_spend: float
    mom_change_pct: float
    avg_daily_spend: float
    top_categories: List[dict]
    top_merchants: List[dict]
    runway_days: int
    last_updated: str


# ---------------------------------------------------------------------------
# Pipeline Status
# ---------------------------------------------------------------------------
class PipelineStageStatus(BaseModel):
    stage: str
    status: str  # success | failed | running | pending
    last_run_time: Optional[str] = None
    records_processed: int = 0
    duration_seconds: Optional[float] = None
    error_count: int = 0
    details: Optional[str] = None


class PipelineStatusResponse(BaseModel):
    stages: List[PipelineStageStatus]
    overall_status: str
    last_full_run: Optional[str] = None


class TriggerPipelineResponse(BaseModel):
    dag_run_id: str
    status: str
    triggered_at: str


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------
class CreateAlertRequest(BaseModel):
    user_id: str
    alert_type: str = Field(..., description="daily_spend | single_transaction | category_budget")
    threshold: float = Field(..., gt=0)
    category: Optional[str] = None
    channel: str = Field("dashboard", description="dashboard | email")
    enabled: bool = True


class AlertRecord(BaseModel):
    user_id: str
    alert_id: str
    alert_type: str
    threshold: float
    category: Optional[str] = None
    channel: str
    enabled: bool
    created_at: str
    triggered_count: int = 0
    last_triggered: Optional[str] = None


class AlertListResponse(BaseModel):
    alerts: List[AlertRecord]
    recent_events: List[dict]


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float
    aws_connected: bool
    environment: str
