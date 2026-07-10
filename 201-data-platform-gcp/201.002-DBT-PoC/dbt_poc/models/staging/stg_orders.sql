-- models/staging/stg_orders.sql
-- ─────────────────────────────────────────────────────────────────────────────
-- STAGING: Orders
-- Limpia y tipifica la tabla RAW de pedidos.
-- Materialización: VIEW (sin coste de almacenamiento)
-- ─────────────────────────────────────────────────────────────────────────────

with source as (

    select * from {{ source('raw', 'orders') }}

),

staged as (

    select
        -- Identificadores
        cast(order_id    as string)  as order_id,
        cast(customer_id as string)  as customer_id,
        cast(product_id  as string)  as product_id,

        -- Fechas
        cast(order_date as date)     as order_date,

        -- Atributos
        lower(trim(status))          as status,
        upper(trim(country))         as country_code,

        -- Métricas
        cast(amount as numeric)      as order_amount_eur,

        -- Metadatos de auditoría
        current_timestamp()          as _loaded_at

    from source

)

select * from staged
