# Fabric Auto-Scaling System — Capa 3: Motor de Decisión
# =========================================================
# Notebook: layer3_decision_engine
# Descripción: Lee el urgency_score de Capa 2, aplica reglas de escalado
#              con budget awareness y cooldown de 15 min. Escribe la decisión
#              en decision_pending (buzón para Automation) y en decision_log.
# Idempotencia: un único registro pending por (capacity_id, run_timestamp).
#               Si ya existe una decisión no consumida, no genera otra.
# =========================================================


# ── CELDA 1: Configuración centralizada ──────────────────────────────────────

CONFIG = {
    # --- Identidad (debe coincidir con Capas 1 y 2) ---
    "capacity_id": "<YOUR_CAPACITY_ID>",

    # --- Delta tables ---
    "table_urgency_scores":  "urgency_scores",
    "table_decision_pending": "decision_pending",
    "table_decision_log":    "decision_log",

    # --- Umbrales de decisión ---
    "urgency_scale_up_threshold":   70,   # score > 70 → escalar arriba
    "urgency_scale_down_threshold": 20,   # score < 20 durante N min → bajar/pausar

    # Minutos consecutivos por debajo del umbral antes de scale_down / pause
    # Evita bajar la capacity por un valle momentáneo de actividad
    "scale_down_sustained_minutes": 30,

    # --- SKU ladder — orden estricto de escalado ---
    # Solo se puede subir/bajar un escalón por acción (evita saltos bruscos)
    "sku_ladder": ["F2", "F4", "F8", "F16", "F32", "F64", "F128", "F256", "F512", "F1024", "F2048"],
    "sku_min":    "F2",    # nunca bajará de aquí
    "sku_max":    "F64",   # nunca subirá de aquí

    # --- Cooldown entre acciones ---
    "cooldown_minutes": 15,   # mínimo entre dos acciones consecutivas

    # --- Budget mensual ---
    # Coste aproximado por hora de cada SKU en EUR (ajustar a tu región/contrato)
    # Fuente: https://azure.microsoft.com/pricing/details/microsoft-fabric/
    "sku_cost_eur_per_hour": {
        "F2":    0.36,
        "F4":    0.72,
        "F8":    1.44,
        "F16":   2.88,
        "F32":   5.76,
        "F64":  11.52,
        "F128": 23.04,
        "F256": 46.08,
        "F512": 92.16,
        "F1024":184.32,
        "F2048":368.64,
    },
    "budget_max_monthly_eur": 500.0,   # presupuesto mensual máximo
    # Porcentaje del presupuesto consumido a partir del cual bloquear scale_up
    "budget_block_scale_up_pct": 0.90,  # 90% del budget → no más scale_up

    # --- Pausa automática ---
    # Si el score lleva N min bajo el umbral Y el SKU es el mínimo → pausar
    "pause_when_at_sku_min": True,
    # Hora del día (UTC) fuera de la cual no se pausa automáticamente
    # None = pausar a cualquier hora
    "no_pause_hours_utc": None,   # ej: (7, 22) → no pausar entre 07:00 y 22:00 UTC

    # --- Modo seguro ---
    "dry_run": False,

    # --- Diagnóstico ---
    "verbose": True,
}

print("✅ Configuración Capa 3 cargada.")
_w = CONFIG["sku_ladder"]
print(f"   SKU ladder : {' → '.join(_w)}")
print(f"   Rango      : {CONFIG['sku_min']} – {CONFIG['sku_max']}")
print(f"   Cooldown   : {CONFIG['cooldown_minutes']} min")
print(f"   Budget     : {CONFIG['budget_max_monthly_eur']} EUR/mes")


# ── CELDA 2: Imports ──────────────────────────────────────────────────────────

import traceback
from datetime import datetime, timezone, timedelta
from enum import Enum

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField,
    StringType, DoubleType, LongType,
    BooleanType, TimestampType,
)

spark = SparkSession.builder.getOrCreate()
print(f"✅ Spark {spark.version} activo.")


# ── CELDA 3: Enumeración de acciones posibles ─────────────────────────────────

class Action(str, Enum):
    SCALE_UP   = "scale_up"     # subir un escalón de SKU
    SCALE_DOWN = "scale_down"   # bajar un escalón de SKU
    PAUSE      = "pause"        # suspender la capacity
    NOOP       = "noop"         # no hacer nada


