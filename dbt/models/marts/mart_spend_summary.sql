-- SmartSpend360 dbt: mart_spend_summary
-- Final spend metrics table for API and dashboard consumption

{{
  config(
    materialized='table',
    tags=['marts', 'spend']
  )
}}

with daily as (
    select * from {{ ref('int_daily_aggregates') }}
),

monthly_summary as (
    select
        user_id,
        year,
        month,
        sum(daily_spend_usd)        as monthly_spend_usd,
        sum(transaction_count)      as monthly_transaction_count,
        avg(daily_spend_usd)        as avg_daily_spend,
        max(daily_spend_usd)        as peak_daily_spend,
        min(daily_spend_usd)        as min_daily_spend,
        count(distinct date)        as active_days,

        -- Category totals
        sum(food_spend)             as monthly_food_spend,
        sum(transport_spend)        as monthly_transport_spend,
        sum(entertainment_spend)    as monthly_entertainment_spend,
        sum(healthcare_spend)       as monthly_healthcare_spend,
        sum(housing_spend)          as monthly_housing_spend,
        sum(other_spend)            as monthly_other_spend

    from daily
    group by user_id, year, month
),

with_prior_month as (
    select
        m.*,
        lag(m.monthly_spend_usd) over (
            partition by m.user_id
            order by m.year, m.month
        ) as prior_month_spend,
        lag(m.monthly_food_spend) over (
            partition by m.user_id
            order by m.year, m.month
        ) as prior_food_spend,
        lag(m.monthly_transport_spend) over (
            partition by m.user_id
            order by m.year, m.month
        ) as prior_transport_spend

    from monthly_summary m
),

final as (
    select
        user_id,
        year,
        month,
        date_format(date_parse(concat(cast(year as varchar), '-', lpad(cast(month as varchar), 2, '0'), '-01'), '%Y-%m-%d'), '%Y-%m') as year_month,
        monthly_spend_usd,
        monthly_transaction_count,
        round(avg_daily_spend, 2)           as avg_daily_spend_usd,
        peak_daily_spend,
        active_days,

        -- MoM changes
        prior_month_spend,
        case
            when prior_month_spend > 0
            then round((monthly_spend_usd - prior_month_spend) / prior_month_spend * 100, 1)
            else null
        end                                 as mom_spend_change_pct,

        -- Category amounts
        round(monthly_food_spend, 2)            as food_spend,
        round(monthly_transport_spend, 2)       as transport_spend,
        round(monthly_entertainment_spend, 2)   as entertainment_spend,
        round(monthly_healthcare_spend, 2)      as healthcare_spend,
        round(monthly_housing_spend, 2)         as housing_spend,
        round(monthly_other_spend, 2)           as other_spend,

        -- Category percentages
        round(monthly_food_spend / nullif(monthly_spend_usd, 0) * 100, 1)            as food_pct,
        round(monthly_transport_spend / nullif(monthly_spend_usd, 0) * 100, 1)       as transport_pct,
        round(monthly_entertainment_spend / nullif(monthly_spend_usd, 0) * 100, 1)   as entertainment_pct,
        round(monthly_healthcare_spend / nullif(monthly_spend_usd, 0) * 100, 1)      as healthcare_pct,
        round(monthly_housing_spend / nullif(monthly_spend_usd, 0) * 100, 1)         as housing_pct,
        round(monthly_other_spend / nullif(monthly_spend_usd, 0) * 100, 1)           as other_pct,

        -- Burn rate (annualized)
        round(avg_daily_spend * 30, 2)      as monthly_burn_rate,

        current_timestamp                   as dbt_updated_at

    from with_prior_month
)

select * from final
order by user_id, year desc, month desc
