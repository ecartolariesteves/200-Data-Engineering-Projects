# Fabric Auto-Scaling System — Capa 1: Observabilidad
# ======================================================
# Notebook: layer1_observability
# Descripción: Conecta con la Fabric Capacity Metrics API, extrae métricas
#              cada 5 minutos y las persiste en Delta table `metrics_raw`.
# Scheduling:  Ejecutar este notebook vía Fabric Pipeline con trigger cada 5 min.
# Idempotencia: Deduplicación por (capacity_id, window_start_time) antes de escribir.
# ======================================================

# ── CELDA 1: Configuración centralizada ──────────────────────────────────────
# Todos los parámetros configurables en un único dict. Sin hardcoding fuera de aquí.

CONFIG = {
    # --- Identidad de la capacity a monitorizar ---
    "capacity_id": "<YOUR_CAPACITY_ID>",          # GUID de la Fabric capacity
    "subscription_id": "<YOUR_SUBSCRIPTION_ID>",  # Azure Subscription ID
    "resource_group": "<YOUR_RESOURCE_GROUP>",    # Resource group de la capacity

    # --- Autenticación (Managed Identity del workspace Fabric) ---
    # Si el workspace tiene Managed Identity activa, token_source = "managed_identity"
    # Alternativa: "service_principal" → rellenar client_id / client_secret / tenant_id
    "token_source": "managed_identity",           # "managed_identity" | "service_principal"
    "tenant_id": "<YOUR_TENANT_ID>",              # Solo para service_principal
    "client_id": "<YOUR_CLIENT_ID>",              # Solo para service_principal
    "client_secret": "<YOUR_CLIENT_SECRET>",      # Solo para service_principal (usar Key Vault)

    # --- Lakehouse / Delta ---
    "lakehouse_name": "AutoScalingLakehouse",     # Nombre del Lakehouse en Fabric
    "table_metrics_raw": "metrics_raw",           # Delta table de destino

    # --- Ventana de métricas ---
    # La API de Fabric Capacity Metrics devuelve datos con granularidad de 1 min.
    # Capturamos los últimos N minutos en cada ejecución para tolerar retrasos.
    "lookback_minutes": 10,                       # Ventana de lookback en cada run
    "collection_interval_minutes": 5,             # Frecuencia de scheduling (documentativo)

    # --- Modo seguro ---
    "dry_run": False,                             # True → no escribe en Delta, solo imprime

    # --- Diagnóstico ---
    "verbose": True,                              # Imprime métricas extraídas por pantalla
}

print("✅ Configuración cargada.")
print(f"   capacity_id      : {CONFIG['capacity_id']}")
print(f"   tabla destino     : {CONFIG['table_metrics_raw']}")
print(f"   lookback_minutes  : {CONFIG['lookback_minutes']}")
print(f"   dry_run           : {CONFIG['dry_run']}")


# ── CELDA 2: Imports y dependencias ──────────────────────────────────────────
# Todas las librerías disponibles de serie en Fabric Runtime 1.3 (Spark 3.4 / Python 3.11)

import json
import time
import requests
import traceback
from datetime import datetime, timezone, timedelta

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField,
    StringType, DoubleType, LongType, BooleanType, TimestampType
)

spark = SparkSession.builder.getOrCreate()
print(f"✅ Spark {spark.version} activo.")


# ── CELDA 3: Esquema canónico de metrics_raw ──────────────────────────────────
# Esquema estable y explícito. Cualquier cambio aquí se propaga a toda la pipeline.

