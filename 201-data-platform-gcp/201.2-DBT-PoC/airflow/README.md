# Airflow — Orquestación del pipeline

## Levantar Airflow

```powershell
# Desde la raíz del proyecto 201.2-DBT-PoC/
docker-compose up -d
```

Primera vez tarda ~3-5 minutos (descarga imagen + instala dbt-bigquery).

## Acceder a la UI

```
http://localhost:8080
Usuario: admin
Password: admin
```

## DAG: dbt_poc_pipeline

Ejecución automática diaria a las **05:00 hora Madrid**.

```
extract_and_load → dbt_run → dbt_test
```

Para ejecutar manualmente: UI → DAG `dbt_poc_pipeline` → botón ▶ Trigger DAG

## Parar Airflow

```powershell
docker-compose down
```

## Ver logs

```powershell
docker-compose logs -f airflow
```
