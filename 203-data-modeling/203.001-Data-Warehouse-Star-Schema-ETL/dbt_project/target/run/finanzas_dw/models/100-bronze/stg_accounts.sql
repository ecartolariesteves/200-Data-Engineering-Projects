
  
  create view "finanzas_dw"."main_bronze"."stg_accounts__dbt_tmp" as (
    -- models/100-bronze/stg_accounts.sql
-- Layer: Bronze  |  Materialization: View

with source as (

    select * from read_csv_auto(
        'data/raw/accounts.csv',
        header     = true,
        dateformat = '%Y-%m-%d'
    )

),

typed as (

    select
        account_id                              as account_id,
        customer_name                           as customer_name,
        email                                   as email,
        phone                                   as phone,
        branch                                  as branch,
        segment                                 as segment,
        risk_level                              as risk_level,
        product_id                              as product_id,
        cast(open_date    as date)              as open_date,
        status                                  as status,
        cast(credit_limit as decimal(18,2))     as credit_limit,
        cast(balance      as decimal(18,2))     as balance,
        cast(created_at   as date)              as created_at,
        cast(updated_at   as date)              as updated_at,

        current_timestamp                       as _loaded_at

    from source

)

select * from typed
  );