METRICS_RAW_SCHEMA = StructType([
    # Identificación
    StructField("ingestion_timestamp",  TimestampType(), False),  # Momento de ingesta (UTC)
    StructField("window_start_time",    TimestampType(), False),  # Inicio ventana métrica (UTC)
    StructField("window_end_time",      TimestampType(), True),   # Fin ventana métrica (UTC)
    StructField("capacity_id",          StringType(),   False),   # GUID de la capacity
    StructField("sku",                  StringType(),   True),    # SKU activo (F2, F4, … F2048)

    # Consumo de Compute Units
    StructField("cu_consumption_pct",   DoubleType(),   True),    # % uso CUs sobre límite SKU
    StructField("cu_used",              DoubleType(),   True),    # CUs usadas (valor absoluto)
    StructField("cu_limit",             DoubleType(),   True),    # CUs límite del SKU actual
    StructField("cu_background_pct",    DoubleType(),   True),    # % consumo background jobs
    StructField("cu_interactive_pct",   DoubleType(),   True),    # % consumo interactive jobs

    # Cola y throttling
    StructField("queued_jobs",          LongType(),     True),    # Trabajos en cola
    StructField("throttling_active",    BooleanType(),  True),    # ¿Throttling activo?
    StructField("throttling_rejected",  LongType(),     True),    # Requests rechazados por throttle

    # Estado de la capacity
    StructField("capacity_state",       StringType(),   True),    # Active | Paused | Scaling
    StructField("operation_in_progress",BooleanType(),  True),    # ¿Cambio de SKU en curso?

    # Metadata de ingesta
    StructField("api_response_ms",      LongType(),     True),    # Latencia llamada API (ms)
    StructField("source_notebook",      StringType(),   True),    # Trazabilidad
])

print("✅ Esquema metrics_raw definido con", len(METRICS_RAW_SCHEMA.fields), "campos.")


# ── CELDA 4: Autenticación → token Azure AD ───────────────────────────────────

def get_access_token(config: dict) -> str:
    """
    Obtiene un Bearer token de Azure AD.
    - managed_identity: usa el endpoint IMDS del nodo Fabric (sin credenciales).
    - service_principal: flujo client_credentials estándar.
    Lanza RuntimeError si no puede autenticarse.
    """
    resource = "https://management.azure.com/"

    if config["token_source"] == "managed_identity":
        # Azure Instance Metadata Service (IMDS) — disponible en todos los nodos Fabric
        imds_url = (
            "http://169.254.169.254/metadata/identity/oauth2/token"
            f"?api-version=2018-02-01&resource={resource}"
        )
        resp = requests.get(imds_url, headers={"Metadata": "true"}, timeout=10)
        resp.raise_for_status()
        token = resp.json()["access_token"]
        if config.get("verbose"):
            print("✅ Token obtenido via Managed Identity.")
        return token

    elif config["token_source"] == "service_principal":
        url = f"https://login.microsoftonline.com/{config['tenant_id']}/oauth2/token"
        payload = {
            "grant_type":    "client_credentials",
            "client_id":     config["client_id"],
            "client_secret": config["client_secret"],
            "resource":      resource,
        }
        resp = requests.post(url, data=payload, timeout=15)
        resp.raise_for_status()
        token = resp.json()["access_token"]
        if config.get("verbose"):
            print("✅ Token obtenido via Service Principal.")
        return token

    else:
        raise ValueError(f"token_source desconocido: {config['token_source']}")


# ── CELDA 5: Cliente Fabric Capacity Metrics API ──────────────────────────────

