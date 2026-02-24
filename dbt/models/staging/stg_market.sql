-- SmartSpend360 dbt: stg_market
-- Reads SPY/QQQ/VTI prices from S3 silver layer via Athena

{{
  config(
    materialized='view',
    tags=['staging', 'market']
  )
}}

with source as (
    select
        symbol,
        date,
        cast(open as double)    as open_price,
        cast(high as double)    as high_price,
        cast(low as double)     as low_price,
        cast(close as double)   as close_price,
        cast(volume as bigint)  as volume,
        ingested_at,
        current_timestamp       as dbt_processed_at
    from {{ source('smartspend360_raw', 'silver_market') }}
    where symbol is not null
      and date is not null
      and close is not null
      and close > 0
)

select * from source
