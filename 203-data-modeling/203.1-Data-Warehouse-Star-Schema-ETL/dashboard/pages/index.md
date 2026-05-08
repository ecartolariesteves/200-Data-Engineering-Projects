---
title: Dashboard Financiero — Banco España
---

```sql resumen_general
select
    sum(total_transactions)              as total_txns,
    round(sum(total_credits)  / 1e6, 2) as creditos_M,
    round(sum(total_debits)   / 1e6, 2) as debitos_M,
    round(sum(total_fees)     / 1e3, 1) as comisiones_K,
    round(avg(digital_adoption_pct), 1) as adopcion_digital_pct
from finanzas.vw_dashboard
```

<BigValue
  data={resumen_general}
  value=total_txns
  title="Transacciones totales"
  fmt=num0
/>
<BigValue
  data={resumen_general}
  value=creditos_M
  title="Créditos totales (M€)"
  fmt=num2
/>
<BigValue
  data={resumen_general}
  value=comisiones_K
  title="Comisiones (K€)"
  fmt=num1
/>
<BigValue
  data={resumen_general}
  value=adopcion_digital_pct
  title="Adopción digital (%)"
  fmt=num1
/>

---

## Volumen mensual de transacciones

```sql volumen_mensual
select
    year_month,
    year,
    month_number,
    total_transactions,
    active_accounts,
    round(total_credits / 1e6, 2)  as creditos_M,
    round(total_debits  / 1e6, 2)  as debitos_M,
    round(total_fees    / 1e3, 1)  as comisiones_K,
    round(net_flow      / 1e6, 2)  as flujo_neto_M,
    digital_adoption_pct
from finanzas.vw_dashboard
order by year, month_number
```

<LineChart
  data={volumen_mensual}
  x=year_month
  y=total_transactions
  title="Transacciones por mes"
  yAxisTitle="Nº transacciones"
/>

<BarChart
  data={volumen_mensual}
  x=year_month
  y={['creditos_M','debitos_M']}
  title="Créditos vs Débitos mensuales (M€)"
  yAxisTitle="Millones €"
  type=grouped
/>

---

## Revenue y comisiones

<LineChart
  data={volumen_mensual}
  x=year_month
  y=comisiones_K
  title="Comisiones mensuales (K€)"
  yAxisTitle="Miles €"
/>

<LineChart
  data={volumen_mensual}
  x=year_month
  y=flujo_neto_M
  title="Flujo neto mensual (M€)"
  yAxisTitle="Millones €"
/>

---

## Cuentas activas por mes

<AreaChart
  data={volumen_mensual}
  x=year_month
  y=active_accounts
  title="Cuentas activas"
  yAxisTitle="Cuentas"
/>

---

## Adopción digital

<LineChart
  data={volumen_mensual}
  x=year_month
  y=digital_adoption_pct
  title="Adopción digital mensual (%)"
  yAxisTitle="%"
/>
