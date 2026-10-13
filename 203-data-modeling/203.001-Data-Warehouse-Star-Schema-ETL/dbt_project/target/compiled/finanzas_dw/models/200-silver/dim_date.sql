-- models/200-silver/dim_date.sql
-- Layer: Silver  |  Materialization: Table
-- Pattern: Static calendar dimension (no SCD needed)
--
-- Covers 2022-01-01 → 2025-12-31
-- Fiscal year starts January 1 (standard in Spain).
-- Includes business day flag, Spanish weekday/month names,
-- ISO week, and quarterly groupings.

with date_spine as (

    select unnest(
        generate_series(
            cast('2022-01-01' as date),
            cast('2025-12-31' as date),
            interval '1 day'
        )
    ) as date_day

),

final as (

    select
        -- PK: integer key YYYYMMDD
        cast(strftime(date_day, '%Y%m%d') as integer)           as date_key,
        cast(date_day as date)                                   as date_day,

        -- Calendar decomposition
        year(date_day)                                           as year,
        quarter(date_day)                                        as quarter_number,
        'Q' || quarter(date_day)                                 as quarter_label,
        month(date_day)                                          as month_number,
        strftime(date_day, '%B')                                 as month_name_en,

        case month(date_day)
            when  1 then 'Enero'
            when  2 then 'Febrero'
            when  3 then 'Marzo'
            when  4 then 'Abril'
            when  5 then 'Mayo'
            when  6 then 'Junio'
            when  7 then 'Julio'
            when  8 then 'Agosto'
            when  9 then 'Septiembre'
            when 10 then 'Octubre'
            when 11 then 'Noviembre'
            when 12 then 'Diciembre'
        end                                                      as month_name_es,

        -- ISO week
        isoyear(date_day)                                        as iso_year,
        week(date_day)                                           as week_number,

        -- Day
        dayofmonth(date_day)                                     as day_of_month,
        dayofweek(date_day)                                      as day_of_week,    -- 0=Sun
        dayofyear(date_day)                                      as day_of_year,

        strftime(date_day, '%A')                                 as weekday_name_en,
        case dayofweek(date_day)
            when 0 then 'Domingo'
            when 1 then 'Lunes'
            when 2 then 'Martes'
            when 3 then 'Miércoles'
            when 4 then 'Jueves'
            when 5 then 'Viernes'
            when 6 then 'Sábado'
        end                                                      as weekday_name_es,

        -- Business day flag (Mon–Fri, national holiday logic excluded)
        case when dayofweek(date_day) in (0, 6) then false
             else true
        end                                                      as is_business_day,

        case when dayofweek(date_day) in (0, 6) then 'Fin de Semana'
             else 'Día Hábil'
        end                                                      as day_type,

        -- Fiscal year — January start (Spain standard)
        year(date_day)                                           as fiscal_year,

        case quarter(date_day)
            when 1 then 'FQ1'
            when 2 then 'FQ2'
            when 3 then 'FQ3'
            when 4 then 'FQ4'
        end                                                      as fiscal_quarter,

        -- Convenience labels
        cast(strftime(date_day, '%Y-%m') as varchar)             as year_month,
        cast(strftime(date_day, '%Y-W%V') as varchar)            as year_week

    from date_spine

)

select * from final
order by date_day