# ── CELDA 4: Esquemas Delta ───────────────────────────────────────────────────

DECISION_PENDING_SCHEMA = StructType([
    StructField("run_id",           StringType(),   False),  # UUID del run
    StructField("run_timestamp",    TimestampType(), False),
    StructField("capacity_id",      StringType(),   False),
    StructField("action",           StringType(),   False),  # Action enum value
    StructField("sku_current",      StringType(),   True),   # SKU en el momento de la decisión
    StructField("sku_target",       StringType(),   True),   # SKU objetivo (None si pause/noop)
    StructField("urgency_score",    DoubleType(),   True),
    StructField("reason",           StringType(),   True),   # Motivo legible
    StructField("consumed",         BooleanType(),  False),  # Automation lo marca True al actuar
    StructField("source_notebook",  StringType(),   True),
])

DECISION_LOG_SCHEMA = StructType([
    StructField("run_id",                  StringType(),   False),
    StructField("run_timestamp",           TimestampType(), False),
    StructField("capacity_id",             StringType(),   False),
    StructField("action",                  StringType(),   False),
    StructField("sku_before",              StringType(),   True),
    StructField("sku_after",               StringType(),   True),   # None hasta que Automation confirme
    StructField("urgency_score",           DoubleType(),   True),
    StructField("score_consumption",       DoubleType(),   True),
    StructField("score_forecast",          DoubleType(),   True),
    StructField("score_anomaly",           DoubleType(),   True),
    StructField("reason",                  StringType(),   True),
    StructField("budget_consumed_eur",     DoubleType(),   True),   # coste acumulado mes actual
    StructField("budget_remaining_eur",    DoubleType(),   True),
    StructField("cost_per_hour_before",    DoubleType(),   True),
    StructField("cost_per_hour_after",     DoubleType(),   True),
    StructField("cooldown_active",         BooleanType(),  True),   # ¿Se bloqueó por cooldown?
    StructField("budget_blocked",          BooleanType(),  True),   # ¿Se bloqueó por budget?
    StructField("action_executed",         BooleanType(),  True),   # False hasta confirmación
    StructField("dry_run",                 BooleanType(),  False),
    StructField("source_notebook",         StringType(),   True),
])

print("✅ Esquemas decision_pending y decision_log definidos.")


# ── CELDA 5: Helpers de SKU ladder ───────────────────────────────────────────

def sku_index(sku: str, config: dict) -> int:
    try:
        return config["sku_ladder"].index(sku)
    except ValueError:
        raise ValueError(f"SKU desconocido: '{sku}'. Ladder: {config['sku_ladder']}")


def sku_up(sku: str, config: dict) -> str | None:
    """Devuelve el siguiente SKU en la escalera, respetando sku_max. None si ya está arriba."""
    idx     = sku_index(sku, config)
    max_idx = sku_index(config["sku_max"], config)
    return config["sku_ladder"][idx + 1] if idx < max_idx else None


def sku_down(sku: str, config: dict) -> str | None:
    """Devuelve el SKU anterior en la escalera, respetando sku_min. None si ya está abajo."""
    idx     = sku_index(sku, config)
    min_idx = sku_index(config["sku_min"], config)
    return config["sku_ladder"][idx - 1] if idx > min_idx else None


def cost_per_hour(sku: str, config: dict) -> float:
    return config["sku_cost_eur_per_hour"].get(sku, 0.0)


# ── CELDA 6: Leer estado actual desde Delta tables ────────────────────────────

def read_latest_urgency(config: dict) -> dict | None:
    """
    Lee el urgency_score más reciente de urgency_scores.
    Devuelve dict con todos los campos o None si no hay datos.
    """
    table = config["table_urgency_scores"]
    cap   = config["capacity_id"]
    try:
        row = spark.sql(f"""
            SELECT *
            FROM {table}
            WHERE capacity_id = '{cap}'
            ORDER BY run_timestamp DESC
            LIMIT 1
        """).collect()
        if not row:
            return None
        r = row[0].asDict()
        if config.get("verbose"):
            print(f"📊 Último urgency_score: {r['urgency_score']:.1f} "
                  f"(at {r['run_timestamp']})")
        return r
    except Exception as e:
        print(f"⚠️  No se pudo leer urgency_scores: {e}")
        return None


