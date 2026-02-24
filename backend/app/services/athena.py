"""SmartSpend360 — Athena Query Service"""

import time
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("athena")


def _get_client():
    settings = get_settings()
    kwargs = {"region_name": settings.aws_region}
    if settings.aws_access_key_id:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    return boto3.client("athena", **kwargs)


def execute_query(sql: str, timeout: int = 60) -> list[dict]:
    """Execute an Athena query and return rows as dicts."""
    settings = get_settings()
    client = _get_client()

    try:
        # Start query
        response = client.start_query_execution(
            QueryString=sql,
            QueryExecutionContext={"Database": settings.athena_database},
            WorkGroup=settings.athena_workgroup,
        )
        execution_id = response["QueryExecutionId"]
        log.debug("Athena query started", execution_id=execution_id)

        # Poll until complete
        start = time.time()
        while time.time() - start < timeout:
            status_resp = client.get_query_execution(QueryExecutionId=execution_id)
            state = status_resp["QueryExecution"]["Status"]["State"]

            if state == "SUCCEEDED":
                break
            elif state in ("FAILED", "CANCELLED"):
                reason = status_resp["QueryExecution"]["Status"].get("StateChangeReason", "Unknown")
                log.error("Athena query failed", state=state, reason=reason, sql=sql[:200])
                raise RuntimeError(f"Athena query {state}: {reason}")

            time.sleep(settings.athena_poll_interval)
        else:
            raise TimeoutError(f"Athena query timed out after {timeout}s")

        # Fetch results
        results = client.get_query_results(QueryExecutionId=execution_id)
        rows = _parse_results(results)
        log.debug("Athena query complete", rows=len(rows), execution_id=execution_id)
        return rows

    except ClientError as e:
        log.error("Athena client error", error=str(e))
        raise


def _parse_results(results: dict) -> list[dict]:
    """Convert Athena result set to list of dicts."""
    columns = [col["VarCharValue"] for col in results["ResultSet"]["Rows"][0]["Data"]]
    rows = []
    for row in results["ResultSet"]["Rows"][1:]:  # Skip header
        values = [cell.get("VarCharValue", None) for cell in row["Data"]]
        rows.append(dict(zip(columns, values)))

    # Handle pagination
    next_token = results.get("NextToken")
    while next_token:
        client = _get_client()
        page = client.get_query_results(
            QueryExecutionId=results["QueryExecution"]["QueryExecutionId"],
            NextToken=next_token,
        )
        for row in page["ResultSet"]["Rows"]:
            values = [cell.get("VarCharValue", None) for cell in row["Data"]]
            rows.append(dict(zip(columns, values)))
        next_token = page.get("NextToken")

    return rows


def get_transactions(
    user_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    category: Optional[str] = None,
    anomaly_only: bool = False,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Query transactions with filtering and pagination."""
    conditions = [f"user_id = '{user_id}'"]
    if start_date:
        conditions.append(f"date >= '{start_date}'")
    if end_date:
        conditions.append(f"date <= '{end_date}'")
    if category:
        conditions.append(f"category = '{category}'")
    if anomaly_only:
        conditions.append("is_anomaly = true")

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * page_size

    count_sql = f"""
    SELECT COUNT(*) as total
    FROM smartspend360_db.gold_transactions
    WHERE {where_clause}
    """

    data_sql = f"""
    SELECT
        transaction_id, user_id, date, merchant_name, category,
        amount_abs, is_debit, is_weekend, anomaly_score, anomaly_severity,
        rolling_30d_mean, ingested_at
    FROM smartspend360_db.gold_transactions
    WHERE {where_clause}
    ORDER BY date DESC
    LIMIT {page_size}
    OFFSET {offset}
    """

    try:
        count_rows = execute_query(count_sql)
        total = int(count_rows[0]["total"]) if count_rows else 0

        data_rows = execute_query(data_sql)
        total_pages = (total + page_size - 1) // page_size

        return {
            "transactions": data_rows,
            "total_count": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }
    except Exception as e:
        log.error("get_transactions failed", error=str(e))
        raise
