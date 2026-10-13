-- models/staging/stg_customers.sql
-- ─────────────────────────────────────────────────────────────────────────────
-- STAGING: Customers
-- Limpia y tipifica la tabla RAW de clientes.
-- ─────────────────────────────────────────────────────────────────────────────

with source as (

    select * from {{ source('raw', 'customers') }}

),

staged as (

    select
        -- Identificadores
        cast(customer_id as string)      as customer_id,

        -- Atributos personales (nunca PII en marts)
        trim(first_name)                 as first_name,
        trim(last_name)                  as last_name,
        lower(trim(email))               as email,
        upper(trim(country))             as country_code,

        -- Segmentación
        lower(trim(segment))             as segment,

        -- Fechas
        cast(signup_date as date)        as signup_date,

        -- Metadatos
        current_timestamp()              as _loaded_at

    from source

)

select * from staged
