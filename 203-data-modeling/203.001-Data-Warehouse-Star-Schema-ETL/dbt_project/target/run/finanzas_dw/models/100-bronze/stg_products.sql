
  
  create view "finanzas_dw"."main_bronze"."stg_products__dbt_tmp" as (
    -- models/100-bronze/stg_products.sql
-- Layer: Bronze  |  Materialization: View

with source as (

    select * from read_csv_auto(
        'data/raw/products.csv',
        header = true
    )

),

typed as (

    select
        product_id                                  as product_id,
        product_name                                as product_name,
        product_category                            as product_category,
        cast(interest_rate_pct as decimal(8,4))     as interest_rate_pct,
        cast(fee_rate_pct      as decimal(8,4))     as fee_rate_pct,
        cast(is_active         as boolean)          as is_active,
        cast(created_at        as date)             as created_at,

        current_timestamp                           as _loaded_at

    from source

)

select * from typed
  );
