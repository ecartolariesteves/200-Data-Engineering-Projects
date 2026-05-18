-- models/staging/rts_3/stg_rts_3__orders.sql
-- Normalización de pedidos del origen: RTS-3

with source as (
    select * from {{ source('raw_rts_3', 'orders') }}
),

staged as (
    select
        cast(order_id    as string)   as order_id,
        cast(customer_id as string)   as customer_id,
        cast(product_id  as string)   as product_id,
        cast(order_date  as date)     as order_date,
        lower(trim(status))           as status,
        upper(trim(country))          as country_code,
        cast(amount      as numeric)  as order_amount_eur,
        'RTS-3'                    as origen,
        current_timestamp()           as _loaded_at
    from source
)

select * from staged
