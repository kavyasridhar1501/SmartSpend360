"""SmartSpend360 — Transactions API Routes"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import verify_api_key
from app.core.logging import get_logger
from app.models.schemas import PageInfo, Transaction, TransactionListResponse
from app.services import athena, dynamodb

router = APIRouter()
log = get_logger("api.transactions")

# Fallback mock data when Athena is not available
MOCK_TRANSACTIONS = [
    {
        "transaction_id": f"txn_mock_{i:04d}",
        "user_id": "demo_user",
        "date": f"2024-{(i % 3 + 1):02d}-{(i % 28 + 1):02d}",
        "merchant_name": ["Whole Foods", "Starbucks", "Amazon", "Shell", "Netflix"][i % 5],
        "category": ["Food", "Food", "Other", "Transport", "Entertainment"][i % 5],
        "amount_abs": round(10.0 + (i * 7.3 % 200), 2),
        "is_debit": True,
        "is_weekend": i % 7 in (5, 6),
        "anomaly_score": round(-0.8 if i % 15 == 0 else 0.2 + (i % 10) * 0.05, 2),
        "anomaly_severity": "HIGH" if i % 15 == 0 else "NORMAL",
        "rolling_30d_mean": 85.0,
        "payment_channel": "online",
    }
    for i in range(1, 201)
]


@router.get(
    "/transactions",
    response_model=TransactionListResponse,
    summary="List transactions",
    description="Paginated list of transactions from Athena gold layer with optional filters.",
)
async def list_transactions(
    user_id: str = Query("demo_user"),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    category: Optional[str] = Query(None),
    anomaly_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _key: str = Depends(verify_api_key),
):
    try:
        result = athena.get_transactions(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            category=category,
            anomaly_only=anomaly_only,
            page=page,
            page_size=page_size,
        )

        txns = [Transaction(**t) for t in result["transactions"]]
        total = result["total_count"]

    except Exception as e:
        log.warning("Athena unavailable, using mock data", error=str(e))
        # Filter mock data
        filtered = MOCK_TRANSACTIONS
        if category:
            filtered = [t for t in filtered if t["category"] == category]
        if anomaly_only:
            filtered = [t for t in filtered if t.get("anomaly_severity") in ("HIGH", "MEDIUM")]
        if start_date:
            filtered = [t for t in filtered if t["date"] >= start_date]
        if end_date:
            filtered = [t for t in filtered if t["date"] <= end_date]

        total = len(filtered)
        offset = (page - 1) * page_size
        paged = filtered[offset : offset + page_size]
        txns = [Transaction(**t) for t in paged]

    total_pages = max(1, (total + page_size - 1) // page_size)
    return TransactionListResponse(
        transactions=txns,
        total_count=total,
        page_info=PageInfo(
            page=page,
            page_size=page_size,
            total_count=total,
            total_pages=total_pages,
        ),
    )
