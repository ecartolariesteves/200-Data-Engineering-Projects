# 201.2 - dbt PoC: Data Platform GCP

> **PoC validada y ejecutada al 100% a coste cero.**
> Demuestra el flujo completo de una plataforma de datos moderna sobre Google Cloud Platform.

**DW on-premise → BigQuery RAW → dbt STAGING → dbt MARTS**

→ Resultados completos y explicación para preventa en [RESULTS.md](./RESULTS.md)

---

## Arquitectura

```
data/*.csv          ingestion/              BigQuery                    dbt Core
(simula DW          load_to_bigquery.py  ┌──────────────┐    ┌─────────────────────────┐
 on-premise)  ───►  (simula Cloud Run)  ─► │  RAW (x11)   │ ──► │ staging/origen/ (views) │
                                           └──────────────┘    │ intermediate/  (views)  │
                                                                │ marts/         (tables) │
                                                                └─────────────────────────┘
```

## Estructura del proyecto

```
201.2-DBT-PoC/
├── .github/
│   └── workflows/
│       └── dbt_ci_cd.yml         ← CI/CD: dbt run + test en cada PR
├── .gitignore
├── .env.example
├── profiles.yml.example
├── docker-compose.yml            ← Airflow local
├── data/                         ← CSVs de muestra (simula DW on-premise)
├── ingestion/
│   └── load_to_bigquery.py
└── dbt_poc/
    ├── dbt_project.yml
    └── models/
        ├── staging/
        │   ├── allard/           ← un folder por origen
        │   │   ├── _sources_allard.yml
        │   │   ├── stg_allard__customers.sql
        │   │   └── stg_allard__orders.sql
        │   ├── sap_1/            (misma estructura x11 orígenes)
        │   ├── sap_2/
        │   ├── sis/
        │   └── ...
        ├── intermediate/
        │   ├── int_customers.sql ← UNION ALL de los 11 stg_*__customers
        │   ├── int_orders.sql    ← UNION ALL de los 11 stg_*__orders
        │   └── int_models.yml
        └── marts/
            ├── fact_orders.sql   ← consume int_orders
            ├── dim_customers.sql ← consume int_customers
            └── mart_models.yml
```

---

## Setup paso a paso

### 1. Prerrequisitos

```bash
python 3.9+
pip install dbt-bigquery==1.7.x
```

### 2. Autenticación en GCP (sin fichero JSON)

**Opción A — VS Code con extensión Google Cloud (recomendado):**
Si ya estás conectado en VS Code, las ADC están configuradas automáticamente. No necesitas hacer nada más.

**Opción B — gcloud CLI:**
```bash
gcloud auth application-default login
gcloud config set project project-34ac0f7c-00d8-4675-afe
```
Esto abre el browser, te autenticas, y guarda un token en `~/.config/gcloud/`. Nada va a GitHub.

> Para producción (CI/CD) se usa Service Account con JSON inyectado como secret. Ver `profiles.yml.example`.

### 3. Configurar dbt profile

```bash
# El profiles.yml va en tu HOME, fuera del repo (nunca en GitHub)
cp profiles.yml.example ~/.dbt/profiles.yml
# El método oauth (ADC) no requiere editar nada más
```

### 5. Crear datasets en BigQuery

Crea manualmente estos datasets en tu proyecto GCP (`europe-west6`):
- `raw`
- `dbt_poc_dev`

O usa la CLI de gcloud:
```bash
bq --location=europe-west6 mk --dataset project-34ac0f7c-00d8-4675-afe:raw
bq --location=europe-west6 mk --dataset project-34ac0f7c-00d8-4675-afe:dbt_poc_dev
```

### 6. Cargar datos a BigQuery RAW

```bash
cd ingestion
pip install -r requirements.txt
python load_to_bigquery.py
```

Deberías ver:
```
🚀 Iniciando ingesta hacia BigQuery
✅ Dataset listo: project-34ac0f7c-00d8-4675-afe.raw
✅ Cargado 20 filas → ...raw.orders
✅ Cargado 10 filas → ...raw.customers
✅ Cargado 5 filas  → ...raw.products
🎉 Ingesta completada.
```

### 7. Ejecutar dbt

```bash
cd dbt_poc

# Verificar conexión
dbt debug

# Ejecutar todos los modelos
dbt run

# Ejecutar tests
dbt test

# Generar y ver documentación
dbt docs generate
dbt docs serve
```

### 8. Ver resultados en BigQuery

Después de `dbt run` tendrás en BigQuery:
- `dbt_poc_dev.stg_orders` (vista)
- `dbt_poc_dev.stg_customers` (vista)
- `dbt_poc_dev.stg_products` (vista)
- `dbt_poc_dev.fact_orders` (tabla)
- `dbt_poc_dev.dim_customers` (tabla)

---

## Queries de validación

```sql
-- Revenue por mes
SELECT order_year_month, SUM(revenue_eur) AS revenue
FROM `project-34ac0f7c-00d8-4675-afe.dbt_poc_dev.fact_orders`
GROUP BY 1 ORDER BY 1;

-- Clientes por value tier
SELECT value_tier, COUNT(*) AS customers, SUM(total_revenue_eur) AS revenue
FROM `project-34ac0f7c-00d8-4675-afe.dbt_poc_dev.dim_customers`
GROUP BY 1;

-- Top productos por revenue
SELECT product_name, SUM(revenue_eur) AS revenue
FROM `project-34ac0f7c-00d8-4675-afe.dbt_poc_dev.fact_orders`
WHERE status = 'completed'
GROUP BY 1 ORDER BY 2 DESC;
```

---

## Coste

| Componente | Coste |
|---|---|
| dbt Core | **Gratis** (open source) |
| BigQuery storage (<10GB) | **Gratis** (free tier) |
| BigQuery queries (<1TB/mes) | **Gratis** (free tier) |
| Python / scripts locales | **Gratis** |
| **TOTAL PoC** | **0 €** |

