-- models/marts/dim_customers.sql
-- ─────────────────────────────────────────────────────────────────────────────
-- MART: dim_customers
-- Dimensión de clientes con métricas agregadas de comportamiento.
-- Consume de int_customers (UNION ALL de los 11 orígenes) — incluye col. origen
-- ─────────────────────────────────────────────────────────────────────────────

with customers as (

    select * from {{ ref('int_customers') }}

),

orders as (

    select * from {{ ref('int_orders') }}

),

customer_orders as (

    select
        customer_id,
        count(*)                                    as total_orders,
        countif(status = 'completed')               as completed_orders,
        countif(status = 'cancelled')               as cancelled_orders,
        sum(case when status = 'completed'
                 then order_amount_eur else 0 end)  as total_revenue_eur,
        min(order_date)                             as first_order_date,
        max(order_date)                             as last_order_date

    from orders
    group by customer_id

),

final as (

    select
        c.customer_id,
        c.email,
        c.country_code,
        c.segment,
        c.signup_date,

        -- Origen: trazabilidad del sistema fuente
        c.origen,

        -- Métricas de comportamiento
        coalesce(co.total_orders, 0)        as total_orders,
        coalesce(co.completed_orders, 0)    as completed_orders,
        coalesce(co.cancelled_orders, 0)    as cancelled_orders,
        coalesce(co.total_revenue_eur, 0)   as total_revenue_eur,
        co.first_order_date,
        co.last_order_date,

        -- Customer lifetime value simplificado
        round(
            safe_divide(
                coalesce(co.total_revenue_eur, 0),
                nullif(coalesce(co.completed_orders, 0), 0)
            ), 2
        )                                   as avg_order_value_eur,

        -- Clasificación por valor
        case
            when coalesce(co.total_revenue_eur, 0) >= 500 then 'high_value'
            when coalesce(co.total_revenue_eur, 0) >= 200 then 'mid_value'
            else 'low_value'
        end                                 as value_tier

    from customers c
    left join customer_orders co on c.customer_id = co.customer_id

)

select * from final

