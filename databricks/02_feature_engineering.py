# Databricks notebook source
# SmartSpend360 — Notebook 02: Feature Engineering
# Computes user-level daily feature matrix for ML models

# COMMAND ----------

import os
from datetime import datetime

from pyspark.sql import functions as F
from pyspark.sql.window import Window

S3_BUCKET = dbutils.widgets.get("s3_bucket") if "dbutils" in dir() else os.getenv("S3_BUCKET_NAME", "smartspend360-datalake")
RUN_DATE = dbutils.widgets.get("run_date") if "dbutils" in dir() else datetime.utcnow().strftime("%Y-%m-%d")

# COMMAND ----------

try:
    spark
except NameError:
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.appName("SmartSpend360-FeatureEngineering").getOrCreate()

spark.conf.set("spark.sql.shuffle.partitions", "8")

# COMMAND ----------
# Load gold transactions
gold_path = f"s3a://{S3_BUCKET}/gold/transactions/"
df = spark.read.format("delta").load(gold_path)
print(f"Loaded {df.count()} gold transactions")

CATEGORIES = ["Food", "Transport", "Entertainment", "Healthcare", "Housing", "Income", "Transfer", "Other"]

# COMMAND ----------
# Daily aggregates per user
window_30d_day = (
    Window
    .partitionBy("user_id")
    .orderBy(F.col("date_parsed").cast("long"))
    .rangeBetween(-30 * 86400, 0)
)

df_debits = df.filter(F.col("is_debit"))

df_daily = (
    df_debits
    .groupBy("user_id", "date", "date_parsed", "is_weekend", "day_of_week")
    .agg(
        F.sum("amount_abs").alias("daily_total"),
        F.count("transaction_id").alias("daily_transaction_count"),
        F.countDistinct("merchant_normalized").alias("unique_merchants"),
        F.max("amount_abs").alias("max_transaction"),
        F.avg("amount_abs").alias("avg_transaction"),
        # Per-category spend
        *[
            F.sum(
                F.when(F.col("category") == cat, F.col("amount_abs")).otherwise(0)
            ).alias(f"spend_{cat.lower()}")
            for cat in CATEGORIES
            if cat not in ("Income", "Transfer")
        ],
    )
)

# COMMAND ----------
# Category spend ratios
df_ratios = df_daily
for cat in CATEGORIES:
    if cat in ("Income", "Transfer"):
        continue
    col_name = f"spend_{cat.lower()}"
    ratio_name = f"ratio_{cat.lower()}"
    df_ratios = df_ratios.withColumn(
        ratio_name,
        F.when(F.col("daily_total") > 0, F.col(col_name) / F.col("daily_total")).otherwise(0)
    )

# COMMAND ----------
# Merchant diversity score: unique_merchants / daily_transaction_count
df_diversity = df_ratios.withColumn(
    "merchant_diversity_score",
    F.when(
        F.col("daily_transaction_count") > 0,
        F.col("unique_merchants") / F.col("daily_transaction_count")
    ).otherwise(0)
)

# COMMAND ----------
# Weekend spend ratio (7-day rolling)
window_7d = (
    Window
    .partitionBy("user_id")
    .orderBy(F.col("date_parsed").cast("long"))
    .rangeBetween(-7 * 86400, 0)
)

df_weekend = df_diversity.withColumn(
    "weekend_spend_7d",
    F.sum(F.when(F.col("is_weekend"), F.col("daily_total")).otherwise(0)).over(window_7d)
).withColumn(
    "total_spend_7d",
    F.sum("daily_total").over(window_7d)
).withColumn(
    "weekend_spend_ratio",
    F.when(F.col("total_spend_7d") > 0, F.col("weekend_spend_7d") / F.col("total_spend_7d")).otherwise(0)
)

# COMMAND ----------
# Large transaction flag: amount > mean + 2*std over rolling 30d
df_stats = (
    df
    .filter(F.col("is_debit"))
    .groupBy("user_id")
    .agg(
        F.avg("amount_abs").alias("global_mean"),
        F.stddev("amount_abs").alias("global_std"),
    )
)

df_with_flag = df_daily.join(df_stats, on="user_id", how="left").withColumn(
    "large_transaction_threshold",
    F.col("global_mean") + 2 * F.col("global_std")
).withColumn(
    "has_large_transaction",
    F.col("max_transaction") > F.col("large_transaction_threshold")
)

# Merge all features
df_features = (
    df_weekend
    .join(
        df_stats.select("user_id", "global_mean", "global_std"),
        on="user_id", how="left"
    )
    .withColumn(
        "large_transaction_threshold",
        F.col("global_mean") + 2 * F.col("global_std")
    )
    .withColumn(
        "has_large_transaction",
        F.col("max_transaction") > F.col("large_transaction_threshold")
    )
    .drop("weekend_spend_7d", "total_spend_7d")
)

# COMMAND ----------
# Spend trend: slope of daily_total over last 7 days (positive = increasing)
# Approximated as: (today - 7d_ago_avg) / 7d_avg
df_trend = df_features.withColumn(
    "spend_trend_7d",
    (F.col("daily_total") - F.avg("daily_total").over(window_7d)) / (F.avg("daily_total").over(window_7d) + 0.01)
)

# COMMAND ----------
# Write feature matrix to gold/features/
features_path = f"s3a://{S3_BUCKET}/gold/features/"
print(f"Writing feature matrix to: {features_path}")

(
    df_trend
    .write
    .parquet(features_path + f"{RUN_DATE}.parquet")
)

feature_count = df_trend.count()
print(f"Feature matrix written: {feature_count} rows, {len(df_trend.columns)} features")

# COMMAND ----------
# Preview schema
print("\n=== FEATURE SCHEMA ===")
df_trend.printSchema()
print("\n=== SAMPLE FEATURES ===")
df_trend.select("date", "daily_total", "merchant_diversity_score", "weekend_spend_ratio", "has_large_transaction").show(5)

# COMMAND ----------
print("Notebook 02_feature_engineering completed successfully")
