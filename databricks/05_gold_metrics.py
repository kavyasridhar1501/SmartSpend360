# Databricks notebook source
# SmartSpend360 — Notebook 05: Gold Metrics
# Computes final business metrics → DynamoDB + Athena

# COMMAND ----------

import json
import os
from datetime import datetime, timedelta

import boto3
import numpy as np
import pandas as pd

S3_BUCKET = dbutils.widgets.get("s3_bucket") if "dbutils" in dir() else os.getenv("S3_BUCKET_NAME", "smartspend360-datalake")
RUN_DATE = dbutils.widgets.get("run_date") if "dbutils" in dir() else datetime.utcnow().strftime("%Y-%m-%d")

# COMMAND ----------

try:
    spark
except NameError:
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.appName("SmartSpend360-GoldMetrics").getOrCreate()

# COMMAND ----------
# Load all gold data
gold_path = f"s3a://{S3_BUCKET}/gold/transactions/"
df_txns = spark.read.format("delta").load(gold_path).toPandas()
df_debits = df_txns[df_txns["is_debit"]].copy()

# Date calculations
now = datetime.utcnow()
today = now.strftime("%Y-%m-%d")
start_of_month = now.replace(day=1).strftime("%Y-%m-%d")
last_month_start = (now.replace(day=1) - timedelta(days=1)).replace(day=1).strftime("%Y-%m-%d")
last_month_end = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m-%d")
thirty_days_ago = (now - timedelta(days=30)).strftime("%Y-%m-%d")

USER_ID = "demo_user"

# COMMAND ----------
# MTD Spend (month-to-date)
df_mtd = df_debits[df_debits["date"] >= start_of_month]
mtd_spend = float(df_mtd["amount_abs"].sum())
mtd_count = len(df_mtd)
print(f"MTD Spend: ${mtd_spend:.2f} ({mtd_count} transactions)")

# COMMAND ----------
# Last month spend for MoM comparison
df_last_month = df_debits[
    (df_debits["date"] >= last_month_start) & (df_debits["date"] <= last_month_end)
]
last_month_spend = float(df_last_month["amount_abs"].sum())
mom_change_pct = (
    ((mtd_spend - last_month_spend) / last_month_spend * 100)
    if last_month_spend > 0 else 0
)
print(f"Last Month Spend: ${last_month_spend:.2f}")
print(f"MoM Change: {mom_change_pct:+.1f}%")

# COMMAND ----------
# Monthly burn rate (30d avg daily spend × 30)
df_30d = df_debits[df_debits["date"] >= thirty_days_ago]
daily_spend_30d = (
    df_30d.groupby("date")["amount_abs"].sum().reset_index()
)
avg_daily_spend = float(daily_spend_30d["amount_abs"].mean()) if len(daily_spend_30d) > 0 else 0
monthly_burn_rate = avg_daily_spend * 30
print(f"Avg Daily Spend (30d): ${avg_daily_spend:.2f}")
print(f"Monthly Burn Rate: ${monthly_burn_rate:.2f}")

# COMMAND ----------
# Category breakdown (MTD)
category_spend = (
    df_mtd.groupby("category")["amount_abs"]
    .sum()
    .sort_values(ascending=False)
    .reset_index()
)
total_category_spend = category_spend["amount_abs"].sum()
category_spend["percentage"] = (category_spend["amount_abs"] / total_category_spend * 100).round(1)

print("\nCategory Breakdown (MTD):")
print(category_spend.to_string(index=False))

# Prior month categories
category_spend_prior = (
    df_last_month.groupby("category")["amount_abs"]
    .sum()
    .reset_index()
    .rename(columns={"amount_abs": "prior_amount"})
)
category_comparison = category_spend.merge(category_spend_prior, on="category", how="left").fillna(0)
category_comparison["mom_change"] = (
    (category_comparison["amount_abs"] - category_comparison["prior_amount"])
    / (category_comparison["prior_amount"] + 0.01) * 100
).round(1)

# COMMAND ----------
# Top 5 merchants by spend (last 30 days)
top_merchants = (
    df_30d.groupby("merchant_normalized")
    .agg(total_spend=("amount_abs", "sum"), txn_count=("transaction_id", "count"))
    .sort_values("total_spend", ascending=False)
    .head(5)
    .reset_index()
)
print("\nTop 5 Merchants (30d):")
print(top_merchants.to_string(index=False))

# COMMAND ----------
# Largest single transactions (all time)
largest_txns = (
    df_debits.nlargest(10, "amount_abs")
    [["date", "merchant_name", "category", "amount_abs"]]
    .reset_index(drop=True)
)
print("\nLargest Transactions:")
print(largest_txns.to_string(index=False))

# COMMAND ----------
# Load anomaly data to compute anomaly metrics
try:
    anomaly_path = f"s3a://{S3_BUCKET}/gold/anomalies/{RUN_DATE}/"
    df_anomalies = spark.read.parquet(anomaly_path).toPandas()
    anomaly_count = int((df_anomalies["is_anomaly"] == True).sum()) if "is_anomaly" in df_anomalies.columns else 0
    high_anomaly_count = int((df_anomalies["anomaly_severity"] == "HIGH").sum()) if "anomaly_severity" in df_anomalies.columns else 0
    anomaly_rate = anomaly_count / len(df_anomalies) if len(df_anomalies) > 0 else 0