def read_last_action(config: dict) -> dict | None:
    """
    Lee la última acción registrada (excluye NOOP) desde decision_log.
    Usada para calcular si el cooldown ha expirado.
    """
    table = config["table_decision_log"]
    cap   = config["capacity_id"]
    try:
        row = spark.sql(f"""
            SELECT run_timestamp, action, sku_before, sku_after
            FROM {table}
            WHERE capacity_id = '{cap}'
              AND action != 'noop'
              AND dry_run = false
            ORDER BY run_timestamp DESC
            LIMIT 1
        """).collect()
        return row[0].asDict() if row else None
    except Exception:
        return None  # tabla no existe aún → primera ejecución


def read_current_sku(config: dict) -> str:
    """
    Lee el SKU actual desde la última entrada de metrics_raw.
    Fallback: sku_min si no hay datos.
    """
    table = config["table_metrics_raw"] if "table_metrics_raw" in config else "metrics_raw"
    cap   = config["capacity_id"]
    try:
        row = spark.sql(f"""
            SELECT sku FROM metrics_raw
            WHERE capacity_id = '{cap}'
              AND sku IS NOT NULL
            ORDER BY window_start_time DESC
            LIMIT 1
        """).collect()
        sku = row[0]["sku"] if row else config["sku_min"]
        if config.get("verbose"):
            print(f"🔧 SKU actual: {sku}")
        return sku
    except Exception:
        return config["sku_min"]


def read_low_urgency_streak(config: dict) -> int:
    """
    Cuenta cuántos minutos consecutivos el urgency_score ha estado
    por debajo del umbral scale_down.
    Usado para confirmar que el scale_down es sostenido.
    """
    table     = config["table_urgency_scores"]
    cap       = config["capacity_id"]
    threshold = config["urgency_scale_down_threshold"]
    lookback  = config["scale_down_sustained_minutes"] + 5  # margen

    try:
        rows = spark.sql(f"""
            SELECT urgency_score, run_timestamp
            FROM {table}
            WHERE capacity_id = '{cap}'
            ORDER BY run_timestamp DESC
            LIMIT {lookback}
        """).collect()

        if not rows:
            return 0

        # Contar desde el más reciente hacia atrás mientras score < threshold
        streak = 0
        for r in rows:
            if r["urgency_score"] < threshold:
                streak += 1
            else:
                break  # rompe la racha en cuanto encontramos un score alto

        if config.get("verbose"):
            print(f"📉 Racha de score bajo: {streak} ciclos "
                  f"(umbral={threshold}, requerido={config['scale_down_sustained_minutes']})")
        return streak
    except Exception:
        return 0


def read_budget_consumed_this_month(config: dict) -> float:
    """
    Estima el coste acumulado en el mes actual leyendo decision_log.
    Suma (horas entre acciones × coste_sku_periodo).
    Aproximación conservadora para no requerir Azure Cost Management API.
    """
    table = config["table_decision_log"]
    cap   = config["capacity_id"]

    now_utc     = datetime.now(timezone.utc)
    month_start = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    try:
        rows = spark.sql(f"""
            SELECT run_timestamp, sku_before, action
            FROM {table}
            WHERE capacity_id  = '{cap}'
              AND run_timestamp >= '{month_start.strftime('%Y-%m-%d %H:%M:%S')}'
              AND dry_run = false
            ORDER BY run_timestamp ASC
        """).collect()

        if not rows:
            return 0.0

        # Calcular coste acumulado por tramos de tiempo entre acciones
        total_cost = 0.0
        prev_ts    = month_start
        prev_sku   = rows[0]["sku_before"] or config["sku_min"]

        for r in rows:
            ts  = r["run_timestamp"].replace(tzinfo=timezone.utc)
            hours_elapsed = (ts - prev_ts).total_seconds() / 3600
            total_cost   += hours_elapsed * cost_per_hour(prev_sku, config)
            prev_ts       = ts
            prev_sku      = r["sku_before"] or prev_sku

        # Añadir tiempo desde la última acción hasta ahora
        hours_since_last = (now_utc - prev_ts).total_seconds() / 3600
        total_cost += hours_since_last * cost_per_hour(prev_sku, config)

        if config.get("verbose"):
            print(f"💰 Coste estimado mes actual: {total_cost:.2f} EUR "
                  f"/ {config['budget_max_monthly_eur']:.2f} EUR")
        return round(total_cost, 4)

    except Exception:
        return 0.0


