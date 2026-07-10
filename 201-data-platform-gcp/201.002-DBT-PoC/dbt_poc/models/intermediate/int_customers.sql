-- models/intermediate/int_customers.sql
-- ─────────────────────────────────────────────────────────────────────────────
-- INTERMEDIATE: Clientes unificados de todos los orígenes
-- UNION ALL de los 11 stagings con columna 'origen' para trazabilidad
-- Materialización: view (sin coste de almacenamiento)
-- ─────────────────────────────────────────────────────────────────────────────

with allard     as ( select * from {{ ref('stg_allard__customers') }} ),
     as400_1    as ( select * from {{ ref('stg_as400_1__customers') }} ),
     gesbox     as ( select * from {{ ref('stg_gesbox__customers') }} ),
     hist_as400 as ( select * from {{ ref('stg_hist_as400__customers') }} ),
     nav        as ( select * from {{ ref('stg_nav__customers') }} ),
     rts_1      as ( select * from {{ ref('stg_rts_1__customers') }} ),
     rts_2      as ( select * from {{ ref('stg_rts_2__customers') }} ),
     rts_3      as ( select * from {{ ref('stg_rts_3__customers') }} ),
     sap_1      as ( select * from {{ ref('stg_sap_1__customers') }} ),
     sap_2      as ( select * from {{ ref('stg_sap_2__customers') }} ),
     sis        as ( select * from {{ ref('stg_sis__customers') }} ),

final as (
    select * from allard
    union all
    select * from as400_1
    union all
    select * from gesbox
    union all
    select * from hist_as400
    union all
    select * from nav
    union all
    select * from rts_1
    union all
    select * from rts_2
    union all
    select * from rts_3
    union all
    select * from sap_1
    union all
    select * from sap_2
    union all
    select * from sis
)

select * from final
