#!/usr/bin/env python3
"""
SmartSpend360 — Mock Data Generator
Generates 90 days of realistic transaction data and uploads to S3 + DynamoDB.
Run once after setup to make all dashboard pages functional with zero real API keys.

Usage:
    python data/seed/generate_mock_data.py
    python data/seed/generate_mock_data.py --dry-run  (saves locally, no AWS)
"""

import argparse
import json
import logging
import math
import os
import pickle
import random
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

random.seed(42)

# ---------------------------------------------------------------------------
# Merchant profiles: (name, category, min_amount, max_amount, frequency_weight)
# ---------------------------------------------------------------------------
MERCHANTS = [
    # Housing
    ("Rent Payment",        "Housing",       1500.0, 1500.0, 1),
    ("Con Edison",          "Housing",        80.0,  160.0,  2),
    ("Internet Bill",       "Housing",        45.0,   75.0,  1),
    # Food
    ("Whole Foods Market",  "Food",           35.0,  175.0,  15),
    ("Trader Joe's",        "Food",           25.0,   90.0,  12),
    ("Starbucks",           "Food",            4.5,   12.0,  20),
    ("Chipotle",            "Food",           10.0,   22.0,  10),
    ("Sweetgreen",          "Food",           12.0,   18.0,   8),
    ("Uber Eats",           "Food",           18.0,   55.0,   6),
    ("DoorDash",            "Food",           20.0,   60.0,   5),
    # Transport
    ("Uber",                "Transport",       8.0,   45.0,  18),
    ("Lyft",                "Transport",       7.0,   40.0,  10),
    ("Shell Gas Station",   "Transport",      35.0,   80.0,   4),
    ("Metro Card",          "Transport",      33.0,   33.0,   3),
    # Entertainment
    ("Netflix",             "Entertainment",  15.5,   15.5,   1),
    ("Spotify",             "Entertainment",   9.99,   9.99,  1),
    ("AMC Theaters",        "Entertainment",  15.0,   45.0,   4),
    ("Steam Games",         "Entertainment",   5.0,   60.0,   3),
    # Healthcare
    ("CVS Pharmacy",        "Healthcare",     12.0,   85.0,   5),
    ("Planet Fitness",      "Healthcare",     10.0,   25.0,   2),
    ("Walgreens",           "Healthcare",     10.0,   60.0,   4),
    # Shopping
    ("Amazon",              "Other",          12.0,  250.0,  15),
    ("Target",              "Other",          25.0,  150.0,   8),
    ("Apple App Store",     "Other",           0.99,  14.99,  5),
    # Income
    ("Payroll Direct Dep.", "Income",       3500.0, 3500.0,  2),  # Bi-weekly
    # Transfer
    ("Venmo Transfer",      "Transfer",      20.0,  200.0,   4),
    ("ATM Withdrawal",      "Transfer",     100.0,  300.0,   3),
]

MERCHANT_WEIGHTS = [m[4] for m in MERCHANTS]

USER_ID = "demo_user"
DAYS = 90
ANOMALY_DAYS_COUNT = 10  # Days with injected anomalies


def pick_merchants_for_day(date: datetime) -> list:
    """Pick 3-8 merchants for a day, weighted by frequency."""
    is_weekend = date.weekday() >= 5
    count = random.randint(4, 9) if is_weekend else random.randint(3, 7)

    # Remove income from daily random picks (handle separately)
    eligible = [(i, m) for i, m in enumerate(MERCHANTS) if m[1] != "Income" and m[1] != "Housing"]
    weights = [MERCHANT_WEIGHTS[i] for i, _ in eligible]

    selected_indices = random.choices(range(len(eligible)), weights=weights, k=count)
    return [eligible[i][1] for i in selected_indices]