def check_pending_decision(config: dict) -> bool:
    """
    Verifica si ya existe una decisión no consumida en decision_pending.
    Si existe → Automation no la ha procesado aún → no generar otra.
    """
    table = config["table_decision_pending"]
    cap   = config["capacity_id"]
    try:
        count = spark.sql(f"""
            SELECT COUNT(*) AS n
            FROM {table}
            WHERE capacity_id = '{cap}'
              AND consumed = false
        """).collect()[0]["n"]
        if count > 0 and config.get("verbose"):
            print(f"⏳ Ya existe {count} decisión(es) pendiente(s) sin consumir → skip")
        return count > 0
    except Exception:
        return False  # tabla no existe → no hay pendientes


# ── CELDA 7: Motor de decisión ────────────────────────────────────────────────

def decide(
    urgency_data:  dict,
    current_sku:   str,
    low_streak:    int,
    last_action:   dict | None,
    budget_consumed: float,
    config:        dict,
) -> tuple[Action, str, bool, bool]:
    """
    Aplica las reglas de decisión en orden de prioridad.
    Devuelve (action, reason, cooldown_active, budget_blocked).

    Orden de evaluación:
      1. ¿Cooldown activo?            → NOOP
      2. ¿Budget bloqueado?           → NOOP (si iba a escalar arriba)
      3. ¿Urgency > scale_up umbral?  → SCALE_UP
      4. ¿Urgency < scale_down umbral durante N min?
           ¿SKU ya en mínimo?        → PAUSE (si está configurado)
           Si no               → SCALE_DOWN
      5. Default                      → NOOP
    """
    score      = urgency_data["urgency_score"]
    now_utc    = datetime.now(timezone.utc)
    up_thresh  = config["urgency_scale_up_threshold"]
    dn_thresh  = config["urgency_scale_down_threshold"]
    cooldown_m = config["cooldown_minutes"]
    sustained  = config["scale_down_sustained_minutes"]

    cooldown_active = False
    budget_blocked  = False

    # ── 1. Cooldown ───────────────────────────────────────────────────────────
    if last_action:
        last_ts      = last_action["run_timestamp"]
        if hasattr(last_ts, "tzinfo") and last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)
        minutes_since = (now_utc - last_ts).total_seconds() / 60
        if minutes_since < cooldown_m:
            cooldown_active = True
            reason = (f"Cooldown activo: última acción hace "
                      f"{minutes_since:.1f} min (cooldown={cooldown_m} min)")
            if config.get("verbose"):
                print(f"⏱  {reason}")
            return Action.NOOP, reason, True, False

    # ── 2. Budget ─────────────────────────────────────────────────────────────
    budget_max   = config["budget_max_monthly_eur"]
    budget_block_threshold = budget_max * config["budget_block_scale_up_pct"]
    budget_blocked_flag = budget_consumed >= budget_block_threshold

    # ── 3. Scale UP ───────────────────────────────────────────────────────────
    if score >= up_thresh:
        if budget_blocked_flag:
            budget_blocked = True
            reason = (f"Score={score:.1f} requiere scale_up pero budget bloqueado: "
                      f"{budget_consumed:.2f}/{budget_max:.2f} EUR "
                      f"(≥{config['budget_block_scale_up_pct']*100:.0f}%)")
            if config.get("verbose"):
                print(f"💸 {reason}")
            return Action.NOOP, reason, False, True

        target = sku_up(current_sku, config)
        if target is None:
            reason = (f"Score={score:.1f} requiere scale_up pero SKU ya en máximo "
                      f"({current_sku} = {config['sku_max']})")
            return Action.NOOP, reason, False, False

        reason = (f"Urgency score {score:.1f} ≥ {up_thresh} → "
                  f"scale_up {current_sku} → {target}")
        return Action.SCALE_UP, reason, False, False

    # ── 4. Scale DOWN / Pause ─────────────────────────────────────────────────
    if score < dn_thresh and low_streak >= sustained:

        # ¿Ventana horaria de no-pause?
        if config["no_pause_hours_utc"]:
            h_start, h_end = config["no_pause_hours_utc"]
            current_hour = now_utc.hour
            in_active_window = h_start <= current_hour < h_end
        else:
            in_active_window = False

        # ¿Ya estamos en el SKU mínimo?
        at_sku_min = (current_sku == config["sku_min"])

        if at_sku_min and config["pause_when_at_sku_min"] and not in_active_window:
            reason = (f"Urgency score {score:.1f} < {dn_thresh} durante "
                      f"{low_streak} ciclos y SKU en mínimo ({current_sku}) → pause")
            return Action.PAUSE, reason, False, False

        if not at_sku_min:
            target = sku_down(current_sku, config)
            if target is None:
                reason = f"Score bajo pero SKU ya en mínimo ({current_sku})"
                return Action.NOOP, reason, False, False
            reason = (f"Urgency score {score:.1f} < {dn_thresh} durante "
                      f"{low_streak} ciclos → scale_down {current_sku} → {target}")
            return Action.SCALE_DOWN, reason, False, False

        reason = (f"Urgency score {score:.1f} < {dn_thresh} pero en ventana "
                  f"horaria protegida o condiciones no cumplen → noop")
        return Action.NOOP, reason, False, False

    # ── 5. Default ────────────────────────────────────────────────────────────
    reason = (f"Urgency score {score:.1f} en zona neutral "
              f"[{dn_thresh}–{up_thresh}] → no action")
    return Action.NOOP, reason, False, False


