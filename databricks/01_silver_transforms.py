# Databricks notebook source
# SmartSpend360 — Notebook 01: Silver Transforms
# Reads S3 silver Parquet → cleans → enriches → writes Gold Delta

# COMMAND ----------

import os
from datetime import datetime, timedelta

from pyspark.sql import SparkSession, functions as F
from pyspark.sql.window import Window
from pyspark.sql.types import (
    BooleanType, DoubleType, StringType, StructField, StructType,
)

# COMMAND ----------
# Configuration
S3_BUCKET = dbutils.widgets.get("s3_bucket") if "dbutils" in dir() else os.getenv("S3_BUCKET_NAME", "smartspend360-datalake")
RUN_DATE = dbutils.widgets.get("run_date") if "dbutils" in dir() else datetime.utcnow().strftime("%Y-%m-%d")

print(f"S3 Bucket: {S3_BUCKET}")
print(f"Run Date: {RUN_DATE}")

# COMMAND ----------
# Initialize Spark (Databricks uses built-in `spark`, local needs init)
try:
    spark  # Already exists in Databricks
except NameError:
    spark = (
        SparkSession.builder
        .appName("SmartSpend360-SilverTransforms")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .getOrCreate()
    )

spark.conf.set("spark.sql.shuffle.partitions", "8")

# COMMAND ----------
# Category taxonomy mapping (Plaid categories → SmartSpend360 custom)
CATEGORY_MAP = {
    "Food and Drink": "Food",
    "Restaurants": "Food",
    "Groceries": "Food",
    "Fast Food": "Food",
    "Coffee Shop": "Food",
    "Travel": "Transport",
    "Transportation": "Transport",
    "Taxi": "Transport",
    "Uber": "Transport",
    "Lyft": "Transport",
    "Gas Stations": "Transport",
    "Airlines": "Transport",
    "Entertainment": "Entertainment",
    "Recreation": "Entertainment",
    "Arts": "Entertainment",
    "Movies": "Entertainment",
    "Music": "Entertainment",
    "Games": "Entertainment",
    "Healthcare": "Healthcare",
    "Medical": "Healthcare",
    "Pharmacy": "Healthcare",
    "Gyms": "Healthcare",
    "Personal Care": "Healthcare",
    "Housing": "Housing",
    "Rent": "Housing",
    "Mortgage": "Housing",
    "Home": "Housing",
    "Utilities": "Housing",
    "Income": "Income",
    "Payroll": "Income",
    "Deposit": "Income",
    "Transfer": "Transfer",
    "ATM": "Transfer",
    "Shopping": "Other",
    "Department Stores": "Other",
    "Electronics": "Other",
    "Clothing": "Other",
}

VALID_CATEGORIES = {"Food", "Transport", "Entertainment", "Healthcare", "Housing", "Income", "Transfer", "Other"}

# COMMAND ----------
# Load silver transactions
silver_path = f"s3a://{S3_BUCKET}/silver/transactions/"
print(f"Reading from: {silver_path}")

df_raw = (
    spark.read
    .option("mergeSchema", "true")
    .parquet(silver_path)
)

print(f"Loaded {df_raw.count()} rows from silver layer")
df_raw.printSchema()

# COMMAND ----------
# Step 1: Remove duplicates
df_dedup = df_raw.dropDuplicates(["transaction_id"])
dupes_removed = df_raw.count() - df_dedup.count()
print(f"Removed {dupes_removed} duplicate transactions")

# COMMAND ----------
# Step 2: Standardize merchant names
df_merchants = df_dedup.withColumn(
    "merchant_normalized",
    F.lower(F.trim(F.regexp_replace(F.col("merchant_name"), r"[^a-zA-Z0-9\s]", "")))
)

# COMMAND ----------
# Step 3: Map Plaid categories to SmartSpend360 taxonomy
category_map_broadcast = spark.sparkContext.broadcast(CATEGORY_MAP)

