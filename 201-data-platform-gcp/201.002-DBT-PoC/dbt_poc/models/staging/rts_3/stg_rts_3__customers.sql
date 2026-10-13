-- models/staging/rts_3/stg_rts_3__customers.sql
-- Normalización de clientes del origen: RTS-3

with source as (
    select * from {{ source('raw_rts_3', 'customers') }}
),

staged as (
    select
        cast(customer_id  as string)  as customer_id,
        lower(trim(email))            as email,
        upper(trim(country))          as country_code,
        lower(trim(segment))          as segment,
        cast(signup_date  as date)    as signup_date,
        'RTS-3'                    as origen,
        current_timestamp()           as _loaded_at
    from source
)

select * from staged
