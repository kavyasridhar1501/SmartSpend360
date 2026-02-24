# Databricks notebook source
# SmartSpend360 — Notebook 03: Anomaly Detection
# Trains Isolation Forest on feature matrix and classifies transactions

# COMMAND ----------

import os
import pickle
import uuid
from datetime import datetime
from io import BytesIO

import boto3
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

S3_BUCKET = dbutils.widgets.get("s3_bucket") if "dbutils" in dir() else os.getenv("S3_BUCKET_NAME", "smartspend360-datalake")
RUN_DATE = dbutils.widgets.get("run_date") if "dbutils" in dir() else datetime.utcnow().strftime("%Y-%m-%d")

# COMMAND ----------

try:
    spark
except NameError:
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.appName("SmartSpend360-AnomalyDetection").getOrCreate()

# COMMAND ----------
# Load feature matrix (latest file)
features_path = f"s3a://{S3_BUCKET}/gold/features/{RUN_DATE}.parquet"
print(f"Loading features from: {features_path}")

df_spark = spark.read.parquet(features_path)
df = df_spark.toPandas()
print(f"Loaded {len(df)} rows for anomaly detection")

# COMMAND ----------
# Feature selection for model
FEATURE_COLS = [
    "daily_total",
    "daily_transaction_count",
    "unique_merchants",
    "max_transaction",
    "avg_transaction",
    "merchant_diversity_score",
    "weekend_spend_ratio",
    "spend_trend_7d",
    "ratio_food",
    "ratio_transport",
    "ratio_entertainment",
    "ratio_healthcare",
    "ratio_housing",
    "ratio_other",
    "day_of_week",
    "is_weekend",
]

# Filter to available columns
available = [c for c in FEATURE_COLS if c in df.columns]
print(f"Using {len(available)} features: {available}")

X = df[available].fillna(0)
X["is_weekend"] = X["is_weekend"].astype(int)

# COMMAND ----------
# Scale features
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# COMMAND ----------
# Train Isolation Forest
print("Training Isolation Forest...")
iso_forest = IsolationForest(
    contamination=0.05,
    n_estimators=100,
    max_samples="auto",
    random_state=42,
    n_jobs=-1,
)
iso_forest.fit(X_scaled)

# Generate anomaly scores (-1 to 1: lower = more anomalous)
raw_scores = iso_forest.decision_function(X_scaled)  # positive = normal
predictions = iso_forest.predict(X_scaled)  # -1 = anomaly, 1 = normal

# Normalize scores to -1..1 range
score_min, score_max = raw_scores.min(), raw_scores.max()
normalized_scores = 2 * (raw_scores - score_min) / (score_max - score_min + 1e-8) - 1

df["anomaly_score"] = normalized_scores
df["anomaly_prediction"] = predictions
df["is_anomaly"] = predictions == -1

# COMMAND ----------
# Classify severity
def classify_severity(score: float) -> str:
    if score < -0.5:
        return "HIGH"
    elif score < -0.3:
        return "MEDIUM"
    return "NORMAL"

df["anomaly_severity"] = df["anomaly_score"].apply(classify_severity)

anomaly_count = df["is_anomaly"].sum()
high_count = (df["anomaly_severity"] == "HIGH").sum()
medium_count = (df["anomaly_severity"] == "MEDIUM").sum()
print(f"\nAnomaly detection results:")
print(f"  Total rows:   {len(df)}")
print(f"  Anomalies:    {anomaly_count} ({anomaly_count/len(df)*100:.1f}%)")
print(f"  HIGH:         {high_count}")
print(f"  MEDIUM:       {medium_count}")

# COMMAND ----------
# Join anomaly scores back to transactions for full context
gold_txn_path = f"s3a://{S3_BUCKET}/gold/transactions/"
df_txns_spark = spark.read.format("delta").load(gold_txn_path)
df_txns = df_txns_spark.toPandas()

# Merge on date + user_id
df_anomaly_detail = df_txns.merge(
    df[["date", "user_id", "anomaly_score", "anomaly_severity", "is_anomaly"]],
    on=["date", "user_id"],
    how="left",
)
df_anomaly_detail["anomaly_score"] = df_anomaly_detail["anomaly_score"].fillna(0)
df_anomaly_detail["anomaly_severity"] = df_anomaly_detail["anomaly_severity"].fillna("NORMAL")
df_anomaly_detail["is_anomaly"] = df_anomaly_detail["is_anomaly"].fillna(False)

# COMMAND ----------
# Save anomaly results to S3 gold/anomalies/
anomaly_path = f"gold/anomalies/{RUN_DATE}/"
s3 = boto3.client("s3")

# Save full anomaly detail as Parquet via Spark
df_anomaly_spark = spark.createDataFrame(df_anomaly_detail)
(
    df_anomaly_spark
    .write
    .mode("overwrite")
    .parquet(f"s3a://{S3_BUCKET}/{anomaly_path}")
)
print(f"Anomaly details saved to s3://{S3_BUCKET}/{anomaly_path}")

# COMMAND ----------
# Save anomaly summary to DynamoDB
ddb = boto3.client("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1"))
now = datetime.utcnow()

anomaly_summary = {
    "userId": {"S": "demo_user"},
    "date": {"S": RUN_DATE},
    "anomalyCount": {"N": str(int(anomaly_count))},
    "highCount": {"N": str(int(high_count))},
    "mediumCount": {"N": str(int(medium_count))},
    "anomalyRate": {"N": str(round(anomaly_count / len(df) if len(df) > 0 else 0, 4))},
    "modelVersion": {"S": f"isolation_forest_v{RUN_DATE}"},
    "timestamp": {"S": now.isoformat()},
    "type": {"S": "anomaly_summary"},
}

try:
    ddb.put_item(TableName="ss360-metrics", Item=anomaly_summary)
    print("Anomaly summary saved to DynamoDB")
except Exception as e:
    print(f"Warning: Could not save to DynamoDB: {e}")

# COMMAND ----------
# Save high-severity anomalies as individual DynamoDB alerts
high_anomaly_days = df[df["anomaly_severity"] == "HIGH"].head(20)
for _, row in high_anomaly_days.iterrows():
    try:
        ddb.put_item(
            TableName="ss360-alerts",
            Item={
                "userId": {"S": "demo_user"},
                "alertId": {"S": f"anomaly_{uuid.uuid4().hex[:8]}"},
                "alertType": {"S": "anomaly_detected"},
                "date": {"S": str(row["date"])},
                "anomalyScore": {"N": str(round(float(row["anomaly_score"]), 4))},
                "severity": {"S": "HIGH"},
                "dailyTotal": {"N": str(round(float(row.get("daily_total", 0)), 2))},
                "status": {"S": "active"},
                "timestamp": {"S": now.isoformat()},
            },
        )
    except Exception as e:
        print(f"Warning: Could not save alert: {e}")

print(f"Saved {len(high_anomaly_days)} HIGH anomaly alerts to DynamoDB")

# COMMAND ----------
# Persist model artifact to S3
model_artifact = {"model": iso_forest, "scaler": scaler, "feature_cols": available}
model_buf = BytesIO()
pickle.dump(model_artifact, model_buf)
model_buf.seek(0)

model_key = f"models/isolation_forest_v{RUN_DATE}.pkl"
s3.put_object(Bucket=S3_BUCKET, Key=model_key, Body=model_buf.read())
print(f"Model saved to s3://{S3_BUCKET}/{model_key}")

# COMMAND ----------
print("Notebook 03_anomaly_detection completed successfully")