def generate_transactions(days: int = 90) -> list:
    now = datetime.utcnow()
    transactions = []

    # Pick anomaly days
    anomaly_day_indices = sorted(random.sample(range(5, days - 2), ANOMALY_DAYS_COUNT))
    log.info("Anomaly days: %s", anomaly_day_indices)

    for day_offset in range(days, 0, -1):
        txn_date = now - timedelta(days=day_offset)
        is_anomaly_day = day_offset in anomaly_day_indices
        is_weekend = txn_date.weekday() >= 5

        # Bi-weekly payroll on alternating Fridays
        if txn_date.weekday() == 4 and day_offset % 14 < 7:
            transactions.append(_make_txn(txn_date, MERCHANTS[-3], anomaly=False))  # Payroll

        # Monthly rent on 1st
        if txn_date.day == 1:
            transactions.append(_make_txn(txn_date, MERCHANTS[0], anomaly=False))  # Rent

        # Monthly utilities on 15th
        if txn_date.day == 15:
            transactions.append(_make_txn(txn_date, MERCHANTS[1], anomaly=False))  # Utilities

        # Daily transactions
        merchants = pick_merchants_for_day(txn_date)
        for merchant_info in merchants:
            is_anomaly = is_anomaly_day and random.random() < 0.4
            transactions.append(_make_txn(txn_date, merchant_info, anomaly=is_anomaly))

    log.info("Generated %d transactions", len(transactions))
    return transactions


def _make_txn(date: datetime, merchant: tuple, anomaly: bool) -> dict:
    name, category, min_amt, max_amt, _ = merchant
    amount = round(random.uniform(min_amt, max_amt), 2)

    if anomaly:
        # Inject anomaly: 5-15x normal amount
        amount = round(amount * random.uniform(5, 15), 2)

    # Income is negative (credit in Plaid convention)
    if category == "Income":
        amount = -amount

    return {
        "transaction_id": f"txn_{uuid.uuid4().hex[:16]}",
        "account_id": "acc_demo_checking",
        "user_id": USER_ID,
        "amount": amount,
        "amount_abs": abs(amount),
        "is_debit": amount > 0,
        "date": date.strftime("%Y-%m-%d"),
        "merchant_name": name,
        "merchant_normalized": name.lower().strip(),
        "category": category,
        "category_id": f"cat_{category.lower()}",
        "payment_channel": random.choice(["online", "in store", "other"]),
        "pending": False,
        "iso_currency_code": "USD",
        "is_weekend": date.weekday() >= 5,
        "day_of_week": date.isoweekday(),
        "week_of_month": math.ceil(date.day / 7),
        "month": date.month,
        "year": date.year,
        "rolling_7d_spend": None,
        "rolling_30d_spend": None,
        "rolling_30d_mean": None,
        "rolling_30d_std": None,
        "ingested_at": datetime.utcnow().isoformat(),
        "_is_anomaly_injected": anomaly,
    }


def compute_rolling_windows(transactions: list) -> list:
    """Add rolling window aggregates to each transaction."""
    user_debits = sorted(
        [t for t in transactions if t["is_debit"]],
        key=lambda t: t["date"]
    )

    # Index by date
    date_amounts = {}
    for t in user_debits:
        date_amounts.setdefault(t["date"], []).append(t["amount_abs"])

    all_dates = sorted(date_amounts.keys())

    def get_window_sum(date_str: str, days: int) -> float:
        end = datetime.strptime(date_str, "%Y-%m-%d")
        total = 0.0
        for d in all_dates:
            d_dt = datetime.strptime(d, "%Y-%m-%d")
            if end - timedelta(days=days) <= d_dt <= end:
                total += sum(date_amounts[d])
        return round(total, 2)

    def get_window_stats(date_str: str, days: int):
        end = datetime.strptime(date_str, "%Y-%m-%d")
        amounts = []
        for d in all_dates:
            d_dt = datetime.strptime(d, "%Y-%m-%d")
            if end - timedelta(days=days) <= d_dt <= end:
                amounts.extend(date_amounts[d])
        if not amounts:
            return 0.0, 0.0
        mean = sum(amounts) / len(amounts)
        variance = sum((x - mean) ** 2 for x in amounts) / len(amounts)
        return round(mean, 2), round(variance ** 0.5, 2)

    for t in transactions:
        if t["is_debit"]:
            t["rolling_7d_spend"] = get_window_sum(t["date"], 7)
            t["rolling_30d_spend"] = get_window_sum(t["date"], 30)
            mean_30, std_30 = get_window_stats(t["date"], 30)
            t["rolling_30d_mean"] = mean_30
            t["rolling_30d_std"] = std_30

    return transactions


