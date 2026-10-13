-- models/gold/fact_transactions.sql
-- Layer: Gold  |  Materialization: Table
-- Pattern: Star Schema Fact Table (Transaction Grain)
--
-- One row per financial transaction.
-- Joins to dimensions using the versioned surrogate keys (SCD Type 2 aware):
--   dim_account  → account version active ON the transaction date
--   dim_product  → product version active ON the transaction date
--   dim_date     → calendar dimension
--
-- This is the core fact table. All KPI marts derive from here.

with txns as (

    select * from "finanzas_dw"."main_bronze"."stg_transactions"

),

-- Resolve account version active on the transaction date (SCD2 join)
dim_account as (

    select * from "finanzas_dw"."main_silver"."dim_account"

),

-- Resolve product version active on the transaction date (SCD2 join)
dim_product as (

    select * from "finanzas_dw"."main_silver"."dim_product"

),

dim_date as (

    select * from "finanzas_dw"."main_silver"."dim_date"

),

-- Join accounts: get the account_key for the version valid at txn date
txns_with_account as (

    select
        t.*,
        a.account_key,
        a.segment                   as account_segment,
        a.risk_level                as account_risk_level,
        a.branch                    as account_branch,
        a.product_id                as account_product_id

    from txns t
    left join dim_account a
        on  t.account_id    = a.account_id
        and t.transaction_date >= a.valid_from
        and (t.transaction_date <= a.valid_to or a.valid_to is null)

),

-- Join products on the account's product for the valid rate at txn date
txns_with_product as (

    select
        ta.*,
        p.product_key,
        p.product_name,
        p.product_category,
        p.interest_rate_pct,
        p.fee_rate_pct          as product_fee_rate_pct

    from txns_with_account ta
    left join dim_product p
        on  ta.account_product_id   = p.product_id
        and ta.transaction_date    >= p.valid_from
        and (ta.transaction_date   <= p.valid_to or p.valid_to is null)

),

-- Join date dimension
final as (

    select
        -- Surrogate fact key
        md5(tp.transaction_id)              as transaction_key,

        -- Foreign keys
        tp.account_key,
        tp.product_key,
        d.date_key,

        -- Degenerate dimensions (attributes of the transaction itself)
        tp.transaction_id,
        tp.account_id,
        tp.transaction_type,
        tp.direction,
        tp.currency,
        tp.channel,
        tp.status,

        -- Additive measures
        tp.amount,
        tp.fee_amount,
        tp.net_amount,
        tp.exchange_rate,

        -- Derived measures
        case tp.direction
            when 'Crédito' then tp.net_amount
            else 0.0
        end                                 as credit_amount,

        case tp.direction
            when 'Débito'  then tp.net_amount
            else 0.0
        end                                 as debit_amount,

        -- Contextual attributes (avoid joins downstream)
        tp.account_segment,
        tp.account_risk_level,
        tp.account_branch,
        tp.product_name,
        tp.product_category,
        d.year,
        d.quarter_label,
        d.month_number,
        d.month_name_es,
        d.is_business_day,
        d.fiscal_year,
        d.fiscal_quarter,

        tp.transaction_date,
        tp._loaded_at

    from txns_with_product tp
    left join dim_date d
        on tp.transaction_date = d.date_day

    -- Only completed transactions for financial reporting
    where tp.status = 'Completada'

)

select * from final