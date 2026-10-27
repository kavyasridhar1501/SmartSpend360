#!/usr/bin/env python3
"""
SmartSpend360 — Anomaly model evaluation.

Rebuilds the notebook 02 daily feature matrix in pandas on mock data from
data/seed/generate_mock_data.py, trains the notebook 03 Isolation Forest, and
scores it against the injected anomaly labels. Compares:

  before: all debits, original 16 features (incl. ratio_housing)
  after:  recurring bills (Housing) excluded, 15 features
  rule:   day max_transaction > global mean + 2*std (notebook 02's flag)

Runs locally with pandas, numpy and scikit-learn only (no AWS, no Spark).

Usage:
    python scripts/evaluate_anomaly_model.py [--seeds 30] [--days 90] [--as-of 2026-10-27]
"""

import argparse
import importlib.util
import logging
import random
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATOR_PATH = REPO_ROOT / "data" / "seed" / "generate_mock_data.py"

RECURRING_BILL_CATEGORIES = ["Housing"]
SPEND_CATEGORIES_BEFORE = ["Food", "Transport", "Entertainment", "Healthcare", "Housing", "Other"]
SPEND_CATEGORIES_AFTER = ["Food", "Transport", "Entertainment", "Healthcare", "Other"]

BASE_FEATURES = [
    "daily_total",
    "daily_transaction_count",
    "unique_merchants",
    "max_transaction",
    "avg_transaction",
    "merchant_diversity_score",
    "weekend_spend_ratio",
    "spend_trend_7d",
]


def feature_cols(categories: list) -> list:
    return BASE_FEATURES + [f"ratio_{c.lower()}" for c in categories] + ["day_of_week", "is_weekend"]


def load_generator(as_of: datetime):
    """Import generate_mock_data as a module. Its AWS code lives in main(), so it never runs."""
    spec = importlib.util.spec_from_file_location("generate_mock_data", GENERATOR_PATH)
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    gen.log.setLevel(logging.WARNING)

    # The generator anchors its 90-day window on utcnow(), and rent/utility days depend
    # on the calendar, so pin the date to keep runs reproducible.
    class _FixedDatetime(datetime):
        @classmethod
        def utcnow(cls):
            return as_of

    gen.datetime = _FixedDatetime
    return gen


def build_daily_features(txns: pd.DataFrame, exclude_recurring: bool) -> pd.DataFrame:
    """Pandas port of notebook 02 for a single user."""
    categories = SPEND_CATEGORIES_AFTER if exclude_recurring else SPEND_CATEGORIES_BEFORE

    debits = txns[txns["is_debit"]]
    if exclude_recurring:
        debits = debits[~debits["category"].isin(RECURRING_BILL_CATEGORIES)]

    daily = debits.groupby("date_parsed").agg(
        daily_total=("amount_abs", "sum"),
        daily_transaction_count=("transaction_id", "count"),
        unique_merchants=("merchant_normalized", "nunique"),
        max_transaction=("amount_abs", "max"),
        avg_transaction=("amount_abs", "mean"),
        is_weekend=("is_weekend", "first"),
        day_of_week=("day_of_week", "first"),
    )
    cat_spend = (
        debits.pivot_table(index="date_parsed", columns="category", values="amount_abs", aggfunc="sum")
        .reindex(columns=categories)
        .fillna(0.0)
    )
    for cat in categories:
        daily[f"spend_{cat.lower()}"] = cat_spend[cat]
        daily[f"ratio_{cat.lower()}"] = np.where(
            daily["daily_total"] > 0, daily[f"spend_{cat.lower()}"] / daily["daily_total"], 0.0
        )

    daily["merchant_diversity_score"] = np.where(
        daily["daily_transaction_count"] > 0,
        daily["unique_merchants"] / daily["daily_transaction_count"],
        0.0,
    )

    # rangeBetween(-7 days, 0) == trailing 8 calendar days inclusive; "8D" covers (t-8d, t]
    daily = daily.sort_index()
    weekend_total = daily["daily_total"].where(daily["is_weekend"], 0.0)
    weekend_7d = weekend_total.rolling("8D").sum()
    total_7d = daily["daily_total"].rolling("8D").sum()
    avg_7d = daily["daily_total"].rolling("8D").mean()
    daily["weekend_spend_ratio"] = np.where(total_7d > 0, weekend_7d / total_7d, 0.0)
    daily["spend_trend_7d"] = (daily["daily_total"] - avg_7d) / (avg_7d + 0.01)

    # Global stats for the large-transaction rule (Spark stddev = sample std)
    global_mean = debits["amount_abs"].mean()
    global_std = debits["amount_abs"].std(ddof=1)
    daily["large_transaction_threshold"] = global_mean + 2 * global_std
    daily["has_large_transaction"] = daily["max_transaction"] > daily["large_transaction_threshold"]

    return daily


