# Databricks notebook source
# SmartSpend360 — Notebook 04: Cash Flow Forecast
# Trains Facebook Prophet on daily spend → 30-day forecast + runway

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
    spark = SparkSession.builder.appName("SmartSpend360-Forecast").getOrCreate()

# COMMAND ----------
# Load gold transactions and compute daily aggregates
gold_path = f"s3a://{S3_BUCKET}/gold/transactions/"
df_txns = spark.read.format("delta").load(gold_path).toPandas()

# Daily spend aggregates (debits only)
df_daily = (
    df_txns[df_txns["is_debit"]]
    .groupby(["user_id", "date"])
    .agg(
        daily_spend=("amount_abs", "sum"),
        txn_count=("transaction_id", "count"),
        is_weekend=("is_weekend", "first"),
    )
    .reset_index()
    .sort_values("date")
)

print(f"Daily aggregates: {len(df_daily)} days for user(s): {df_daily['user_id'].unique()}")
df_daily.head()

# COMMAND ----------
# Prophet requires columns named 'ds' and 'y'
from prophet import Prophet
from prophet.make_holidays import make_holidays_df

user_id = "demo_user"
df_user = df_daily[df_daily["user_id"] == user_id].copy()
df_user["ds"] = pd.to_datetime(df_user["date"])
df_user["y"] = df_user["daily_spend"]
df_user["is_weekend"] = df_user["is_weekend"].astype(int)

print(f"Training data: {len(df_user)} days")
print(f"Spend range: ${df_user['y'].min():.2f} - ${df_user['y'].max():.2f}")
print(f"Mean daily spend: ${df_user['y'].mean():.2f}")

# COMMAND ----------
# Build US holidays
try:
    holidays = make_holidays_df(year_list=[2023, 2024, 2025], country="US")
except Exception:
    holidays = None
    print("Could not load US holidays, proceeding without")

# COMMAND ----------
# Train Prophet model
model = Prophet(
    yearly_seasonality=False,
    weekly_seasonality=True,
    daily_seasonality=False,
    holidays=holidays,
    interval_width=0.80,
    changepoint_prior_scale=0.05,
)
model.add_regressor("is_weekend")

model.fit(df_user[["ds", "y", "is_weekend"]])
print("Prophet model trained")

# COMMAND ----------
# Generate 30-day forecast
HORIZON_DAYS = 30
future = model.make_future_dataframe(periods=HORIZON_DAYS)
future["is_weekend"] = future["ds"].dt.dayofweek.isin([5, 6]).astype(int)

forecast = model.predict(future)

# Clip negative values (can't have negative spend)
forecast["yhat"] = forecast["yhat"].clip(lower=0)
forecast["yhat_lower"] = forecast["yhat_lower"].clip(lower=0)
forecast["yhat_upper"] = forecast["yhat_upper"].clip(lower=0)

# 95% confidence intervals (re-train with interval_width=0.95 for separate bands)
model_95 = Prophet(
    yearly_seasonality=False,
    weekly_seasonality=True,
    holidays=holidays,
    interval_width=0.95,
    changepoint_prior_scale=0.05,
)
model_95.add_regressor("is_weekend")
model_95.fit(df_user[["ds", "y", "is_weekend"]])
forecast_95 = model_95.predict(future)

forecast["yhat_lower_95"] = forecast_95["yhat_lower"].clip(lower=0)
forecast["yhat_upper_95"] = forecast_95["yhat_upper"].clip(lower=0)

print(f"Forecast generated for {HORIZON_DAYS} days")
forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(10)

# COMMAND ----------
# Compute runway (days until projected balance hits zero)
ASSUMED_DAILY_INCOME = 200.0  # $200/day default assumption (~$6000/month)

future_only = forecast[forecast["ds"] > pd.Timestamp(RUN_DATE)].copy()
future_only["net_daily"] = ASSUMED_DAILY_INCOME - future_only["yhat"]
future_only["cumulative_balance"] = future_only["net_daily"].cumsum()

