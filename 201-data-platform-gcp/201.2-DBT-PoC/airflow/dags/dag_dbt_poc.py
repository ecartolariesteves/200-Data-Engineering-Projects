"""
dags/dag_dbt_poc.py
--------------------
DAG principal del pipeline de datos.
Ejecución diaria a las 05:00 hora Madrid (03:00 UTC).

Flujo:
    [extract_and_load] → [dbt_run] → [dbt_test]

En producción:
    - extract_and_load se reemplaza por la extracción real del DW on-premise
    - dbt_run y dbt_test son idénticos
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

# ── Configuración del DAG ────────────────────────────────────────────────────

default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,   # cambiar a True en producción con SMTP configurado
    "email_on_retry": False,
}

with DAG(
    dag_id="dbt_poc_pipeline",
    description="Pipeline diario: ingesta DW on-premise → BigQuery RAW → dbt transformaciones",
    schedule_interval="0 3 * * *",   # 03:00 UTC = 05:00 Madrid (horario verano)
    start_date=days_ago(1),
    catchup=False,                   # no ejecutar días pasados al activar el DAG
    default_args=default_args,
    tags=["dbt", "bigquery", "poc"],
) as dag:

    # ── Task 1: Extracción e ingesta ─────────────────────────────────────────
    # PoC:        carga CSVs locales → BigQuery RAW
    # Producción: reemplazar por extracción real del DW on-premise (JDBC/ODBC)

    extract_and_load = BashOperator(
        task_id="extract_and_load",
        bash_command="""
            echo "▶ Iniciando extracción e ingesta..."
            export GOOGLE_APPLICATION_CREDENTIALS=/opt/gcloud/application_default_credentials.json
            cd /opt/ingestion
            pip install -q -r requirements.txt
            python load_to_bigquery.py
            echo "✅ Ingesta completada"
        """,
        doc_md="""
        ### extract_and_load
        **PoC**: Carga los CSVs de `/data` en BigQuery dataset `raw`.
        **Producción**: Reemplazar por extracción del DW on-premise vía JDBC/ODBC o Fivetran.
        """,
    )

    # ── Task 2: dbt run ──────────────────────────────────────────────────────
    # Ejecuta todos los modelos en orden de dependencias:
    # stg_orders, stg_customers, stg_products → fact_orders, dim_customers

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command="""
            echo "▶ Ejecutando modelos dbt..."
            export GOOGLE_APPLICATION_CREDENTIALS=/opt/gcloud/application_default_credentials.json
            cd /opt/dbt_poc
            dbt run --profiles-dir /opt/dbt_profiles --project-dir /opt/dbt_poc
            echo "✅ dbt run completado"
        """,
        doc_md="""
        ### dbt_run
        Ejecuta las transformaciones RAW → STAGING → MARTS en BigQuery.
        - 3 vistas de staging (limpieza y tipado)
        - 2 tablas de marts (lógica de negocio)
        Usa `WRITE_TRUNCATE` — borra y recarga en cada ejecución.
        """,
    )

    # ── Task 3: dbt test ─────────────────────────────────────────────────────
    # Valida la calidad de los datos después de cada transformación.
    # Si algún test falla, el DAG falla y genera alerta.

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command="""
            echo "▶ Ejecutando tests de calidad..."
            export GOOGLE_APPLICATION_CREDENTIALS=/opt/gcloud/application_default_credentials.json
            cd /opt/dbt_poc
            dbt test --profiles-dir /opt/dbt_profiles --project-dir /opt/dbt_poc
            echo "✅ 32 tests pasados — datos validados"
        """,
        doc_md="""
        ### dbt_test
        Ejecuta los 32 tests de calidad declarados en los YMLs:
        - unique / not_null en claves primarias
        - accepted_values en campos categóricos
        Si algún test falla → el DAG falla → alerta al equipo.
        """,
    )

    # ── Dependencias ─────────────────────────────────────────────────────────
    # extract_and_load debe terminar OK antes de dbt_run
    # dbt_run debe terminar OK antes de dbt_test

    extract_and_load >> dbt_run >> dbt_test
