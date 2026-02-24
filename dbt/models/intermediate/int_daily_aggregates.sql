-- SmartSpend360 dbt: int_daily_aggregates
-- Daily rollups per user for mart consumption

{{
  config(
    materialized='table',
    tags=['intermediate', 'aggregates']
  )
}}

with enriched as (
    select * from {{ ref('int_transactions_enriched') }}
    where is_debit = true  -- Only count outgoing spend
),

daily_totals as (
    select
        user_id,
        date,
        transaction_date,
        year,
        month,
        day_of_week,
        is_weekend,

        -- Volume metrics
        sum(amount_usd)                     as daily_spend_usd,
        sum(amount_abs)                     as daily_spend_native,
        count(transaction_id)               as transaction_count,
        count(distinct merchant_normalized) as unique_merchant_count,
        max(amount_usd)                     as max_transaction_usd,
        avg(amount_usd)                     as avg_transaction_usd,

        -- Category breakdowns
        sum(case when category = 'Food'          then amount_usd else 0 end) as food_spend,
        sum(case when category = 'Transport'     then amount_usd else 0 end) as transport_spend,
        sum(case when category = 'Entertainment' then amount_usd else 0 end) as entertainment_spend,
        sum(case when category = 'Healthcare'    then amount_usd else 0 end) as healthcare_spend,
        sum(case when category = 'Housing'       then amount_usd else 0 end) as housing_spend,
        sum(case when category = 'Other'         then amount_usd else 0 end) as other_spend,

        -- Category ratios
        sum(case when category = 'Food'          then amount_usd else 0 end) / nullif(sum(amount_usd), 0) as food_ratio,
        sum(case when category = 'Transport'     then amount_usd else 0 end) / nullif(sum(amount_usd), 0) as transport_ratio,
        sum(case when category = 'Entertainment' then amount_usd else 0 end) / nullif(sum(amount_usd), 0) as entertainment_ratio,
        sum(case when category = 'Healthcare'    then amount_usd else 0 end) / nullif(sum(amount_usd), 0) as healthcare_ratio,
        sum(case when category = 'Housing'       then amount_usd else 0 end) / nullif(sum(amount_usd), 0) as housing_ratio,

        -- Merchant diversity (unique / total)
        count(distinct merchant_normalized) * 1.0 / nullif(count(transaction_id), 0) as merchant_diversity_score

    from enriched
    group by 1, 2, 3, 4, 5, 6, 7
),

with_rolling as (
    select
        *,
        -- 7-day rolling spend
        sum(daily_spend_usd) over (
            partition by user_id
            order by transaction_date
            rows between 6 preceding and current row
        ) as rolling_7d_spend,

        -- 30-day rolling spend
        sum(daily_spend_usd) over (
            partition by user_id
            order by transaction_date
            rows between 29 preceding and current row
        ) as rolling_30d_spend,

        -- 30-day rolling avg
        avg(daily_spend_usd) over (
            partition by user_id
            order by transaction_date
            rows between 29 preceding and current row
        ) as rolling_30d_avg,

        -- Week-over-week comparison
        lag(daily_spend_usd, 7) over (
            partition by user_id
            order by transaction_date
        ) as spend_7d_ago

    from daily_totals
)

select
    *,
    case
        when spend_7d_ago is not null and spend_7d_ago > 0
        then (daily_spend_usd - spend_7d_ago) / spend_7d_ago
        else null
    end as wow_change_pct
from with_rolling