def detect_anomalies(transactions: list) -> list:
    """Simple z-score based anomaly detection (mimics Isolation Forest output)."""
    debits = [t for t in transactions if t["is_debit"] and t["rolling_30d_mean"]]

    for t in transactions:
        if not t["is_debit"] or not t.get("rolling_30d_mean"):
            t["anomaly_score"] = 0.0
            t["anomaly_severity"] = "NORMAL"
            t["is_anomaly"] = False
            continue

        mean = t["rolling_30d_mean"] or 1
        std = t["rolling_30d_std"] or 1
        z_score = (t["amount_abs"] - mean) / (std + 0.01)

        # Convert z-score to anomaly score range (-1 to 1)
        score = max(-1.0, min(1.0, -z_score / 4))

        t["anomaly_score"] = round(score, 3)
        if score < -0.5 or t.get("_is_anomaly_injected"):
            t["anomaly_severity"] = "HIGH"
            t["is_anomaly"] = True
        elif score < -0.3:
            t["anomaly_severity"] = "MEDIUM"
            t["is_anomaly"] = True
        else:
            t["anomaly_severity"] = "NORMAL"
            t["is_anomaly"] = False

    anomaly_count = sum(1 for t in transactions if t.get("is_anomaly"))
    log.info("Detected %d anomalies", anomaly_count)
    return transactions


def generate_forecast(transactions: list) -> dict:
    """Generate a simple mock forecast (Prophet-like output)."""
    now = datetime.utcnow()

    # Daily spend history
    daily = {}
    for t in transactions:
        if t["is_debit"]:
            daily[t["date"]] = daily.get(t["date"], 0) + t["amount_abs"]

    all_amounts = list(daily.values())
    mean_spend = sum(all_amounts) / len(all_amounts) if all_amounts else 100
    std_spend = (sum((x - mean_spend) ** 2 for x in all_amounts) / len(all_amounts)) ** 0.5 if all_amounts else 20

    forecast_points = []

    # Historical part (last 90 days)
    for d_str, amount in sorted(daily.items()):
        d = datetime.strptime(d_str, "%Y-%m-%d")
        is_weekend = d.weekday() >= 5
        seasonal = std_spend * 0.3 * math.sin(2 * math.pi * d.toordinal() / 7)

        forecast_points.append({
            "ds": d_str,
            "yhat": round(mean_spend + seasonal, 2),
            "yhat_lower": round(max(0, mean_spend + seasonal - std_spend * 1.3), 2),
            "yhat_upper": round(mean_spend + seasonal + std_spend * 1.3, 2),
            "yhat_lower_95": round(max(0, mean_spend + seasonal - std_spend * 2.0), 2),
            "yhat_upper_95": round(mean_spend + seasonal + std_spend * 2.0, 2),
            "trend": round(mean_spend * (1 - 0.001 * (now - d).days), 2),
            "is_future": False,
        })

    # Future 30 days
    DAILY_INCOME = 3500.0 / 15  # Bi-weekly $3500 payroll
    HORIZON = 30
    cumulative_balance = 0

    runway_days = HORIZON
    projected_30d = 0

    for i in range(HORIZON):
        future_date = now + timedelta(days=i + 1)
        is_weekend = future_date.weekday() >= 5
        seasonal = std_spend * 0.3 * math.sin(2 * math.pi * future_date.toordinal() / 7)
        uncertainty = std_spend * 0.1 * (i / HORIZON)

        yhat = max(0, mean_spend + seasonal + random.gauss(0, std_spend * 0.05))
        projected_30d += yhat
        cumulative_balance += DAILY_INCOME - yhat

        if cumulative_balance < 0 and runway_days == HORIZON:
            runway_days = i

        forecast_points.append({
            "ds": future_date.strftime("%Y-%m-%d"),
            "yhat": round(yhat, 2),
            "yhat_lower": round(max(0, yhat - std_spend * 1.3 - uncertainty), 2),
            "yhat_upper": round(yhat + std_spend * 1.3 + uncertainty, 2),
            "yhat_lower_95": round(max(0, yhat - std_spend * 2.0 - uncertainty * 1.5), 2),
            "yhat_upper_95": round(yhat + std_spend * 2.0 + uncertainty * 1.5, 2),
            "trend": round(mean_spend * (1 - 0.002 * i), 2),
            "is_future": True,
        })

    return {
        "user_id": USER_ID,
        "run_date": now.strftime("%Y-%m-%d"),
        "horizon_days": HORIZON,
        "runway_days": runway_days,
        "projected_30d_spend": round(projected_30d, 2),
        "mean_daily_spend": round(mean_spend, 2),
        "forecast": forecast_points,
    }