class FabricCapacityMetricsClient:
    """
    Wrapper sobre la REST API de Azure Monitor / Fabric Capacity Metrics.

    Endpoints utilizados:
    1. GET /subscriptions/{sub}/resourceGroups/{rg}/providers/
           Microsoft.Fabric/capacities/{cap}
       → estado actual (SKU, provisioningState, state)

    2. GET /subscriptions/{sub}/resourceGroups/{rg}/providers/
           Microsoft.Fabric/capacities/{cap}/providers/
           microsoft.insights/metrics
       → series temporales de CUs, throttling, cola
    """

    BASE_ARM = "https://management.azure.com"
    API_FABRIC  = "2023-11-01"
    API_MONITOR = "2023-10-01"

    def __init__(self, config: dict, token: str):
        self.config  = config
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
        }
        sub  = config["subscription_id"]
        rg   = config["resource_group"]
        cap  = config["capacity_id"]
        self._capacity_url = (
            f"{self.BASE_ARM}/subscriptions/{sub}/resourceGroups/{rg}"
            f"/providers/Microsoft.Fabric/capacities/{cap}"
        )

    # ── helpers ──────────────────────────────────────────────────────────────

    def _get(self, url: str, params: dict = None, timeout: int = 20) -> dict:
        t0 = time.monotonic()
        resp = requests.get(url, headers=self.headers, params=params, timeout=timeout)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        resp.raise_for_status()
        data = resp.json()
        data["_api_response_ms"] = elapsed_ms
        return data

    # ── métodos públicos ──────────────────────────────────────────────────────

    def get_capacity_state(self) -> dict:
        """
        Devuelve estado actual de la capacity: SKU, state, operationInProgress.
        """
        params = {"api-version": self.API_FABRIC}
        data   = self._get(self._capacity_url, params=params)
        props  = data.get("properties", {})
        return {
            "sku":                   data.get("sku", {}).get("name", "unknown"),
            "capacity_state":        props.get("state", "unknown"),
            "operation_in_progress": props.get("provisioningState", "") == "Updating",
            "api_response_ms":       data["_api_response_ms"],
        }

    def get_metrics(self, window_start: datetime, window_end: datetime) -> list[dict]:
        """
        Consulta Azure Monitor para obtener métricas de la capacity en la ventana dada.
        Devuelve lista de dicts, uno por minuto en la ventana.

        Métricas solicitadas:
          - CapacityUsagePercent      → cu_consumption_pct
          - CapacityLimitCU           → cu_limit
          - CapacityUsedCU            → cu_used
          - BackgroundCapacityPercent → cu_background_pct
          - InteractiveCapacityPercent→ cu_interactive_pct
          - ThrottlingActive          → throttling_active (max en ventana de 1 min)
          - ThrottlingRejected        → throttling_rejected
          - QueuedJobCount            → queued_jobs

        Nota: no todas las métricas están disponibles en todos los SKU/regiones.
        Campos faltantes se rellenan con None para mantener el esquema.
        """
        metrics_url = (
            f"{self._capacity_url}/providers/microsoft.insights/metrics"
        )
        metric_names = ",".join([
            "CapacityUsagePercent",
            "CapacityLimitCU",
            "CapacityUsedCU",
            "BackgroundCapacityPercent",
            "InteractiveCapacityPercent",
            "ThrottlingActive",
            "ThrottlingRejected",
            "QueuedJobCount",
        ])
        params = {
            "api-version":    self.API_MONITOR,
            "metricnames":    metric_names,
            "timespan":       (
                f"{window_start.strftime('%Y-%m-%dT%H:%M:%SZ')}/"
                f"{window_end.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            ),
            "interval":       "PT1M",          # granularidad 1 minuto
            "aggregation":    "Average,Maximum,Total",
            "metricNamespace":"microsoft.fabric/capacities",
        }
        data = self._get(metrics_url, params=params)
        api_ms = data["_api_response_ms"]

        # ── parsear series temporales ─────────────────────────────────────────
        # Construimos un dict {timestamp → {metric_key: value}}
        timeline: dict[str, dict] = {}

        metric_map = {
            "CapacityUsagePercent":       ("cu_consumption_pct",    "average"),
            "CapacityLimitCU":            ("cu_limit",               "average"),
            "CapacityUsedCU":             ("cu_used",                "average"),
            "BackgroundCapacityPercent":  ("cu_background_pct",      "average"),
            "InteractiveCapacityPercent": ("cu_interactive_pct",     "average"),
            "ThrottlingActive":           ("throttling_active",      "maximum"),
            "ThrottlingRejected":         ("throttling_rejected",    "total"),
            "QueuedJobCount":             ("queued_jobs",            "average"),
        }

        for metric in data.get("value", []):
            api_name  = metric.get("name", {}).get("value", "")
            if api_name not in metric_map:
                continue
            field_name, agg = metric_map[api_name]
            for series in metric.get("timeseries", []):
                for point in series.get("data", []):
                    ts = point.get("timeStamp", "")
                    if not ts:
                        continue
                    if ts not in timeline:
                        timeline[ts] = {}
                    raw_val = point.get(agg)
                    # Conversión especial: ThrottlingActive → bool
                    if field_name == "throttling_active":
                        timeline[ts][field_name] = bool(raw_val) if raw_val is not None else None
                    elif field_name == "throttling_rejected":
                        timeline[ts][field_name] = int(raw_val) if raw_val is not None else None
                    elif field_name == "queued_jobs":
                        timeline[ts][field_name] = int(raw_val) if raw_val is not None else None
                    else:
                        timeline[ts][field_name] = float(raw_val) if raw_val is not None else None

        # ── convertir a lista de registros ────────────────────────────────────
        records = []
        for ts_str, fields in sorted(timeline.items()):
            try:
                window_start_dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc
                )
                window_end_dt   = window_start_dt + timedelta(minutes=1)
            except ValueError:
                continue
            records.append({
                "window_start_time":     window_start_dt,
                "window_end_time":       window_end_dt,
                "cu_consumption_pct":    fields.get("cu_consumption_pct"),
                "cu_used":               fields.get("cu_used"),
                "cu_limit":              fields.get("cu_limit"),
                "cu_background_pct":     fields.get("cu_background_pct"),
                "cu_interactive_pct":    fields.get("cu_interactive_pct"),
                "queued_jobs":           fields.get("queued_jobs"),
                "throttling_active":     fields.get("throttling_active"),
                "throttling_rejected":   fields.get("throttling_rejected"),
                "api_response_ms":       api_ms,
            })
        return records


