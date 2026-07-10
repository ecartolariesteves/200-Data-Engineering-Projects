# PoC Results — dbt + BigQuery Data Platform

> Prueba de concepto ejecutada sobre Google Cloud Platform a **coste cero**.
> Objetivo: validar la viabilidad técnica de migrar un Data Warehouse on-premise a BigQuery
> usando dbt como capa de transformación.

---

## Resultados de la ejecución

| Métrica | Resultado |
|---|---|
| Modelos ejecutados | **5 / 5** ✅ |
| Tests de calidad pasados | **32 / 32** ✅ |
| Tiempo de ejecución (`dbt run`) | **11.8 segundos** |
| Tiempo de validación (`dbt test`) | **15.0 segundos** |
| Coste total GCP | **0 €** |
| Data catalog generado | **Sí** (`dbt docs`) |

---

## La arquitectura que hemos validado

```
┌─────────────────────────────────────────────────────────────────────┐
│  ON-PREMISE (simulado)          GOOGLE CLOUD PLATFORM               │
│                                                                     │
│  DW on-premise                  BigQuery                            │
│  ┌──────────┐    Ingesta    ┌──────────┐    dbt Core               │
│  │ orders   │ ─────────────►│  RAW     │──────────────┐            │
│  │ customers│  (Python /    │  dataset │              │            │
│  │ products │   Cloud Run)  └──────────┘              ▼            │
│  └──────────┘                                  ┌──────────────┐    │
│                                                │   STAGING    │    │
│                                                │  (3 vistas)  │    │
│                                                └──────┬───────┘    │
│                                                       │            │
│                                                       ▼            │
│                                                ┌──────────────┐    │
│                                                │    MARTS     │    │
│                                                │  (2 tablas)  │    │
│                                                └──────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

**Capas del Data Warehouse:**

- **RAW** — Datos en bruto tal como vienen del DW on-premise. Sin transformar, sin tocar. Trazabilidad total.
- **STAGING** — Limpieza, tipado correcto, normalización. Materializado como **vistas** (coste de almacenamiento cero).
- **MARTS** — Lógica de negocio: tabla de hechos y dimensiones enriquecidas. Materializado como **tablas** para máximo rendimiento.

---

## Cómo decide dbt el orden de ejecución

Cuando lanzas `dbt run`, dbt **no sigue ningún orden manual** — lee el código de cada modelo y construye un grafo de dependencias automáticamente.

El mecanismo son dos funciones dentro del SQL:

- `{{ source('raw', 'orders') }}` — lee de la capa RAW declarada en `sources.yml`
- `{{ ref('stg_orders') }}` — indica que este modelo depende de otro modelo dbt

Con eso, dbt construye el grafo y ejecuta en el orden correcto:

```
1️⃣  Lee todos los .sql y detecta las referencias

     stg_orders.sql     →  source raw.orders
     stg_customers.sql  →  source raw.customers
     stg_products.sql   →  source raw.products

     fact_orders.sql    →  ref stg_orders, stg_customers, stg_products
     dim_customers.sql  →  ref stg_customers, stg_orders

2️⃣  Construye el grafo de dependencias

     raw.orders ──────────► stg_orders ───────► fact_orders
     raw.customers ────────► stg_customers ───► fact_orders
                                            └─► dim_customers
     raw.products ─────────► stg_products ────► fact_orders

3️⃣  Ejecuta respetando el grafo

     stg_orders      ✅  (sin dependencias dbt, va primero)
     stg_customers   ✅  (sin dependencias dbt, va primero)
     stg_products    ✅  (sin dependencias dbt, va primero)
         │
         ▼
     fact_orders     ✅  (espera a que los 3 stg terminen)
     dim_customers   ✅  (espera a stg_customers y stg_orders)
