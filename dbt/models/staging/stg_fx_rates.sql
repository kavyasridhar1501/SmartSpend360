-- SmartSpend360 dbt: stg_fx_rates
-- Reads daily USD FX rates from S3 silver layer via Athena

{{
  config(
    materialized='view',
    tags=['staging', 'fx']
  )
}}

with source as (
    select
        date,
        base_currency,
        target_currency,
        cast(rate as double)            as rate,
        cast(usd_to_target as double)   as usd_to_target,
        cast(target_to_usd as double)   as target_to_usd,
        ingested_at,
        current_timestamp               as dbt_processed_at
    from {{ source('smartspend360_raw', 'silver_fx_rates') }}
    where date is not null
      and base_currency is not null
      and target_currency is not null
      and rate > 0
),

deduplicated as (
    select *,
        row_number() over (
            partition by date, base_currency, target_currency
            order by ingested_at desc
        ) as rn
    from source
)

select * from deduplicated where rn = 1
