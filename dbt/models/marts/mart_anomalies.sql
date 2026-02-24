-- SmartSpend360 dbt: mart_anomalies
-- Anomaly report table joining transaction detail with ML scores

{{
  config(
    materialized='table',
    tags=['marts', 'anomalies']
  )
}}

with transactions as (
    select * from {{ ref('int_transactions_enriched') }}
),

-- External anomaly scores loaded from gold/anomalies/ Parquet via Athena
anomaly_scores as (
    select
        transaction_id,
        user_id,
        date,
        cast(anomaly_score as double)   as anomaly_score,
        anomaly_severity,
        cast(is_anomaly as boolean)     as is_anomaly
    from {{ source('smartspend360_raw', 'gold_anomalies') }}
    where anomaly_severity != 'NORMAL'
),

joined as (
    select
        t.transaction_id,
        t.user_id,
        t.date,
        t.transaction_date,
        t.merchant_name,
        t.merchant_normalized,
        t.category,
        t.amount_usd,
        t.amount_abs,
        t.is_debit,
        t.is_weekend,
        t.payment_channel,
        t.rolling_30d_mean,
        t.rolling_30d_std,

        -- Anomaly info
        coalesce(a.anomaly_score, 0)        as anomaly_score,
        coalesce(a.anomaly_severity, 'NORMAL') as anomaly_severity,
        coalesce(a.is_anomaly, false)       as is_anomaly,

        -- How many std devs above mean?
        case
            when t.rolling_30d_std > 0
            then (t.amount_abs - t.rolling_30d_mean) / t.rolling_30d_std
            else 0
        end                                 as z_score,

        -- Human-readable explanation
        case
            when a.anomaly_severity = 'HIGH'   then 'Unusually high spending detected — significantly above 30-day baseline'
            when a.anomaly_severity = 'MEDIUM' then 'Moderately elevated spending — above normal patterns'
            else 'Within normal spending range'
        end                                 as anomaly_explanation,

        current_timestamp                   as dbt_processed_at

    from transactions t
    left join anomaly_scores a
        on t.transaction_id = a.transaction_id
)

select * from joined
where is_anomaly = true
order by anomaly_score asc, date desc
