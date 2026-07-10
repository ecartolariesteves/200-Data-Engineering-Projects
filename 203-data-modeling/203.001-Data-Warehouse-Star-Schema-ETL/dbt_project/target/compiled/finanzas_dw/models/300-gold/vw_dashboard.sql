-- models/300-gold/vw_dashboard.sql
-- Layer: Gold  |  Materialization: Table
-- Purpose: Pre-aggregated flat view optimized for Evidence.dev dashboard.
--          One row per calendar month — zero joins needed downstream.

with kpis as (

    select * from "finanzas_dw"."main_gold"."mart_kpis"

),

monthly_totals as (

    select
        year,
        month_number,
        month_name_es,
        quarter_label,
        fiscal_year,
        fiscal_quarter,
        sum(total_transactions)             as total_transactions,
        sum(active_accounts)                as active_accounts,
        sum(total_credits)                  as total_credits,
        sum(total_debits)                   as total_debits,
        sum(total_fees_collected)           as total_fees,
        sum(net_flow)                       as net_flow,
        avg(avg_transaction_amount)         as avg_txn_amount,
        sum(txns_app)                       as txns_digital,
        round(
            sum(txns_app)::float /
            nullif(sum(total_transactions), 0) * 100, 2
        )                                   as digital_adoption_pct

    from kpis
    group by 1, 2, 3, 4, 5, 6

)

select
    year,
    month_number,
    month_name_es,
    quarter_label,
    fiscal_year,
    fiscal_quarter,

    year || '-' || lpad(cast(month_number as varchar), 2, '0') as year_month,

    total_transactions,
    active_accounts,
    round(total_credits,   2)               as total_credits,
    round(total_debits,    2)               as total_debits,
    round(total_fees,      2)               as total_fees,
    round(net_flow,        2)               as net_flow,
    round(avg_txn_amount,  2)               as avg_txn_amount,
    digital_adoption_pct

from monthly_totals
order by year, month_number