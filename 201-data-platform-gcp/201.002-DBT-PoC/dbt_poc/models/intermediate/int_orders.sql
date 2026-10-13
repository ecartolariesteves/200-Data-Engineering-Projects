-- models/intermediate/int_orders.sql
-- ─────────────────────────────────────────────────────────────────────────────
-- INTERMEDIATE: Pedidos unificados de todos los orígenes
-- UNION ALL de los 11 stagings con columna 'origen' para trazabilidad
-- ─────────────────────────────────────────────────────────────────────────────

with allard     as ( select * from {{ ref('stg_allard__orders') }} ),
     as400_1    as ( select * from {{ ref('stg_as400_1__orders') }} ),
     gesbox     as ( select * from {{ ref('stg_gesbox__orders') }} ),
     hist_as400 as ( select * from {{ ref('stg_hist_as400__orders') }} ),
     nav        as ( select * from {{ ref('stg_nav__orders') }} ),
     rts_1      as ( select * from {{ ref('stg_rts_1__orders') }} ),
     rts_2      as ( select * from {{ ref('stg_rts_2__orders') }} ),
     rts_3      as ( select * from {{ ref('stg_rts_3__orders') }} ),
     sap_1      as ( select * from {{ ref('stg_sap_1__orders') }} ),
     sap_2      as ( select * from {{ ref('stg_sap_2__orders') }} ),
     sis        as ( select * from {{ ref('stg_sis__orders') }} ),

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
