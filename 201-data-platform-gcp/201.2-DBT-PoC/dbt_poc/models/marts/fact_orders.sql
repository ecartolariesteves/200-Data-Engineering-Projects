-- models/marts/fact_orders.sql
-- ─────────────────────────────────────────────────────────────────────────────
-- MART: fact_orders
-- Tabla de hechos principal. Consume de int_orders e int_customers.
-- Incluye columna origen para trazabilidad completa.
-- ─────────────────────────────────────────────────────────────────────────────

with orders as (

    select * from {{ ref('int_orders') }}

),

customers as (

    select * from {{ ref('int_customers') }}

),

products as (

    select * from {{ ref('stg_products') }}

),

final as (

    select
        -- Claves
        o.order_id,
        o.customer_id,
        o.product_id,

        -- Fechas
        o.order_date,
        extract(year  from o.order_date) as order_year,
        extract(month from o.order_date) as order_month,
        format_date('%Y-%m', o.order_date) as order_year_month,

        -- Atributos del pedido
        o.status,
        o.country_code                   as order_country,

        -- Origen: trazabilidad del sistema fuente
        o.origen,

        -- Atributos del cliente
        c.segment                        as customer_segment,
        c.country_code                   as customer_country,

        -- Atributos del producto
        p.product_name,
        p.category                       as product_category,

        -- Métricas financieras
        o.order_amount_eur,
        p.cost_price_eur,
        p.gross_margin_eur,
        p.gross_margin_pct,

        -- Indicadores calculados
        case
            when o.status = 'completed' then o.order_amount_eur
            else 0
        end                              as revenue_eur,

        case
            when o.status = 'cancelled' then 1
            else 0
        end                              as is_cancelled

    from orders o
    left join customers c on o.customer_id = c.customer_id
    left join products  p on o.product_id  = p.product_id

)

select * from final