@F.udf(StringType())
def map_category(category):
    if not category:
        return "Other"
    cat = category_map_broadcast.value
    return cat.get(category, "Other")

df_categorized = df_merchants.withColumn(
    "category_mapped",
    map_category(F.col("category"))
)

# COMMAND ----------
# Step 4: Add derived columns
df_enriched = (
    df_categorized
    .withColumn("date_parsed", F.to_date(F.col("date"), "yyyy-MM-dd"))
    .withColumn("day_of_week", F.dayofweek(F.col("date_parsed")))  # 1=Sunday, 7=Saturday
    .withColumn("week_of_month", F.ceil(F.dayofmonth(F.col("date_parsed")) / 7))
    .withColumn("is_weekend", F.col("day_of_week").isin(1, 7))
    .withColumn("month", F.month(F.col("date_parsed")))
    .withColumn("year", F.year(F.col("date_parsed")))
    .withColumn("amount_abs", F.abs(F.col("amount")))
    .withColumn("is_debit", F.col("amount") > 0)  # Positive = debit in Plaid convention
    .withColumn("user_id", F.lit("demo_user"))  # Will come from account mapping in prod
)

# COMMAND ----------
# Step 5: Rolling window aggregations
window_7d = (
    Window
    .partitionBy("user_id")
    .orderBy(F.col("date_parsed").cast("long"))
    .rangeBetween(-7 * 86400, 0)
)

window_30d = (
    Window
    .partitionBy("user_id")
    .orderBy(F.col("date_parsed").cast("long"))
    .rangeBetween(-30 * 86400, 0)
)

df_with_rolling = (
    df_enriched
    .withColumn(
        "rolling_7d_spend",
        F.sum(F.when(F.col("is_debit"), F.col("amount_abs")).otherwise(0)).over(window_7d)
    )
    .withColumn(
        "rolling_30d_spend",
        F.sum(F.when(F.col("is_debit"), F.col("amount_abs")).otherwise(0)).over(window_30d)
    )
    .withColumn(
        "rolling_30d_mean",
        F.avg(F.when(F.col("is_debit"), F.col("amount_abs")).otherwise(None)).over(window_30d)
    )
    .withColumn(
        "rolling_30d_std",
        F.stddev(F.when(F.col("is_debit"), F.col("amount_abs")).otherwise(None)).over(window_30d)
    )
)

# COMMAND ----------
# Select final output columns
df_gold = df_with_rolling.select(
    "transaction_id",
    "account_id",
    "user_id",
    "amount",
    "amount_abs",
    "is_debit",
    "date",
    "date_parsed",
    "day_of_week",
    "week_of_month",
    "is_weekend",
    "month",
    "year",
    "merchant_name",
    "merchant_normalized",
    F.col("category_mapped").alias("category"),
    "category_id",
    "payment_channel",
    "pending",
    "iso_currency_code",
    "rolling_7d_spend",
    "rolling_30d_spend",
    "rolling_30d_mean",
    "rolling_30d_std",
    "ingested_at",
)

# COMMAND ----------
# Write to gold layer as Delta format
gold_path = f"s3a://{S3_BUCKET}/gold/transactions/"
print(f"Writing to: {gold_path}")

(
    df_gold
    .write
    .format("delta")
    .mode("overwrite")
    .partitionBy("year", "month")
    .save(gold_path)
)

final_count = df_gold.count()
print(f"Gold transactions written: {final_count} rows")

# COMMAND ----------
# Summary stats
print("\n=== TRANSFORM SUMMARY ===")
print(f"Input rows:     {df_raw.count()}")
print(f"After dedup:    {df_dedup.count()}")
print(f"Final output:   {final_count}")
print(f"\nCategory distribution:")
df_gold.groupBy("category").count().orderBy("count", ascending=False).show()
print(f"\nDate range:")
df_gold.agg(F.min("date").alias("earliest"), F.max("date").alias("latest")).show()

# COMMAND ----------
print("Notebook 01_silver_transforms completed successfully")
