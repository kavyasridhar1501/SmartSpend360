-- SmartSpend360 dbt: mart_forecast_accuracy
-- Tracks Prophet model accuracy over time (forecast vs actuals)

{{
  config(
    materialized='table',
    tags=['marts', 'forecast', 'accuracy']
  )
}}

with actuals as (
    select
        user_id,
        date,
        sum(amount_usd) as actual_spend
    from {{ ref('int_transactions_enriched') }}
    where is_debit = true
    group by user_id, date
),

forecasts as (
    select
        user_id,
        ds                          as forecast_date,
        cast(yhat as double)        as predicted_spend,
        cast(yhat_lower as double)  as predicted_lower_80,
        cast(yhat_upper as double)  as predicted_upper_80,
        cast(is_future as boolean)  as is_future_forecast
    from {{ source('smartspend360_raw', 'gold_forecasts') }}
    where is_future_forecast = false  -- Historical predictions only for accuracy
),

joined as (
    select
        a.user_id,
        a.date,
        a.actual_spend,
        f.predicted_spend,
        f.predicted_lower_80,
        f.predicted_upper_80,

        -- Error metrics
        abs(a.actual_spend - f.predicted_spend)                                 as absolute_error,
        abs(a.actual_spend - f.predicted_spend) / nullif(a.actual_spend, 0)     as absolute_pct_error,
        (a.actual_spend - f.predicted_spend)                                    as signed_error,

        -- Was actual within confidence interval?
        case
            when a.actual_spend between f.predicted_lower_80 and f.predicted_upper_80
            then true else false
        end                                                                     as within_80_ci,

        current_timestamp                                                       as dbt_processed_at

    from actuals a
    inner join forecasts f
        on a.user_id = f.user_id
        and a.date = f.forecast_date
),

with_rolling_accuracy as (
    select
        *,
        -- 7-day rolling MAPE
        avg(absolute_pct_error) over (
            partition by user_id
            order by date
            rows between 6 preceding and current row
        ) as rolling_7d_mape,

        -- 30-day rolling MAPE
        avg(absolute_pct_error) over (
            partition by user_id
            order by date
            rows between 29 preceding and current row
        ) as rolling_30d_mape,

        -- 7-day CI coverage rate
        avg(case when within_80_ci then 1.0 else 0.0 end) over (
            partition by user_id
            order by date
            rows between 6 preceding and current row
        ) as rolling_7d_ci_coverage

    from joined
)

select
    user_id,
    date,
    round(actual_spend, 2)          as actual_spend,
    round(predicted_spend, 2)       as predicted_spend,
    round(predicted_lower_80, 2)    as predicted_lower_80,
    round(predicted_upper_80, 2)    as predicted_upper_80,
    round(absolute_error, 2)        as absolute_error,
    round(absolute_pct_error * 100, 1) as mape_pct,
    round(signed_error, 2)          as signed_error,
    within_80_ci,
    round(rolling_7d_mape * 100, 1)     as rolling_7d_mape_pct,
    round(rolling_30d_mape * 100, 1)    as rolling_30d_mape_pct,
    round(rolling_7d_ci_coverage * 100, 1) as rolling_7d_ci_coverage_pct,
    dbt_processed_at
from with_rolling_accuracy
order by user_id, date desc
