-- SmartSpend360 dbt: stg_transactions
-- Reads from S3 Parquet via Athena external table
-- Standardizes field names and types for downstream models

{{
  config(
    materialized='view',
    tags=['staging', 'transactions']
  )
}}

with source as (
    select
        transaction_id,
        account_id,
        user_id,
        cast(amount as double)               as amount,
        cast(amount_abs as double)           as amount_abs,
        cast(is_debit as boolean)            as is_debit,
        date,
        cast(date_parsed as date)            as transaction_date,
        cast(day_of_week as int)             as day_of_week,
        cast(week_of_month as int)           as week_of_month,
        cast(is_weekend as boolean)          as is_weekend,
        cast(month as int)                   as month,
        cast(year as int)                    as year,
        merchant_name,
        merchant_normalized,
        category,
        category_id,
        payment_channel,
        cast(pending as boolean)             as pending,
        iso_currency_code,
        cast(rolling_7d_spend as double)     as rolling_7d_spend,
        cast(rolling_30d_spend as double)    as rolling_30d_spend,
        cast(rolling_30d_mean as double)     as rolling_30d_mean,
        cast(rolling_30d_std as double)      as rolling_30d_std,
        ingested_at,
        current_timestamp                    as dbt_processed_at
    from {{ source('smartspend360_raw', 'gold_transactions') }}
    where transaction_id is not null
      and date is not null
      and amount is not null
)

select * from source
