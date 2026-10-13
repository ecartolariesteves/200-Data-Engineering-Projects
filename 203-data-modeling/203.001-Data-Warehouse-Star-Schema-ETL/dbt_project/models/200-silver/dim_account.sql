-- models/silver/dim_account.sql
-- Layer: Silver  |  Materialization: Table
-- Pattern: SCD Type 2
--
-- Tracks historical changes to account attributes (segment, risk_level).
-- Each row represents one VERSION of an account.
-- A single account can have multiple rows with non-overlapping validity ranges.
--
-- Key columns:
--   account_key   → surrogate key (PK)
--   account_id    → natural/business key (from source)
--   valid_from    → date this version became active
--   valid_to      → date this version was superseded (NULL = current)
--   is_current    → boolean flag for easy filtering

with accounts as (

    select * from {{ ref('stg_accounts') }}

),

changes as (

    select * from {{ ref('stg_account_changes') }}

),

-- Build one row per (account_id, effective_date) combining
-- the original record + any subsequent changes
account_versions as (

    -- Version 0: original record at open_date
    select
        account_id,
        customer_name,
        email,
        phone,
        branch,
        segment                             as segment,
        risk_level                          as risk_level,
        product_id,
        open_date,
        status,
        credit_limit,
        open_date                           as valid_from,
        1                                   as version_number

    from accounts

    union all

    -- Version N: each subsequent change event
    select
        a.account_id,
        a.customer_name,
        a.email,
        a.phone,
        a.branch,
        c.new_segment                       as segment,
        c.new_risk_level                    as risk_level,
        a.product_id,
        a.open_date,
        a.status,
        a.credit_limit,
        c.change_date                       as valid_from,
        row_number() over (
            partition by a.account_id
            order by c.change_date
        ) + 1                               as version_number

    from accounts a
    inner join changes c
        on a.account_id = c.account_id

),

-- Assign valid_to = the next version's valid_from - 1 day
versioned as (

    select
        account_id,
        customer_name,
        email,
        phone,
        branch,
        segment,
        risk_level,
        product_id,
        open_date,
        status,
        credit_limit,
        valid_from,
        version_number,

        -- valid_to: start of the next version, or NULL if current
        lead(valid_from) over (
            partition by account_id
            order by valid_from
        ) - interval '1 day'               as valid_to,

        -- is_current: true only for the latest version
        case
            when lead(valid_from) over (
                partition by account_id
                order by valid_from
            ) is null then true
            else false
        end                                 as is_current

    from account_versions

),

-- Surrogate key using md5 hash of natural key + version
final as (

    select
        md5(account_id || '-' || cast(valid_from as varchar)) as account_key,
        account_id,
        customer_name,
        email,
        phone,
        branch,
        segment,
        risk_level,
        product_id,
        open_date,
        status,
        credit_limit,
        version_number,
        valid_from,
        valid_to,
        is_current,
        current_timestamp                   as _updated_at

    from versioned

)

select * from final
