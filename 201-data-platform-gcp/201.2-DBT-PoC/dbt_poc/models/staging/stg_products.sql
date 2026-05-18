-- models/staging/stg_products.sql
-- ─────────────────────────────────────────────────────────────────────────────
-- STAGING: Products
-- Limpia y tipifica la tabla RAW de productos.
-- ─────────────────────────────────────────────────────────────────────────────

with source as (

    select * from {{ source('raw', 'products') }}

),

staged as (

    select
        -- Identificadores
        cast(product_id as string)       as product_id,

        -- Atributos
        trim(product_name)               as product_name,
        lower(trim(category))            as category,
        upper(trim(supplier_country))    as supplier_country_code,

        -- Métricas
        cast(unit_price  as numeric)     as unit_price_eur,
        cast(cost_price  as numeric)     as cost_price_eur,

        -- Margen calculado en staging
        round(
            cast(unit_price as numeric) - cast(cost_price as numeric),
            2
        )                                as gross_margin_eur,

        round(
            safe_divide(
                cast(unit_price as numeric) - cast(cost_price as numeric),
                cast(unit_price as numeric)
            ) * 100,
            2
        )                                as gross_margin_pct,

        -- Metadatos
        current_timestamp()              as _loaded_at

    from source

)

select * from staged
