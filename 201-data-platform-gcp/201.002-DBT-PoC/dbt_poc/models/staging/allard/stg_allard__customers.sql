-- models/staging/allard/stg_allard__customers.sql
-- Normalización de clientes del origen: ALLARD

with source as (
    select * from {{ source('raw_allard', 'customers') }}
),

staged as (
    select
        cast(customer_id  as string)  as customer_id,
        lower(trim(email))            as email,
        upper(trim(country))          as country_code,
        lower(trim(segment))          as segment,
        cast(signup_date  as date)    as signup_date,
        'ALLARD'                    as origen,
        current_timestamp()           as _loaded_at
    from source
)

select * from staged