```

**Los YMLs no ejecutan nada**, solo informan a dbt:
- `sources.yml` → declara la capa RAW como fuente válida
- `stg_models.yml` / `mart_models.yml` → tests y documentación de columnas

Si mañana añades un nuevo modelo con `ref('fact_orders')`, dbt lo ejecuta al final sin tocar ninguna configuración.

---

## Qué demuestra esta PoC

### 1. Transformaciones SQL versionadas en Git

En el modelo de datos tradicional, la lógica de transformación vive dispersa en stored procedures, scripts SQL sueltos o flujos ETL sin versionar. Imposible saber quién cambió qué y cuándo.

Con dbt, **cada transformación es un fichero `.sql` en Git**:

```sql
-- models/marts/fact_orders.sql
with orders as (
    select * from {{ ref('stg_orders') }}        -- referencia tipada
),
customers as (
    select * from {{ ref('stg_customers') }}
),
final as (
    select
        o.order_id,
        o.order_date,
        c.segment          as customer_segment,
        o.order_amount_eur,
        case when o.status = 'completed'
             then o.order_amount_eur else 0
        end                as revenue_eur
    from orders o
    left join customers c on o.customer_id = c.customer_id
)
select * from final
```

El resultado: **Pull Requests para revisar cambios en el modelo de datos**, igual que en desarrollo de software.

---

### 2. Linaje de datos automático

dbt construye un grafo de dependencias a partir del código. No hay que documentarlo manualmente:

```
raw.orders ──────────────────► stg_orders ──────► fact_orders
raw.customers ────────────────► stg_customers ──► fact_orders
                                               └─► dim_customers
raw.products ────────────────► stg_products ───► fact_orders
```

Cuando un analista pregunta *"¿de dónde viene este número?"*, la respuesta está en el catálogo, un click.

---

### 3. Calidad de datos con 32 tests automáticos

Los tests se declaran en YAML y corren en cada ejecución:

```yaml
- name: order_id
  tests:
    - unique        # no hay duplicados
    - not_null      # no hay nulls

- name: status
  tests:
    - accepted_values:
        values: ['completed', 'shipped', 'cancelled', 'pending']
```

**32 tests ejecutados en 15 segundos.** Si alguno falla, el pipeline se detiene y genera alerta. Los datos incorrectos nunca llegan a producción.

---

### 4. Data Catalog autogenerado

`dbt docs generate` + `dbt docs serve` genera un portal web con:

- Descripción de cada tabla y columna
- Linaje visual interactivo (quién usa qué)
- Resultados de los últimos tests
- Código SQL de cada modelo

**Sin esfuerzo de documentación manual.** El catálogo se actualiza solo en cada deploy.

---

### 5. Coste cero en desarrollo

| Componente | Prod | Esta PoC |
|---|---|---|
| dbt Core | Gratis (open source) | ✅ Gratis |
| BigQuery storage | ~$0.02/GB/mes | ✅ Free tier (<10GB) |
| BigQuery queries | ~$5/TB | ✅ Free tier (<1TB/mes) |
| Cloud Run (ingesta) | De pago | ✅ Script Python local |
| Airflow | De pago | ✅ Ejecución manual CLI |
| **Total** | | **0 €** |

---

## Del modelo actual al modelo objetivo

| | **Hoy (DW on-premise)** | **Con esta arquitectura** |
|---|---|---|
| Transformaciones | Stored procedures / ETL | SQL en Git, versionado |
| Calidad de datos | Tests manuales o ninguno | 32+ tests automáticos |
| Documentación | Manual, desactualizada | Autogenerada, siempre viva |
| Linaje | Desconocido | Grafo visual automático |
| Deploy | Manual | Git PR → CI/CD |
| Escalabilidad | Limitada por hardware | BigQuery escala ilimitado |
| Coste infra | CAPEX (servidores) | OPEX (pay per query) |

---

## Roadmap hacia producción

```
FASE 1 (PoC — completada ✅)
└── dbt Core local + BigQuery free tier + datos de muestra