def score(y_true, y_pred, y_score) -> dict:
    return {
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "roc_auc": roc_auc_score(y_true, y_score) if len(set(y_true)) > 1 else np.nan,
    }


def evaluate_seed(gen, seed: int, days: int) -> dict:
    random.seed(seed)
    txns = pd.DataFrame(gen.generate_transactions(days))
    txns["date_parsed"] = pd.to_datetime(txns["date"])
    # Match notebook 01: Spark dayofweek is 1=Sunday..7=Saturday
    txns["day_of_week"] = txns["date_parsed"].dt.dayofweek.add(1).mod(7).add(1)
    txns["is_weekend"] = txns["day_of_week"].isin([1, 7])

    day_labels = txns.groupby("date_parsed")["_is_anomaly_injected"].any()

    results = {}
    for version, exclude in (("before", False), ("after", True)):
        daily = build_daily_features(txns, exclude_recurring=exclude)
        y = day_labels.reindex(daily.index).fillna(False).astype(int).to_numpy()

        cols = feature_cols(SPEND_CATEGORIES_AFTER if exclude else SPEND_CATEGORIES_BEFORE)
        X = daily[cols].fillna(0).astype(float)
        X_scaled = StandardScaler().fit_transform(X)

        model = IsolationForest(contamination=0.05, n_estimators=100, random_state=42)
        model.fit(X_scaled)
        pred = (model.predict(X_scaled) == -1).astype(int)
        results[f"iforest_{version}"] = score(y, pred, -model.decision_function(X_scaled))

        rule_pred = daily["has_large_transaction"].astype(int).to_numpy()
        rule_score = (daily["max_transaction"] - daily["large_transaction_threshold"]).to_numpy()
        results[f"rule_{version}"] = score(y, rule_pred, rule_score)

    return results


def main():
    parser = argparse.ArgumentParser(description="Evaluate the SmartSpend360 anomaly model")
    parser.add_argument("--seeds", type=int, default=30, help="Number of seeds (0..N-1)")
    parser.add_argument("--days", type=int, default=90, help="Days of history per seed")
    parser.add_argument("--as-of", default="2026-10-27", help="Pinned 'today' for the generator (YYYY-MM-DD)")
    args = parser.parse_args()

    gen = load_generator(datetime.strptime(args.as_of, "%Y-%m-%d"))

    rows = []
    for s in range(args.seeds):
        for model_name, metrics in evaluate_seed(gen, s, args.days).items():
            rows.append({"seed": s, "model": model_name, **metrics})
    df = pd.DataFrame(rows)

    labels = {
        "iforest_before": "Isolation Forest — before (all debits, 16 features)",
        "iforest_after": "Isolation Forest — after (Housing excluded, 15 features)",
        "rule_before": "Rule max > mean + 2*std — all debits",
        "rule_after": "Rule max > mean + 2*std — Housing excluded",
    }
    metrics = ["precision", "recall", "f1", "roc_auc"]
    mean = df.groupby("model")[metrics].mean().reindex(labels)
    std = df.groupby("model")[metrics].std().reindex(labels)

    print("=" * 78)
    print("SmartSpend360 anomaly model evaluation")
    print(f"Seeds: {args.seeds}  |  Days per seed: {args.days}  |  As of: {args.as_of}")
    print("Label: day has >= 1 transaction with _is_anomaly_injected == True")
    print("=" * 78)
    print(f"{'Model':<58}{'Prec':>5}{'Rec':>6}{'F1':>6}{'AUC':>6}")
    print("-" * 78)
    for key, label in labels.items():
        m = mean.loc[key]
        print(f"{label:<58}{m.precision:>5.2f}{m.recall:>6.2f}{m.f1:>6.2f}{m.roc_auc:>6.2f}")
    print("-" * 78)
    print("Std across seeds:")
    for key, label in labels.items():
        sd = std.loc[key]
        print(f"  {label:<56}{sd.precision:>5.2f}{sd.recall:>6.2f}{sd.f1:>6.2f}{sd.roc_auc:>6.2f}")
    print("=" * 78)


if __name__ == "__main__":
    main()