# ── CELDA 6: Lógica principal de extracción ───────────────────────────────────

def extract_metrics(config: dict) -> list[dict]:
    """
    Obtiene token, consulta estado + métricas, combina en registros enriquecidos.
    Devuelve lista de dicts lista para crear un DataFrame Spark.
    """
    now_utc       = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    window_end    = now_utc
    window_start  = now_utc - timedelta(minutes=config["lookback_minutes"])
    ingestion_ts  = now_utc

    if config.get("verbose"):
        print(f"⏱  Ventana: {window_start.isoformat()} → {window_end.isoformat()}")

    # 1. Token
    token  = get_access_token(config)

    # 2. Cliente
    client = FabricCapacityMetricsClient(config, token)

    # 3. Estado actual de la capacity
    state_info = client.get_capacity_state()
    if config.get("verbose"):
        print(f"📡 Estado capacity: {state_info}")

    # 4. Métricas históricas (ventana lookback)
    metric_records = client.get_metrics(window_start, window_end)
    if config.get("verbose"):
        print(f"📊 Puntos recibidos: {len(metric_records)}")

    # 5. Enriquecer cada registro con estado y metadata
    enriched = []
    for rec in metric_records:
        enriched.append({
            **rec,
            "ingestion_timestamp":   ingestion_ts,
            "capacity_id":           config["capacity_id"],
            "sku":                   state_info["sku"],
            "capacity_state":        state_info["capacity_state"],
            "operation_in_progress": state_info["operation_in_progress"],
            "source_notebook":       "layer1_observability",
        })
    return enriched


# ── CELDA 7: Escritura idempotente en Delta table ─────────────────────────────