# ── CELDA 8: Escritura de decisión ───────────────────────────────────────────

def write_decision(
    action:          Action,
    reason:          str,
    urgency_data:    dict,
    current_sku:     str,
    budget_consumed: float,
    cooldown_active: bool,
    budget_blocked:  bool,
    config:          dict,
) -> str:
    """
    Escribe en decision_pending y decision_log.
    Devuelve el run_id generado.
    Idempotente: si ya existe el run_id no inserta duplicado (MERGE).
    """
    import uuid
    run_id     = str(uuid.uuid4())
    run_ts     = urgency_data["run_timestamp"]
    cap_id     = config["capacity_id"]
    score      = urgency_data["urgency_score"]
    budget_max = config["budget_max_monthly_eur"]

    # SKU objetivo según la acción
    if action == Action.SCALE_UP:
        sku_target = sku_up(current_sku, config)
    elif action == Action.SCALE_DOWN:
        sku_target = sku_down(current_sku, config)
    else:
        sku_target = None

    cost_before = cost_per_hour(current_sku, config)
    cost_after  = cost_per_hour(sku_target, config) if sku_target else (
        0.0 if action == Action.PAUSE else cost_before
    )

    if config.get("verbose"):
        print(f"\n── Decisión ────────────────────────────────────────────")
        print(f"   run_id   : {run_id}")
        print(f"   action   : {action.value}")
        print(f"   sku      : {current_sku} → {sku_target or '(sin cambio)'}")
        print(f"   reason   : {reason}")
        print(f"   cost/h   : {cost_before:.2f} → {cost_after:.2f} EUR")

    if config["dry_run"]:
        print(f"🔵 DRY RUN — decisión '{action.value}' no escrita en Delta.")
        return run_id

    # ── decision_pending ──────────────────────────────────────────────────────
    if action != Action.NOOP:
        pending_record = [{
            "run_id":          run_id,
            "run_timestamp":   run_ts,
            "capacity_id":     cap_id,
            "action":          action.value,
            "sku_current":     current_sku,
            "sku_target":      sku_target,
            "urgency_score":   score,
            "reason":          reason,
            "consumed":        False,
            "source_notebook": "layer3_decision_engine",
        }]
        df_pending = spark.createDataFrame(pending_record, schema=DECISION_PENDING_SCHEMA)
        _upsert_or_create(
            df_pending,
            config["table_decision_pending"],
            merge_keys="target.run_id = source.run_id",
            partition_by="capacity_id",
        )

    # ── decision_log ──────────────────────────────────────────────────────────
    log_record = [{
        "run_id":               run_id,
        "run_timestamp":        run_ts,
        "capacity_id":          cap_id,
        "action":               action.value,
        "sku_before":           current_sku,
        "sku_after":            sku_target,
        "urgency_score":        score,
        "score_consumption":    urgency_data.get("score_consumption"),
        "score_forecast":       urgency_data.get("score_forecast"),
        "score_anomaly":        urgency_data.get("score_anomaly"),
        "reason":               reason,
        "budget_consumed_eur":  budget_consumed,
        "budget_remaining_eur": round(budget_max - budget_consumed, 4),
        "cost_per_hour_before": cost_before,
        "cost_per_hour_after":  cost_after,
        "cooldown_active":      cooldown_active,
        "budget_blocked":       budget_blocked,
        "action_executed":      False,   # Automation lo actualiza a True al ejecutar
        "dry_run":              config["dry_run"],
        "source_notebook":      "layer3_decision_engine",
    }]
    df_log = spark.createDataFrame(log_record, schema=DECISION_LOG_SCHEMA)
    _upsert_or_create(
        df_log,
        config["table_decision_log"],
        merge_keys="target.run_id = source.run_id",
        partition_by="capacity_id",
    )

    return run_id


