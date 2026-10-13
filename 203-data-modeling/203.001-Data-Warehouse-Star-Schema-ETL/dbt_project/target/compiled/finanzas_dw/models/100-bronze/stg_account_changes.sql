-- models/100-bronze/stg_account_changes.sql
-- Layer: Bronze  |  Materialization: View
-- Purpose: Source feed for SCD Type 2 processing in Silver layer.

with source as (

    select * from read_csv_auto(
        'data/raw/account_changes.csv',
        header     = true,
        dateformat = '%Y-%m-%d'
    )

),

typed as (

    select
        change_id                           as change_id,
        account_id                          as account_id,
        cast(change_date   as date)         as change_date,
        field_changed                       as field_changed,
        old_value                           as old_value,
        new_value                           as new_value,
        new_segment                         as new_segment,
        new_risk_level                      as new_risk_level,
        changed_by                          as changed_by,

        current_timestamp                   as _loaded_at

    from source

)

select * from typed