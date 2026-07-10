-- models/staging/sap_1/stg_sap_1__customers.sql
-- Normalización de clientes del origen: SAP-1

with source as (
    select * from {{ source('raw_sap_1', 'customers') }}
),

staged as (
    select
        cast(customer_id  as string)  as customer_id,
        lower(trim(email))            as email,
        upper(trim(country))          as country_code,
        lower(trim(segment))          as segment,
        cast(signup_date  as date)    as signup_date,
        'SAP-1'                    as origen,
        current_timestamp()           as _loaded_at
    from source
)

select * from staged