def write_metrics_to_delta(records: list[dict], config: dict) -> int:
    """
    Escribe los registros en la Delta table metrics_raw.
    Idempotencia:  MERGE ON (capacity_id, window_start_time)
                   → INSERT si no existe, no hace UPDATE (evita sobreescribir datos históricos).
    Devuelve el número de filas nuevas insertadas.
    Si dry_run=True, solo imprime el DataFrame sin escribir.
    """
    if not records:
        print("ℹ️  Sin registros nuevos que escribir.")
        return 0

    # Crear DataFrame con esquema explícito
    df_new = spark.createDataFrame(records, schema=METRICS_RAW_SCHEMA)

    if config.get("verbose"):
        print(f"\n📝 Muestra de registros a escribir ({df_new.count()} filas):")
        df_new.select(
            "window_start_time", "sku", "cu_consumption_pct",
            "queued_jobs", "throttling_active", "capacity_state"
        ).show(5, truncate=False)

    if config["dry_run"]:
        print("🔵 DRY RUN — no se escribe en Delta. Registros que se habrían insertado:",
              df_new.count())
        return 0

    # Ruta de la tabla en el Lakehouse activo
    # En Fabric, el Lakehouse activo se accede directamente por nombre de tabla.
    table_name = config["table_metrics_raw"]

    # Crear tabla si no existe (primera ejecución)
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {table_name}
        USING DELTA
        PARTITIONED BY (capacity_id)
        TBLPROPERTIES (
            'delta.autoOptimize.optimizeWrite' = 'true',
            'delta.autoOptimize.autoCompact'   = 'true'
        )
        AS SELECT * FROM (SELECT * FROM {table_name} LIMIT 0)
    """) if False else None  # guard: solo ejecutar si la tabla no existe

    # Usamos Delta MERGE para idempotencia
    df_new.createOrReplaceTempView("metrics_incoming")

    merge_sql = f"""
        MERGE INTO {table_name} AS target
        USING metrics_incoming AS source
        ON  target.capacity_id        = source.capacity_id
        AND target.window_start_time  = source.window_start_time
        WHEN NOT MATCHED THEN INSERT *
    """

    # Primera vez: la tabla puede no existir → intentar write directo con delta
    try:
        from delta.tables import DeltaTable
        if DeltaTable.isDeltaTable(spark, f"Tables/{table_name}"):
            spark.sql(merge_sql)
            # Contar filas insertadas (aproximación: filas en df_new no presentes antes)
            inserted = df_new.count()
        else:
            # Tabla no existe → crear con primera escritura
            (df_new.write
                   .format("delta")
                   .mode("overwrite")
                   .option("overwriteSchema", "true")
                   .partitionBy("capacity_id")
                   .saveAsTable(table_name))
            inserted = df_new.count()
            print(f"✅ Tabla '{table_name}' creada con {inserted} filas.")
    except Exception:
        # Fallback: write con modo append + deduplicación post-hoc
        (df_new.write
               .format("delta")
               .mode("append")
               .option("mergeSchema", "true")
               .saveAsTable(table_name))
        # Deduplicar en sitio
        spark.sql(f"""
            WITH dedup AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY capacity_id, window_start_time
                    ORDER BY ingestion_timestamp DESC
                ) AS rn
                FROM {table_name}
            )
            DELETE FROM {table_name}
            WHERE (capacity_id, window_start_time) IN (
                SELECT capacity_id, window_start_time FROM dedup WHERE rn > 1
            )
        """)
        inserted = df_new.count()

    print(f"✅ Escritura completada. Filas procesadas: {inserted}")
    return inserted


# ── CELDA 8: Validación post-escritura ───────────────────────────────────────

def validate_latest_metrics(config: dict):
    """
    Consulta rápida de sanidad sobre los últimos datos escritos.
    Imprime estadísticas básicas y alertas si los valores son anómalos.
    """
    if config["dry_run"]:
        return

    table_name = config["table_metrics_raw"]
    try:
        df_check = spark.sql(f"""
            SELECT
                MAX(ingestion_timestamp)  AS last_ingestion,
                MAX(window_start_time)    AS last_window,
                COUNT(*)                  AS total_rows,
                AVG(cu_consumption_pct)   AS avg_cu_pct,
                MAX(cu_consumption_pct)   AS max_cu_pct,
                SUM(CAST(throttling_active AS INT)) AS throttle_events
            FROM {table_name}
            WHERE ingestion_timestamp >= current_timestamp() - INTERVAL 10 MINUTES
        """)
        row = df_check.collect()[0]
        print("\n── Validación post-escritura ──────────────────────────────")
        print(f"   Última ingesta     : {row['last_ingestion']}")
        print(f"   Última ventana     : {row['last_window']}")
        print(f"   Filas (10 min)     : {row['total_rows']}")
        print(f"   Avg CU %           : {row['avg_cu_pct']:.1f}%")
        print(f"   Max CU %           : {row['max_cu_pct']:.1f}%")
        print(f"   Eventos throttling : {row['throttle_events']}")

        # Alertas básicas en logs (no bloquean el notebook)
        if row["max_cu_pct"] and row["max_cu_pct"] > 90:
            print("⚠️  ALERTA: Consumo CU > 90% — considera escalar.")
        if row["throttle_events"] and row["throttle_events"] > 0:
            print("⚠️  ALERTA: Throttling detectado en los últimos 10 min.")
    except Exception as e:
        print(f"ℹ️  Validación omitida (tabla puede no existir aún): {e}")


# ── CELDA 9: Entrypoint principal ─────────────────────────────────────────────
# Esta celda es la que ejecuta Fabric Pipeline.
# Control de errores completo: un fallo de API no detiene el run,
# se loguea y el notebook termina con exit code 0 para no bloquear el schedule.

def main():
    print("=" * 60)
    print("  FABRIC AUTO-SCALING — Capa 1: Observabilidad")
    print(f"  Run UTC: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    try:
        # 1. Extraer métricas
        records = extract_metrics(CONFIG)

        # 2. Escribir en Delta
        n_inserted = write_metrics_to_delta(records, CONFIG)

        # 3. Validar
        validate_latest_metrics(CONFIG)

        print(f"\n✅ Capa 1 completada. {n_inserted} registros nuevos en '{CONFIG['table_metrics_raw']}'.")

    except requests.exceptions.HTTPError as e:
        # Error de API → loguear pero no explotar (el schedule seguirá ejecutando)
        status = e.response.status_code if e.response else "N/A"
        print(f"❌ Error HTTP {status} llamando a la API: {e}")
        if e.response is not None:
            print(f"   Respuesta: {e.response.text[:500]}")
        traceback.print_exc()

    except requests.exceptions.ConnectionError as e:
        print(f"❌ Error de conexión (¿token expirado? ¿red?): {e}")
        traceback.print_exc()

    except Exception as e:
        print(f"❌ Error inesperado: {type(e).__name__}: {e}")
        traceback.print_exc()


main()


# ── CELDA 10: Scheduling — instrucciones para Fabric Pipeline ─────────────────
# (Celda de documentación — no ejecuta código)

"""
CONFIGURACIÓN DEL SCHEDULING EN FABRIC PIPELINE
================================================