FASE 2 (Piloto)
├── Conectar al DW on-premise real (JDBC/ODBC)
├── Ingesta con Cloud Run en GCP
├── Orquestación con Apache Airflow (Cloud Composer)
└── Entorno dev / prod separados

FASE 3 (Producción)
├── CI/CD con GitHub Actions (dbt run en cada PR) ✅ configurado
├── 11 orígenes reales conectados (SAP, AS400, SIS...)
├── Alertas de calidad (Slack / email)
├── dbt Cloud para scheduling y observabilidad
└── Expansión a más fuentes y dominios de datos
```

---

## Arquitectura multi-origen: 11 sistemas en un solo pipeline

Con múltiples orígenes (ALLARD, AS400-1, GESBOX, Hist-AS400, NAV, RTS-1, RTS-2, RTS-3, SAP-1, SAP-2, SIS) la estructura de modelos escala así:

```
staging/allard/     stg_allard__customers.sql  ─┐
staging/sap_1/      stg_sap_1__customers.sql   ─┤
staging/sap_2/      stg_sap_2__customers.sql   ─┤
staging/sis/        stg_sis__customers.sql      ─┤──► int_customers ──► dim_customers
staging/nav/        stg_nav__customers.sql      ─┤    (UNION ALL +      (lógica de
staging/rts_1/      stg_rts_1__customers.sql   ─┤     col. origen)       negocio)
...                 ...                         ─┘
```

Cada origen normaliza sus datos en su propia carpeta de staging. La capa `intermediate` hace el `UNION ALL` con la columna `origen` para trazabilidad total. Los marts consumen siempre de intermediate — nunca directamente de staging.

**Resultado**: en `dim_customers` siempre sabes de qué sistema viene cada cliente:

```sql
select customer_id, email, segment, origen
from dbt_poc_prod.dim_customers
-- origen puede ser: 'SAP-1', 'SIS', 'ALLARD', 'NAV'...
```

---

## Flujo Git y deploy a producción

Un solo repositorio, dos entornos controlados por ramas:

```
feature/origen-sap2
        │
        │  Pull Request + revisión
        ▼
   develop ──────────► CI/CD ejecuta dbt run --target dev  ✅
        │
        │  Pull Request validado
        ▼
     main ────────────► CI/CD ejecuta dbt run --target prod ✅
```

**GitHub Actions** (`.github/workflows/dbt_ci_cd.yml`) automatiza todo:

| Evento | Acción automática |
|---|---|
| PR hacia `develop` | `dbt run` + `dbt test` en entorno DEV |
| PR hacia `main` | `dbt run` + `dbt test` en entorno PROD |
| Test fallido | PR bloqueado — los datos incorrectos no llegan a producción |

**Añadir un nuevo origen** sigue siempre el mismo flujo:
```
1. git checkout -b feature/origen-nuevo
2. Crear staging/nuevo_origen/ con .sql y .yml
3. Añadir al UNION ALL en int_customers.sql e int_orders.sql
4. dbt run --select staging.nuevo_origen.* --target dev
5. Pull Request → develop → validación → main → prod
```
El resto del pipeline sigue corriendo sin interrupciones.

---

## Stack tecnológico

| Capa | Tecnología | Licencia |
|---|---|---|
| Transformación | dbt Core 1.11 | Open Source (Apache 2.0) |
| Data Warehouse | Google BigQuery | GCP (pay per use) |
| Ingesta | Python + google-cloud-bigquery | Open Source |
| Orquestación (prod) | Apache Airflow | Open Source (Apache 2.0) |
| CI/CD | GitHub Actions | Gratis hasta 2000 min/mes |
| Autenticación | Google ADC / OAuth | GCP nativo |

---

*PoC desarrollada por Edgar Estévez — Mayo 2026*
*Repositorio: [200-Data-Engineering-Projects](https://github.com/ecartolariesteves/200-Data-Engineering-Projects)*
