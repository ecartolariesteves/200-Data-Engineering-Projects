
  
  create view "finanzas_dw"."main_bronze"."stg_transactions__dbt_tmp" as (
    -- models/100-bronze/stg_transactions.sql
-- Layer: Bronze  |  Materialization: View
-- Purpose: Read raw CSV into DuckDB with light typing only.
--          No business logic. No filtering. No joins.

with source as (

    select * from read_csv_auto(
        'data/raw/transactions.csv',
        header     = true,
        dateformat = '%Y-%m-%d'
    )

),

typed as (

    select
        transaction_id                              as transaction_id,
        account_id                                  as account_id,
        cast(transaction_date as date)              as transaction_date,
        transaction_type                            as transaction_type,
        direction                                   as direction,
        cast(amount          as decimal(18,2))      as amount,
        cast(fee_amount      as decimal(18,2))      as fee_amount,
        cast(net_amount      as decimal(18,2))      as net_amount,
        currency                                    as currency,
        cast(exchange_rate   as decimal(12,6))      as exchange_rate,
        channel                                     as channel,
        status                                      as status,
        description                                 as description,
        reference_id                                as reference_id,
        cast(created_at      as date)               as created_at,

        -- Audit column
        current_timestamp                           as _loaded_at

    from source

)

select * from typed
  );