def compute_metrics(transactions: list, forecast: dict) -> dict:
    """Compute all dashboard metrics."""
    now = datetime.utcnow()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_start = (start_of_month - timedelta(days=1)).replace(day=1)
    last_month_end = start_of_month - timedelta(days=1)
    thirty_days_ago = now - timedelta(days=30)

    debits = [t for t in transactions if t["is_debit"]]

    mtd = [t for t in debits if t["date"] >= start_of_month.strftime("%Y-%m-%d")]
    mtd_spend = sum(t["amount_abs"] for t in mtd)

    last_month = [
        t for t in debits
        if last_month_start.strftime("%Y-%m-%d") <= t["date"] <= last_month_end.strftime("%Y-%m-%d")
    ]
    last_month_spend = sum(t["amount_abs"] for t in last_month)

    recent_30d = [t for t in debits if t["date"] >= thirty_days_ago.strftime("%Y-%m-%d")]
    daily_totals = {}
    for t in recent_30d:
        daily_totals[t["date"]] = daily_totals.get(t["date"], 0) + t["amount_abs"]

    avg_daily = sum(daily_totals.values()) / len(daily_totals) if daily_totals else 0
    burn_rate = avg_daily * 30

    mom_change = ((mtd_spend - last_month_spend) / last_month_spend * 100) if last_month_spend > 0 else 0

    # Category breakdown
    cat_spend: dict[str, float] = {}
    for t in mtd:
        cat_spend[t["category"]] = cat_spend.get(t["category"], 0) + t["amount_abs"]
    total_cat = sum(cat_spend.values())

    top_categories = sorted(
        [{"category": k, "amount_abs": round(v, 2), "percentage": round(v / total_cat * 100, 1), "mom_change": 0.0}
         for k, v in cat_spend.items()],
        key=lambda x: x["amount_abs"], reverse=True,
    )[:7]

    # Top merchants
    merch_spend: dict[str, dict] = {}
    for t in recent_30d:
        k = t["merchant_normalized"]
        merch_spend.setdefault(k, {"total_spend": 0.0, "txn_count": 0})
        merch_spend[k]["total_spend"] += t["amount_abs"]
        merch_spend[k]["txn_count"] += 1

    top_merchants = sorted(
        [{"merchant_normalized": k, "total_spend": round(v["total_spend"], 2), "txn_count": v["txn_count"]}
         for k, v in merch_spend.items()],
        key=lambda x: x["total_spend"], reverse=True,
    )[:5]

    anomaly_count = sum(1 for t in transactions if t.get("is_anomaly"))
    high_count = sum(1 for t in transactions if t.get("anomaly_severity") == "HIGH")

    # Health score
    anomaly_rate = anomaly_count / len(transactions) if transactions else 0
    health_score = max(0, min(100, int(
        40 * (1 - min(1.0, avg_daily / 200)) +  # stability
        30 * (1 - min(1.0, anomaly_rate / 0.1)) +  # anomaly rate
        30 * 0.7  # spend trend (slightly positive default)
    )))

    return {
        "userId": USER_ID,
        "date": now.strftime("%Y-%m-%d"),
        "mtdSpend": round(mtd_spend, 2),
        "mtdTransactionCount": len(mtd),
        "lastMonthSpend": round(last_month_spend, 2),
        "momChangePct": round(mom_change, 1),
        "monthlyBurnRate": round(burn_rate, 2),
        "avgDailySpend": round(avg_daily, 2),
        "anomalyCount": anomaly_count,
        "highAnomalyCount": high_count,
        "anomalyRate": round(anomaly_rate, 4),
        "healthScore": health_score,
        "runwayDays": forecast.get("runway_days", 30),
        "projected30dSpend": forecast.get("projected_30d_spend", burn_rate),
        "topCategories": json.dumps(top_categories),
        "topMerchants": json.dumps(top_merchants),
        "lastUpdated": now.isoformat(),
    }