except Exception as e:
    print(f"Could not load anomaly data: {e}")
    anomaly_count = 0
    high_anomaly_count = 0
    anomaly_rate = 0.0

# COMMAND ----------
# Load forecast data for runway and health score
try:
    s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
    obj = s3.get_object(Bucket=S3_BUCKET, Key=f"gold/forecasts/{RUN_DATE}.json")
    forecast_data = json.loads(obj["Body"].read())
    runway_days = forecast_data.get("runway_days", 30)
    projected_30d = forecast_data.get("projected_30d_spend", monthly_burn_rate)
    forecast_variance = float(np.std([r["yhat"] for r in forecast_data.get("forecast", [])[-30:]]))
except Exception as e:
    print(f"Could not load forecast: {e}")
    runway_days = 30
    projected_30d = monthly_burn_rate
    forecast_variance = 0.0

# COMMAND ----------
# Cash Flow Health Score (0-100)
# 40 pts: forecast stability (lower variance = higher score)
max_variance = avg_daily_spend * 0.5 if avg_daily_spend > 0 else 100
stability_score = max(0, 40 * (1 - min(forecast_variance / (max_variance + 0.01), 1)))

# 30 pts: anomaly rate (fewer anomalies = better score)
anomaly_score_pts = max(0, 30 * (1 - min(anomaly_rate / 0.1, 1)))

# 30 pts: spend trend (decreasing = better)
if len(daily_spend_30d) >= 14:
    first_half = daily_spend_30d["amount_abs"].iloc[:len(daily_spend_30d)//2].mean()
    second_half = daily_spend_30d["amount_abs"].iloc[len(daily_spend_30d)//2:].mean()
    trend_ratio = first_half / (second_half + 0.01)
    trend_score = max(0, min(30, 30 * (trend_ratio - 0.5) / 0.5))
else:
    trend_score = 15  # Neutral

health_score = round(stability_score + anomaly_score_pts + trend_score)
health_score = max(0, min(100, health_score))

print(f"\n=== HEALTH SCORE: {health_score}/100 ===")
print(f"  Stability score: {stability_score:.1f}/40")
print(f"  Anomaly score:   {anomaly_score_pts:.1f}/30")
print(f"  Trend score:     {trend_score:.1f}/30")

# COMMAND ----------
# Build final metrics dict
metrics = {
    "userId": USER_ID,
    "date": today,
    "mtdSpend": round(mtd_spend, 2),
    "mtdTransactionCount": mtd_count,
    "lastMonthSpend": round(last_month_spend, 2),
    "momChangePct": round(mom_change_pct, 1),
    "monthlyBurnRate": round(monthly_burn_rate, 2),
    "avgDailySpend": round(avg_daily_spend, 2),
    "anomalyCount": anomaly_count,
    "highAnomalyCount": high_anomaly_count,
    "anomalyRate": round(anomaly_rate, 4),
    "healthScore": health_score,
    "runwayDays": runway_days,
    "projected30dSpend": round(float(projected_30d), 2),
    "topCategories": category_comparison.to_dict("records"),
    "topMerchants": top_merchants.to_dict("records"),
    "largestTransactions": largest_txns.to_dict("records"),
    "lastUpdated": datetime.utcnow().isoformat(),
}

# COMMAND ----------
# Write to DynamoDB
ddb = boto3.client("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1"))

def to_dynamodb_value(v):
    if isinstance(v, bool):
        return {"BOOL": v}
    elif isinstance(v, (int, float)):
        return {"N": str(v)}
    elif isinstance(v, str):
        return {"S": v}
    elif isinstance(v, list):
        return {"S": json.dumps(v, default=str)}
    elif isinstance(v, dict):
        return {"S": json.dumps(v, default=str)}
    return {"S": str(v)}

try:
    ddb.put_item(
        TableName="ss360-metrics",
        Item={k: to_dynamodb_value(v) for k, v in metrics.items()},
    )
    print("Metrics saved to DynamoDB ss360-metrics")
except Exception as e:
    print(f"Warning: DynamoDB write failed: {e}")

# COMMAND ----------
# Create Athena-queryable views in S3 (JSON format for Athena JSON SerDe)
athena_views_path = f"gold/athena_views/"
s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))

# Write metrics summary
s3.put_object(
    Bucket=S3_BUCKET,
    Key=f"{athena_views_path}metrics/{today}.json",
    Body=json.dumps(metrics, default=str).encode(),
    ContentType="application/json",
)

# Write category breakdown
for record in category_comparison.to_dict("records"):
    record["date"] = today
    record["user_id"] = USER_ID

s3.put_object(
    Bucket=S3_BUCKET,
    Key=f"{athena_views_path}category_breakdown/{today}.json",
    Body="\n".join(json.dumps(r, default=str) for r in category_comparison.to_dict("records")).encode(),
    ContentType="application/json",
)

print(f"Athena views written to s3://{S3_BUCKET}/{athena_views_path}")

# COMMAND ----------
print("\n=== GOLD METRICS SUMMARY ===")
print(f"MTD Spend:       ${mtd_spend:,.2f}")
print(f"Burn Rate:       ${monthly_burn_rate:,.2f}/month")
print(f"Health Score:    {health_score}/100")
print(f"Anomalies:       {anomaly_count} ({high_anomaly_count} HIGH)")
print(f"Runway:          {runway_days} days")
print(f"MoM Change:      {mom_change_pct:+.1f}%")

# COMMAND ----------
print("Notebook 05_gold_metrics completed successfully")
