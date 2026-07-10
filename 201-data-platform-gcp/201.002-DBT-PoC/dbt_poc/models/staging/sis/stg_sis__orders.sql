-- models/staging/sis/stg_sis__orders.sql
-- Normalización de pedidos del origen: SIS

with source as (
    select * from {{ source('raw_sis', 'orders') }}
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
        'SIS'                    as origen,
        current_timestamp()           as _loaded_at
    from source
)

select * from staged
