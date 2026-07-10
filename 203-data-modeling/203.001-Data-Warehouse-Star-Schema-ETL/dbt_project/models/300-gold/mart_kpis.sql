-- models/gold/mart_kpis.sql
-- Layer: Gold  |  Materialization: Table
-- Grain: one row per (year, month, segment, product_category)
--
-- Business KPIs ready for BI consumption.
-- Derived entirely from fact_transactions — no raw source access.

with fact as (

    select * from {{ ref('fact_transactions') }}

),

monthly_agg as (

    select
        year,
        month_number,
        month_name_es,
        quarter_label,
        fiscal_year,
        fiscal_quarter,
        account_segment,
        account_branch,
        product_category,

        -- Volume KPIs
        count(*)                                    as total_transactions,
        count(distinct account_id)                  as active_accounts,

        -- Revenue KPIs
        sum(credit_amount)                          as total_credits,
        sum(debit_amount)                           as total_debits,
        sum(fee_amount)                             as total_fees_collected,
        sum(net_amount)                             as net_flow,

        -- Averages
        avg(amount)                                 as avg_transaction_amount,
        avg(fee_amount)                             as avg_fee_amount,

        -- Channel mix
        count(*) filter (where channel = 'App Móvil')    as txns_app,
        count(*) filter (where channel = 'Web')          as txns_web,
        count(*) filter (where channel = 'ATM')          as txns_atm,
        count(*) filter (where channel = 'Sucursal')     as txns_branch,
        count(*) filter (where channel = 'Homebanking')  as txns_homebanking,

        -- Risk distribution
        count(*) filter (where account_risk_level = 'Bajo')   as txns_risk_low,
        count(*) filter (where account_risk_level = 'Medio')  as txns_risk_medium,
        count(*) filter (where account_risk_level = 'Alto')   as txns_risk_high,

        -- Currency breakdown
        sum(amount) filter (where currency = 'ARS')     as amount_ars,
        sum(amount) filter (where currency = 'USD')     as amount_usd,
        sum(amount) filter (where currency = 'EUR')     as amount_eur

    from fact
    group by 1,2,3,4,5,6,7,8,9

)

select
    *,
    -- Derived ratios
    round(total_fees_collected / nullif(total_credits, 0) * 100, 4) as fee_rate_pct,
    round(txns_app::float / nullif(total_transactions, 0) * 100, 2) as digital_pct

from monthly_agg
order by year, month_number, account_segment
