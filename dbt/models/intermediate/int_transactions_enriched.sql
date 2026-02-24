-- SmartSpend360 dbt: int_transactions_enriched
-- Joins FX rates to transactions and adds USD normalization

{{
  config(
    materialized='table',
    tags=['intermediate', 'transactions']
  )
}}

with transactions as (
    select * from {{ ref('stg_transactions') }}
),

fx_rates as (
    select
        date,
        target_currency,
        usd_to_target,
        target_to_usd
    from {{ ref('stg_fx_rates') }}
    where base_currency = 'USD'
),

enriched as (
    select
        t.transaction_id,
        t.account_id,
        t.user_id,
        t.amount,
        t.amount_abs,
        t.is_debit,
        t.date,
        t.transaction_date,
        t.day_of_week,
        t.week_of_month,
        t.is_weekend,
        t.month,
        t.year,
        t.merchant_name,
        t.merchant_normalized,
        t.category,
        t.payment_channel,
        t.pending,

        -- Default to USD if no FX data needed
        coalesce(t.iso_currency_code, 'USD')        as iso_currency_code,
        coalesce(fx.usd_to_target, 1.0)             as fx_rate_usd_to_txn_currency,
        coalesce(fx.target_to_usd, 1.0)             as fx_rate_txn_to_usd,

        -- Normalize amount to USD
        case
            when coalesce(t.iso_currency_code, 'USD') = 'USD' then t.amount_abs
            else t.amount_abs * coalesce(fx.target_to_usd, 1.0)
        end                                          as amount_usd,

        t.rolling_7d_spend,
        t.rolling_30d_spend,
        t.rolling_30d_mean,
        t.rolling_30d_std,
        t.ingested_at,
        t.dbt_processed_at

    from transactions t
    left join fx_rates fx
        on t.date = fx.date
        and coalesce(t.iso_currency_code, 'USD') = fx.target_currency
)

select * from enriched
