-- models/staging/nav/stg_nav__customers.sql
-- Normalización de clientes del origen: NAV

with source as (
    select * from {{ source('raw_nav', 'customers') }}
),

staged as (
    select
        cast(customer_id  as string)  as customer_id,
        lower(trim(email))            as email,
        upper(trim(country))          as country_code,
        lower(trim(segment))          as segment,
        cast(signup_date  as date)    as signup_date,
        'NAV'                    as origen,
        current_timestamp()           as _loaded_at
    from source
)

select * from staged
