-- models/200-silver/dim_product.sql
-- Layer: Silver  |  Materialization: Table
-- Pattern: SCD Type 2
--
-- Tracks product attribute changes (interest rates, fees, active status).
-- Two snapshots are simulated: original rates (2022-01-01) and a rate
-- revision (2023-07-01), demonstrating the SCD2 pattern.

with products as (

    select * from {{ ref('stg_products') }}

),

-- Two version snapshots per product
product_versions as (

    -- Version 1: original rates at launch
    select
        product_id,
        product_name,
        product_category,
        interest_rate_pct,
        fee_rate_pct,
        is_active,
        cast('2022-01-01' as date)          as valid_from,
        1                                   as version_number
    from products

    union all

    -- Version 2: rate revision mid-2023
    select
        product_id,
        product_name,
        product_category,
        round(interest_rate_pct * 1.10, 4)  as interest_rate_pct,
        round(fee_rate_pct      * 0.95, 4)  as fee_rate_pct,
        is_active,
        cast('2023-07-01' as date)          as valid_from,
        2                                   as version_number
    from products

),

versioned as (

    select
        product_id,
        product_name,
        product_category,
        interest_rate_pct,
        fee_rate_pct,
        is_active,
        valid_from,
        version_number,

        lead(valid_from) over (
            partition by product_id
            order by valid_from
        ) - interval '1 day'               as valid_to,

        case
            when lead(valid_from) over (
                partition by product_id
                order by valid_from
            ) is null then true
            else false
        end                                 as is_current

    from product_versions

),

final as (

    select
        md5(product_id || '-' || cast(valid_from as varchar)) as product_key,
        product_id,
        product_name,
        product_category,
        interest_rate_pct,
        fee_rate_pct,
        is_active,
        version_number,
        valid_from,
        valid_to,
        is_current,
        current_timestamp                   as _updated_at

    from versioned

)

select * from final