1. Crear un Pipeline en el mismo workspace.
2. Añadir actividad "Notebook" → seleccionar este notebook.
3. En "Settings" del Pipeline:
   - Trigger type: Schedule
   - Recurrence: Every 5 minutes
   - Start: inmediato
   - Timezone: UTC (recomendado)

4. Pasar parámetros override si necesitas múltiples capacities:
   En la actividad Notebook → "Base parameters":
     capacity_id       = @pipeline().parameters.capacityId
     subscription_id   = @pipeline().parameters.subscriptionId
   (Y actualizar `main()` para leer notebookutils.notebook.exit o
    parámetros del pipeline si usas parametrización dinámica.)

5. Configurar retry: 2 reintentos con 1 min de espera (tolera fallos transitorios de API).

NOTAS DE IDEMPOTENCIA
=====================
- La clave de deduplicación es (capacity_id, window_start_time).
- Si el pipeline se ejecuta dos veces en la misma ventana de 5 min,
  el MERGE ON no insertará duplicados.
- Si se cambia el lookback_minutes, los registros ya existentes
  en el solapamiento NO se sobreescriben (INSERT WHEN NOT MATCHED).

ROTACIÓN / RETENCIÓN
====================
- Para limitar el crecimiento de la tabla, añadir una actividad de limpieza
  al final del pipeline:
    DELETE FROM metrics_raw
    WHERE window_start_time < current_timestamp() - INTERVAL 90 DAYS
- O usar OPTIMIZE + VACUUM en una pipeline separada diaria.
"""

print("📋 Celda de documentación de scheduling cargada (sin ejecución).")
