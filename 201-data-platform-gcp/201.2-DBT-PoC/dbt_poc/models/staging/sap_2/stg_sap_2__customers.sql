-- models/staging/sap_2/stg_sap_2__customers.sql
-- Normalización de clientes del origen: SAP-2

with source as (
    select * from {{ source('raw_sap_2', 'customers') }}
),

staged as (
    select
        cast(customer_id  as string)  as customer_id,
        lower(trim(email))            as email,
        upper(trim(country))          as country_code,
        lower(trim(segment))          as segment,
        cast(signup_date  as date)    as signup_date,
        'SAP-2'                    as origen,
        current_timestamp()           as _loaded_at
    from source
)

select * from staged