def upload_to_s3(s3_client, bucket: str, transactions: list, forecast: dict):
    now = datetime.utcnow()
    date_str = now.strftime("%Y-%m-%d")

    # Upload transactions as JSON to bronze
    log.info("Uploading bronze transactions to S3...")
    s3_client.put_object(
        Bucket=bucket,
        Key=f"bronze/transactions/{now.year}/{now.month:02d}/{now.day:02d}/{now.hour:02d}/raw.json",
        Body=json.dumps({"ingested_at": now.isoformat(), "transactions": transactions, "record_count": len(transactions)}).encode(),
        ContentType="application/json",
    )

    # Upload as Parquet to silver (requires pyarrow)
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq

        clean_txns = [{k: v for k, v in t.items() if not k.startswith("_")} for t in transactions]
        table = pa.Table.from_pylist(clean_txns)
        buf = BytesIO()
        pq.write_table(table, buf, compression="snappy")
        buf.seek(0)
        s3_client.put_object(
            Bucket=bucket,
            Key=f"silver/transactions/{date_str}.parquet",
            Body=buf.read(),
            ContentType="application/octet-stream",
        )
        log.info("Silver Parquet uploaded")
    except Exception as e:
        log.warning("Could not write Parquet (pyarrow needed): %s", e)

    # Upload gold transactions as JSON
    gold_txns = [{k: v for k, v in t.items() if not k.startswith("_")} for t in transactions]
    s3_client.put_object(
        Bucket=bucket,
        Key=f"gold/transactions/{date_str}.json",
        Body=json.dumps(gold_txns).encode(),
        ContentType="application/json",
    )

    # Upload forecast
    s3_client.put_object(
        Bucket=bucket,
        Key=f"gold/forecasts/{date_str}.json",
        Body=json.dumps(forecast).encode(),
        ContentType="application/json",
    )

    log.info("S3 upload complete")