runway_row = future_only[future_only["cumulative_balance"] < 0]
if len(runway_row) > 0:
    runway_days = (runway_row.iloc[0]["ds"] - pd.Timestamp(RUN_DATE)).days
else:
    runway_days = HORIZON_DAYS  # More than 30 days

projected_30d_spend = future_only["yhat"].sum()
print(f"\nRunway: {runway_days} days")
print(f"Projected 30-day spend: ${projected_30d_spend:.2f}")

# COMMAND ----------
# Build output records for S3 + DynamoDB
forecast_records = []
for _, row in forecast.iterrows():
    record = {
        "ds": row["ds"].strftime("%Y-%m-%d"),
        "yhat": round(float(row["yhat"]), 2),
        "yhat_lower": round(float(row["yhat_lower"]), 2),
        "yhat_upper": round(float(row["yhat_upper"]), 2),
        "yhat_lower_95": round(float(row.get("yhat_lower_95", row["yhat_lower"])), 2),
        "yhat_upper_95": round(float(row.get("yhat_upper_95", row["yhat_upper"])), 2),
        "trend": round(float(row.get("trend", 0)), 2),
        "is_future": row["ds"] > pd.Timestamp(RUN_DATE),
    }
    forecast_records.append(record)

# COMMAND ----------
# Save to S3 gold/forecasts/
s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
forecast_payload = {
    "user_id": user_id,
    "run_date": RUN_DATE,
    "horizon_days": HORIZON_DAYS,
    "runway_days": int(runway_days),
    "projected_30d_spend": round(float(projected_30d_spend), 2),
    "mean_daily_spend": round(float(df_user["y"].mean()), 2),
    "assumed_daily_income": ASSUMED_DAILY_INCOME,
    "forecast": forecast_records,
}

s3_key = f"gold/forecasts/{RUN_DATE}.json"
s3.put_object(
    Bucket=S3_BUCKET,
    Key=s3_key,
    Body=json.dumps(forecast_payload, default=str).encode(),
    ContentType="application/json",
)
print(f"Forecast saved to s3://{S3_BUCKET}/{s3_key}")

# COMMAND ----------
# Save to DynamoDB
ddb = boto3.client("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1"))
now = datetime.utcnow()

try:
    ddb.put_item(
        TableName="ss360-forecasts",
        Item={
            "userId": {"S": user_id},
            "forecastDate": {"S": RUN_DATE},
            "runwayDays": {"N": str(runway_days)},
            "projected30dSpend": {"N": str(round(float(projected_30d_spend), 2))},
            "meanDailySpend": {"N": str(round(float(df_user["y"].mean()), 2))},
            "horizonDays": {"N": str(HORIZON_DAYS)},
            "forecastS3Key": {"S": s3_key},
            "timestamp": {"S": now.isoformat()},
            "forecastJson": {"S": json.dumps(forecast_records[-HORIZON_DAYS:])},
        },
    )
    print("Forecast saved to DynamoDB")
except Exception as e:
    print(f"Warning: DynamoDB write failed: {e}")

# COMMAND ----------
# Save Parquet to gold/forecasts/ for Athena
df_forecast_spark = spark.createDataFrame(
    pd.DataFrame(forecast_records)
)
(
    df_forecast_spark
    .withColumn("user_id", spark.sql("select 'demo_user'").collect()[0][0] if False else __import__("pyspark.sql.functions", fromlist=["lit"]).lit(user_id))
    .write
    .mode("overwrite")
    .parquet(f"s3a://{S3_BUCKET}/gold/forecasts/{RUN_DATE}/")
)

print(f"\n=== FORECAST SUMMARY ===")
print(f"Training days:    {len(df_user)}")
print(f"Horizon:          {HORIZON_DAYS} days")
print(f"Runway:           {runway_days} days")
print(f"30d projected:    ${projected_30d_spend:.2f}")

# COMMAND ----------
print("Notebook 04_cash_flow_forecast completed successfully")