# ── CELDA 9: Helper Delta upsert ─────────────────────────────────────────────

def _upsert_or_create(df_spark, table: str, merge_keys: str, partition_by: str):
    df_spark.createOrReplaceTempView("_decision_tmp")
    try:
        from delta.tables import DeltaTable
        if DeltaTable.isDeltaTable(spark, f"Tables/{table}"):
            spark.sql(f"""
                MERGE INTO {table} AS target
                USING _decision_tmp AS source
                ON {merge_keys}
                WHEN NOT MATCHED THEN INSERT *
            """)
        else:
            raise Exception("tabla no existe")
    except Exception:
        (df_spark.write
                 .format("delta")
                 .mode("append")
                 .option("mergeSchema", "true")
                 .partitionBy(partition_by)
                 .saveAsTable(table))


# ── CELDA 10: Entrypoint principal ───────────────────────────────────────────

def main():
    print("=" * 60)
    print("  FABRIC AUTO-SCALING — Capa 3: Motor de Decisión")
    print(f"  Run UTC: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    try:
        # ── 1. Idempotencia: ¿ya hay decisión pendiente sin consumir? ─────────
        if check_pending_decision(CONFIG):
            print("ℹ️  Decisión pendiente existente — Automation aún no la ha procesado.")
            print("   Saltando este ciclo para evitar acumulación.")
            return

        # ── 2. Leer urgency score más reciente ────────────────────────────────
        urgency_data = read_latest_urgency(CONFIG)
        if not urgency_data:
            print("ℹ️  Sin datos de urgency_scores. ¿Ha corrido la Capa 2?")
            return

        # Verificar que el score es reciente (máx 2 ciclos = 10 min)
        score_age_min = (
            datetime.now(timezone.utc) -
            urgency_data["run_timestamp"].replace(tzinfo=timezone.utc)
        ).total_seconds() / 60
        if score_age_min > 10:
            print(f"⚠️  Urgency score tiene {score_age_min:.1f} min de antigüedad "
                  f"(máx 10 min). ¿Está corriendo la Capa 2?")
            return

        # ── 3. Leer estado del sistema ────────────────────────────────────────
        current_sku      = read_current_sku(CONFIG)
        low_streak       = read_low_urgency_streak(CONFIG)
        last_action      = read_last_action(CONFIG)
        budget_consumed  = read_budget_consumed_this_month(CONFIG)

        # ── 4. Decidir ────────────────────────────────────────────────────────
        action, reason, cooldown_active, budget_blocked = decide(
            urgency_data    = urgency_data,
            current_sku     = current_sku,
            low_streak      = low_streak,
            last_action     = last_action,
            budget_consumed = budget_consumed,
            config          = CONFIG,
        )

        # ── 5. Escribir decisión ──────────────────────────────────────────────
        run_id = write_decision(
            action          = action,
            reason          = reason,
            urgency_data    = urgency_data,
            current_sku     = current_sku,
            budget_consumed = budget_consumed,
            cooldown_active = cooldown_active,
            budget_blocked  = budget_blocked,
            config          = CONFIG,
        )

        print(f"\n✅ Capa 3 completada.")
        print(f"   run_id        : {run_id}")
        print(f"   action        : {action.value}")
        print(f"   reason        : {reason}")

        return action.value

    except Exception as e:
        print(f"❌ Error inesperado en Capa 3: {type(e).__name__}: {e}")
        traceback.print_exc()


main()
