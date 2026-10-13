-- models/staging/as400_1/stg_as400_1__customers.sql
-- Normalización de clientes del origen: AS400-1

with source as (
    select * from {{ source('raw_as400_1', 'customers') }}
),

staged as (
    select
        cast(customer_id  as string)  as customer_id,
        lower(trim(email))            as email,
        upper(trim(country))          as country_code,
        lower(trim(segment))          as segment,
        cast(signup_date  as date)    as signup_date,
        'AS400-1'                    as origen,
        current_timestamp()           as _loaded_at
    from source
)

select * from staged
