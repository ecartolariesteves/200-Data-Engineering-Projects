---
title: Análisis por Segmento
---

```sql kpis_segmento
select
    account_segment                              as segmento,
    sum(total_transactions)                      as total_txns,
    sum(active_accounts)                         as cuentas_activas,
    round(sum(total_credits)  / 1e6, 2)          as creditos_M,
    round(sum(total_fees_collected)     / 1e3, 1)          as comisiones_K,
    round(avg(fee_rate_pct),  2)                 as tasa_comision_pct,
    round(avg(digital_pct),   1)                 as adopcion_digital_pct
from finanzas.mart_kpis
group by account_segment
order by creditos_M desc
```

## Resumen por segmento

<DataTable data={kpis_segmento} />

---

## Créditos por segmento (M€)

<BarChart
  data={kpis_segmento}
  x=segmento
  y=creditos_M
  title="Créditos totales por segmento (M€)"
  yAxisTitle="Millones €"
  swapXY=true
/>

---

## Evolución mensual por segmento

```sql evolucion_segmento
select
    year || '-' || lpad(cast(month_number as varchar), 2, '0') as year_month,
    account_segment                                             as segmento,
    year,
    month_number,
    sum(total_transactions)                                     as txns,
    round(sum(total_credits) / 1e6, 2)                         as creditos_M
from finanzas.mart_kpis
group by 1, 2, 3, 4
order by year, month_number
```

<LineChart
  data={evolucion_segmento}
  x=year_month
  y=creditos_M
  series=segmento
  title="Créditos mensuales por segmento (M€)"
  yAxisTitle="Millones €"
/>

<BarChart
  data={evolucion_segmento}
  x=year_month
  y=txns
  series=segmento
  title="Transacciones mensuales por segmento"
  yAxisTitle="Nº transacciones"
  type=stacked
/>

---

## Adopción digital por segmento

```sql digital_segmento
select
    account_segment              as segmento,
    round(avg(digital_pct), 1)   as adopcion_digital_pct,
    sum(txns_app)                as txns_app,
    sum(total_transactions)      as txns_total
from finanzas.mart_kpis
group by account_segment
order by adopcion_digital_pct desc
```

<BarChart
  data={digital_segmento}
  x=segmento
  y=adopcion_digital_pct
  title="Adopción digital por segmento (%)"
  yAxisTitle="%"
  swapXY=true
/>

---

## Distribución por sucursal

```sql por_sucursal
select
    account_branch                     as sucursal,
    sum(total_transactions)            as txns,
    round(sum(total_credits) / 1e6, 2) as creditos_M,
    round(sum(total_fees_collected)    / 1e3, 1) as comisiones_K
from finanzas.mart_kpis
group by account_branch
order by creditos_M desc
```

<DataTable data={por_sucursal} />

<BarChart
  data={por_sucursal}
  x=sucursal
  y=creditos_M
  title="Créditos por sucursal (M€)"
  yAxisTitle="Millones €"
  swapXY=true
/>