def _to_decimal(obj):
    """Recursively convert floats to Decimal for DynamoDB compatibility."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_decimal(v) for v in obj]
    return obj


def upload_to_dynamodb(ddb_resource, transactions: list, forecast: dict, metrics: dict):
    now = datetime.utcnow()

    # ---- Metrics ----
    table = ddb_resource.Table("ss360-metrics")
    table.put_item(Item=_to_decimal(metrics))
    log.info("Metrics saved to DynamoDB")

    # ---- Forecast ----
    table = ddb_resource.Table("ss360-forecasts")
    table.put_item(
        Item=_to_decimal({
            "userId": USER_ID,
            "forecastDate": metrics["date"],
            "runwayDays": forecast["runway_days"],
            "projected30dSpend": int(forecast["projected_30d_spend"] * 100) / 100,
            "meanDailySpend": int(forecast["mean_daily_spend"] * 100) / 100,
            "horizonDays": forecast["horizon_days"],
            "forecastS3Key": f"gold/forecasts/{metrics['date']}.json",
            "timestamp": now.isoformat(),
            "forecastJson": json.dumps(forecast["forecast"]),
        })
    )
    log.info("Forecast saved to DynamoDB")

    # ---- Anomaly alerts ----
    alert_table = ddb_resource.Table("ss360-alerts")
    anomalies = [t for t in transactions if t.get("is_anomaly")][:20]

    for t in anomalies:
        alert_table.put_item(
            Item={
                "userId": USER_ID,
                "alertId": f"anomaly_{t['transaction_id'][-8:]}",
                "alertType": "anomaly_detected",
                "date": t["date"],
                "merchantName": t["merchant_name"],
                "category": t["category"],
                "anomalyScore": str(round(t.get("anomaly_score", -0.6), 3)),
                "severity": t.get("anomaly_severity", "HIGH"),
                "dailyTotal": str(round(t["amount_abs"], 2)),
                "status": "active",
                "timestamp": f"{t['date']}T12:00:00",
            }
        )
    log.info("Saved %d anomaly alerts to DynamoDB", len(anomalies))

    # ---- Pipeline run ----
    pipeline_table = ddb_resource.Table("ss360-pipeline-runs")
    stages = [
        "ingest_transactions", "ingest_market_data", "ingest_fx_rates",
        "ml_01_silver_transforms", "ml_02_feature_engineering",
        "ml_03_anomaly_detection", "ml_04_cash_flow_forecast", "ml_05_gold_metrics",
    ]
    for i, stage in enumerate(stages):
        pipeline_table.put_item(
            Item={
                "stage": stage,
                "runId": f"run_{now.strftime('%Y%m%d%H%M%S')}_{i:02d}",
                "status": "success",
                "recordsProcessed": len(transactions) if "ingest" in stage or "silver" in stage else 0,
                "timestamp": (now - timedelta(minutes=30 - i * 4)).isoformat(),
                "details": json.dumps({"simulated": True}),
            }
        )
    log.info("Pipeline run records saved to DynamoDB")


def main():
    parser = argparse.ArgumentParser(description="Generate SmartSpend360 mock data")
    parser.add_argument("--dry-run", action="store_true", help="Save locally, skip AWS uploads")
    parser.add_argument("--days", type=int, default=90, help="Days of history to generate")
    parser.add_argument("--output-dir", default="data/seed/output", help="Local output directory")
    args = parser.parse_args()

    log.info("=== SmartSpend360 Mock Data Generator ===")
    log.info("Days: %d | Dry run: %s", args.days, args.dry_run)

    # Step 1: Generate transactions
    log.info("Step 1/4: Generating transactions...")
    transactions = generate_transactions(args.days)

    # Step 2: Compute rolling windows
    log.info("Step 2/4: Computing rolling windows...")
    transactions = compute_rolling_windows(transactions)

    # Step 3: Detect anomalies
    log.info("Step 3/4: Running anomaly detection...")
    transactions = detect_anomalies(transactions)

    # Step 4: Generate forecast
    log.info("Step 4a: Generating forecast...")
    forecast = generate_forecast(transactions)
    metrics = compute_metrics(transactions, forecast)

    log.info("Summary:")
    log.info("  Transactions:  %d", len(transactions))
    log.info("  Anomalies:     %d", sum(1 for t in transactions if t.get("is_anomaly")))
    log.info("  MTD Spend:     $%.2f", metrics["mtdSpend"])
    log.info("  Burn Rate:     $%.2f/month", metrics["monthlyBurnRate"])
    log.info("  Health Score:  %d/100", metrics["healthScore"])
    log.info("  Runway:        %d days", forecast["runway_days"])

    if args.dry_run:
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "transactions.json").write_text(json.dumps(transactions, indent=2))
        (out_dir / "forecast.json").write_text(json.dumps(forecast, indent=2))
        (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
        log.info("Dry run: output saved to %s/", out_dir)
        return

    # Upload to AWS
    import boto3
    from boto3.dynamodb.types import TypeSerializer

    region = os.getenv("AWS_REGION", "us-east-1")
    bucket = os.getenv("S3_BUCKET_NAME", "smartspend360-datalake")

    boto_kwargs = {"region_name": region}
    if os.getenv("AWS_ACCESS_KEY_ID"):
        boto_kwargs["aws_access_key_id"] = os.environ["AWS_ACCESS_KEY_ID"]
        boto_kwargs["aws_secret_access_key"] = os.environ["AWS_SECRET_ACCESS_KEY"]

    s3 = boto3.client("s3", **boto_kwargs)
    ddb = boto3.resource("dynamodb", **boto_kwargs)

    log.info("Step 4b: Uploading to S3 (bucket: %s)...", bucket)
    upload_to_s3(s3, bucket, transactions, forecast)

    log.info("Step 4c: Uploading to DynamoDB...")
    upload_to_dynamodb(ddb, transactions, forecast, metrics)

    log.info("")
    log.info("=== MOCK DATA GENERATION COMPLETE ===")
    log.info("All dashboard pages are now populated with demo data.")
    log.info("Start the backend: cd backend && uvicorn app.main:app --reload")
    log.info("Start the frontend: cd frontend && npm run dev")


if __name__ == "__main__":
    main()
