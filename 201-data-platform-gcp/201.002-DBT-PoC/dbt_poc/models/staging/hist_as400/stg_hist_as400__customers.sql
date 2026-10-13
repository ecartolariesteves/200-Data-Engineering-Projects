-- models/staging/hist_as400/stg_hist_as400__customers.sql
-- Normalización de clientes del origen: Hist-AS400

with source as (
    select * from {{ source('raw_hist_as400', 'customers') }}
),

staged as (
    select
        cast(customer_id  as string)  as customer_id,
        lower(trim(email))            as email,
        upper(trim(country))          as country_code,
        lower(trim(segment))          as segment,
        cast(signup_date  as date)    as signup_date,
        'Hist-AS400'                    as origen,
        current_timestamp()           as _loaded_at
    from source
)

select * from staged
