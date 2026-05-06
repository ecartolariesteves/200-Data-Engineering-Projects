# Fabric Auto-Scaling System — Capa 2: Análisis Predictivo
# ==========================================================
# Notebook: layer2_analytics
# Descripción: Lee metrics_raw, entrena Prophet para predecir demanda a 30 min,
#              detecta anomalías con Isolation Forest, y genera un urgency_score
#              0–100 que combina los tres señales. Escribe en Delta tables:
#                - predictions       (forecast Prophet por ventana)
#                - urgency_scores    (score final + componentes)
# Prerequisito: layer1_observability debe haber escrito datos en metrics_raw.
# ==========================================================


# ── CELDA 1: Configuración centralizada ──────────────────────────────────────

CONFIG = {
    # --- Identidad (debe coincidir con Capa 1) ---
    "capacity_id": "<YOUR_CAPACITY_ID>",

    # --- Lakehouse / Delta tables ---
    "table_metrics_raw":    "metrics_raw",
    "table_predictions":    "predictions",
    "table_urgency_scores": "urgency_scores",

    # --- Prophet ---
    # Mínimo de puntos históricos para entrenar (1 punto = 1 minuto)
    # Con 720 min (12h) de historia ya Prophet da predicciones útiles.
    "prophet_min_history_points": 60,        # mínimo absoluto para arrancar
    "prophet_preferred_history_h": 72,       # horas de historia preferidas para entrenar
    "prophet_forecast_horizon_min": 30,      # minutos a predecir hacia adelante
    "prophet_seasonality_mode": "additive",  # "additive" | "multiplicative"
    "prophet_interval_width": 0.80,          # intervalo de confianza (yhat_lower/upper)

    # --- Isolation Forest ---
    "iforest_contamination": 0.05,   # fracción esperada de anomalías (5%)
    "iforest_n_estimators": 100,
    "iforest_random_state": 42,
    # Features usadas para detección de anomalías
    "iforest_features": [
        "cu_consumption_pct",
        "cu_used",
        "queued_jobs",
        "throttling_rejected",
    ],

    # --- Urgency score: pesos de cada componente (deben sumar 1.0) ---
    # Ajustar según la sensibilidad deseada al escalado
    "weight_current_consumption": 0.40,   # consumo CU en tiempo real
    "weight_forecast":            0.35,   # predicción Prophet a 30 min
    "weight_anomaly":             0.25,   # señal de anomalía Isolation Forest

    # --- Umbrales de alerta (solo informativos aquí, los usa Capa 3) ---
    "urgency_scale_up_threshold":   70,
    "urgency_scale_down_threshold": 20,

    # --- Ventana de datos recientes para scoring en tiempo real ---
    "scoring_window_minutes": 10,    # últimos N minutos para calcular consumo actual

    # --- Modo seguro ---
    "dry_run": False,    # True → no escribe en Delta

    # --- Diagnóstico ---
    "verbose": True,
}

print("✅ Configuración Capa 2 cargada.")
print(f"   Horizonte forecast : {CONFIG['prophet_forecast_horizon_min']} min")
print(f"   Historia preferida : {CONFIG['prophet_preferred_history_h']}h")
print(f"   Pesos urgency      : consumo={CONFIG['weight_current_consumption']} "
      f"forecast={CONFIG['weight_forecast']} anomaly={CONFIG['weight_anomaly']}")
assert abs(
    CONFIG["weight_current_consumption"] +
    CONFIG["weight_forecast"] +
    CONFIG["weight_anomaly"] - 1.0
) < 1e-9, "❌ Los pesos del urgency score deben sumar exactamente 1.0"


# ── CELDA 2: Imports ──────────────────────────────────────────────────────────
# Prophet en Fabric Runtime 1.3: disponible via pip install prophet.
# En el notebook de Fabric añadir en la primera celda:
#   %pip install prophet --quiet
# El resto son librerías estándar del runtime.

import warnings
import traceback
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField,
    StringType, DoubleType, LongType,
    BooleanType, TimestampType, IntegerType,
)

warnings.filterwarnings("ignore")  # Prophet genera warnings de Stan, los silenciamos
spark = SparkSession.builder.getOrCreate()

# Importar Prophet y sklearn — con fallback claro si no están instalados
try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
    print("✅ Prophet disponible.")
except ImportError:
    PROPHET_AVAILABLE = False
    print("⚠️  Prophet no disponible. Ejecuta: %pip install prophet --quiet")
    print("   El notebook continuará en modo degradado (solo anomalías + consumo actual).")

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
    print("✅ scikit-learn disponible.")
except ImportError:
    SKLEARN_AVAILABLE = False
    print("⚠️  scikit-learn no disponible.")

print(f"✅ Spark {spark.version} activo.")


# ── CELDA 3: Esquemas Delta ───────────────────────────────────────────────────

PREDICTIONS_SCHEMA = StructType([
    StructField("run_timestamp",        TimestampType(), False),  # Momento de ejecución (UTC)
    StructField("capacity_id",          StringType(),   False),
    StructField("forecast_target_time", TimestampType(), False),  # Tiempo predicho
    StructField("yhat",                 DoubleType(),   True),    # Predicción central (% CU)
    StructField("yhat_lower",           DoubleType(),   True),    # Límite inferior IC
    StructField("yhat_upper",           DoubleType(),   True),    # Límite superior IC
    StructField("trend",                DoubleType(),   True),    # Componente tendencia
    StructField("history_points_used",  IntegerType(),  True),    # Puntos de historia usados
    StructField("model_trained_at",     TimestampType(), True),   # Cuándo se entrenó el modelo
    StructField("source_notebook",      StringType(),   True),
])

URGENCY_SCORES_SCHEMA = StructType([
    StructField("run_timestamp",         TimestampType(), False),
    StructField("capacity_id",           StringType(),   False),
    StructField("urgency_score",         DoubleType(),   False),  # 0–100, el score final
    StructField("score_consumption",     DoubleType(),   True),   # componente consumo actual
    StructField("score_forecast",        DoubleType(),   True),   # componente predicción
    StructField("score_anomaly",         DoubleType(),   True),   # componente anomalía
    StructField("current_cu_pct",        DoubleType(),   True),   # CU% promedio últimos N min
    StructField("forecast_cu_pct_30min", DoubleType(),   True),   # Predicción CU% en 30 min
    StructField("anomaly_detected",      BooleanType(),  True),   # ¿Anomalía activa?
    StructField("anomaly_score_raw",     DoubleType(),   True),   # Score crudo IForest (-1 a 0)
    StructField("data_points_used",      IntegerType(),  True),   # Puntos usados en scoring
    StructField("prophet_available",     BooleanType(),  True),   # ¿Prophet se usó?
    StructField("source_notebook",       StringType(),   True),
])

print("✅ Esquemas predictions y urgency_scores definidos.")


# ── CELDA 4: Carga de datos históricos desde metrics_raw ─────────────────────

def load_historical_metrics(config: dict) -> pd.DataFrame:
    """
    Lee metrics_raw de los últimos prophet_preferred_history_h horas.
    Si hay menos de prophet_min_history_points, lanza InsufficientDataError.
    Devuelve pandas DataFrame limpio y listo para Prophet/IForest.
    """
    table      = config["table_metrics_raw"]
    cap_id     = config["capacity_id"]
    hours_back = config["prophet_preferred_history_h"]
    min_points = config["prophet_min_history_points"]

    cutoff_str = (
        datetime.now(timezone.utc) - timedelta(hours=hours_back)
    ).strftime("%Y-%m-%d %H:%M:%S")

    df_spark = spark.sql(f"""
        SELECT
            window_start_time,
            cu_consumption_pct,
            cu_used,
            cu_limit,
            queued_jobs,
            throttling_active,
            throttling_rejected,
            sku
        FROM {table}
        WHERE capacity_id      = '{cap_id}'
          AND window_start_time >= '{cutoff_str}'
          AND cu_consumption_pct IS NOT NULL
        ORDER BY window_start_time ASC
    """)

    df = df_spark.toPandas()

    if config.get("verbose"):
        print(f"📥 Datos cargados: {len(df)} puntos "
              f"({hours_back}h de historia, capacity '{cap_id}')")

    if len(df) < min_points:
        raise ValueError(
            f"Datos insuficientes: {len(df)} puntos < mínimo {min_points}. "
            f"Espera a que Capa 1 acumule más historia."
        )

    # Limpiar y normalizar
    df["window_start_time"] = pd.to_datetime(df["window_start_time"], utc=True)
    df = df.sort_values("window_start_time").reset_index(drop=True)

    # Rellenar nulos en features secundarias con 0 (no afecta a cu_consumption_pct)
    for col in ["queued_jobs", "throttling_rejected"]:
        df[col] = df[col].fillna(0).astype(float)
    df["throttling_active"] = df["throttling_active"].fillna(False)

    return df


# ── CELDA 5: Modelo Prophet — forecast de CU% a 30 minutos ───────────────────

def run_prophet_forecast(df: pd.DataFrame, config: dict) -> dict:
    """
    Entrena Prophet sobre cu_consumption_pct y predice los próximos
    prophet_forecast_horizon_min minutos.

    Retorna dict con:
      - forecast_records: lista de dicts para tabla predictions
      - forecast_value_at_horizon: valor puntual de yhat en t+30min
      - yhat_upper_at_horizon: peor caso (límite superior IC)
      - model_trained_at: timestamp del entrenamiento
    """
    if not PROPHET_AVAILABLE:
        return {
            "forecast_records":          [],
            "forecast_value_at_horizon": None,
            "yhat_upper_at_horizon":     None,
            "model_trained_at":          None,
        }

    horizon_min   = config["prophet_forecast_horizon_min"]
    run_ts        = datetime.now(timezone.utc)

    # Prophet requiere columnas 'ds' y 'y'
    df_prophet = df[["window_start_time", "cu_consumption_pct"]].rename(
        columns={"window_start_time": "ds", "cu_consumption_pct": "y"}
    )
    # Prophet no acepta timezone-aware en ds → convertir a UTC naive
    df_prophet["ds"] = df_prophet["ds"].dt.tz_localize(None)

    # Clamp y a [0, 150] para evitar artefactos con valores extremos
    df_prophet["y"] = df_prophet["y"].clip(lower=0, upper=150)

    if config.get("verbose"):
        print(f"🔮 Entrenando Prophet con {len(df_prophet)} puntos...")

    model = Prophet(
        seasonality_mode=config["prophet_seasonality_mode"],
        interval_width=config["prophet_interval_width"],
        daily_seasonality=True,
        weekly_seasonality=len(df_prophet) >= 1440,  # solo si hay +24h de datos
        yearly_seasonality=False,
        changepoint_prior_scale=0.05,    # penaliza cambios bruscos de tendencia
        seasonality_prior_scale=10,
        uncertainty_samples=200,         # balance entre velocidad y precisión IC
    )

    # Estacionalidad intra-hora (patrones cada 15-60 min)
    model.add_seasonality(
        name="hourly",
        period=1 / 24,
        fourier_order=5,
    )

    model.fit(df_prophet)

    # Generar fechas futuras: 1 punto por minuto durante horizon_min
    last_ds  = df_prophet["ds"].max()
    future_dates = pd.date_range(
        start=last_ds + pd.Timedelta(minutes=1),
        periods=horizon_min,
        freq="1min",
    )
    future_df = pd.DataFrame({"ds": future_dates})
    forecast  = model.predict(future_df)

    # Clamp predicciones a [0, 200] — CU% no puede ser negativo
    forecast["yhat"]       = forecast["yhat"].clip(lower=0)
    forecast["yhat_lower"] = forecast["yhat_lower"].clip(lower=0)
    forecast["yhat_upper"] = forecast["yhat_upper"].clip(lower=0)

    if config.get("verbose"):
        last_row = forecast.iloc[-1]
        print(f"   t+{horizon_min}min → yhat={last_row['yhat']:.1f}% "
              f"[{last_row['yhat_lower']:.1f}, {last_row['yhat_upper']:.1f}]")

    # Valor de interés: predicción en el horizonte máximo (t+30min)
    target_row = forecast.iloc[-1]

    # Construir registros para Delta table predictions
    cap_id = config["capacity_id"]
    n_history = len(df_prophet)
    forecast_records = []
    for _, row in forecast.iterrows():
        forecast_records.append({
            "run_timestamp":        run_ts,
            "capacity_id":          cap_id,
            "forecast_target_time": row["ds"].to_pydatetime().replace(tzinfo=timezone.utc),
            "yhat":                 float(row["yhat"]),
            "yhat_lower":           float(row["yhat_lower"]),
            "yhat_upper":           float(row["yhat_upper"]),
            "trend":                float(row.get("trend", 0.0)),
            "history_points_used":  n_history,
            "model_trained_at":     run_ts,
            "source_notebook":      "layer2_analytics",
        })

    return {
        "forecast_records":          forecast_records,
        "forecast_value_at_horizon": float(target_row["yhat"]),
        "yhat_upper_at_horizon":     float(target_row["yhat_upper"]),
        "model_trained_at":          run_ts,
    }


# ── CELDA 6: Isolation Forest — detección de anomalías ───────────────────────

def run_isolation_forest(df: pd.DataFrame, config: dict) -> dict:
    """
    Entrena Isolation Forest sobre los últimos N puntos de historia.
    Evalúa si el punto MÁS RECIENTE es una anomalía.

    Retorna dict con:
      - anomaly_detected:   bool
      - anomaly_score_raw:  float entre -1 (muy anómalo) y 0 (normal)
      - score_anomaly:      float 0–100 para el urgency score
    """
    if not SKLEARN_AVAILABLE:
        return {
            "anomaly_detected":  False,
            "anomaly_score_raw": 0.0,
            "score_anomaly":     0.0,
        }

    features = [f for f in config["iforest_features"] if f in df.columns]
    if not features:
        print("⚠️  Ninguna feature de IForest disponible en los datos.")
        return {"anomaly_detected": False, "anomaly_score_raw": 0.0, "score_anomaly": 0.0}

    df_feat = df[features].fillna(0).astype(float)

    # Normalizar features (IForest es sensible a escala)
    scaler    = StandardScaler()
    X_scaled  = scaler.fit_transform(df_feat)

    model = IsolationForest(
        n_estimators=config["iforest_n_estimators"],
        contamination=config["iforest_contamination"],
        random_state=config["iforest_random_state"],
        n_jobs=-1,
    )
    model.fit(X_scaled)

    # Score del punto más reciente
    last_point      = X_scaled[-1].reshape(1, -1)
    prediction      = model.predict(last_point)[0]      # 1=normal, -1=anomalía
    raw_score       = model.score_samples(last_point)[0] # más negativo = más anómalo

    anomaly_detected = (prediction == -1)

    # Convertir raw_score a 0–100 para urgency:
    # score_samples suele estar en [-0.6, 0.0] aprox.
    # Normalizamos: más negativo → más urgente → score más alto
    # Clamp para robustez
    normalized = float(np.clip(-raw_score * 200, 0, 100))

    if config.get("verbose"):
        status = "🚨 ANOMALÍA" if anomaly_detected else "✅ Normal"
        print(f"🔍 Isolation Forest: {status} "
              f"(raw_score={raw_score:.4f}, score_anomaly={normalized:.1f})")

    return {
        "anomaly_detected":  bool(anomaly_detected),
        "anomaly_score_raw": float(raw_score),
        "score_anomaly":     normalized,
    }


# ── CELDA 7: Consumo actual — señal en tiempo real ────────────────────────────

def compute_current_consumption_score(df: pd.DataFrame, config: dict) -> dict:
    """
    Calcula el score de consumo actual basado en los últimos
    scoring_window_minutes puntos de metrics_raw.

    Lógica de conversión CU% → score 0–100:
      0–50%   → score lineal 0–40     (margen cómodo)
      50–80%  → score lineal 40–75    (zona de atención)
      80–95%  → score lineal 75–95    (zona crítica)
      95–100% → score lineal 95–100   (throttling inminente)
    Esta curva es intencionalmente no lineal: queremos reaccionar
    antes de llegar al 100%.
    """
    window_min = config["scoring_window_minutes"]
    now_utc    = datetime.now(timezone.utc)
    cutoff     = now_utc - timedelta(minutes=window_min)

    df_recent = df[df["window_start_time"] >= cutoff]
    if df_recent.empty:
        df_recent = df.tail(window_min)

    avg_cu_pct = float(df_recent["cu_consumption_pct"].mean())

    # Curva no lineal por tramos
    if avg_cu_pct <= 50:
        score = (avg_cu_pct / 50) * 40
    elif avg_cu_pct <= 80:
        score = 40 + ((avg_cu_pct - 50) / 30) * 35
    elif avg_cu_pct <= 95:
        score = 75 + ((avg_cu_pct - 80) / 15) * 20
    else:
        score = 95 + ((avg_cu_pct - 95) / 5) * 5

    score = float(np.clip(score, 0, 100))

    # Bonus por throttling activo: +15 puntos (cap a 100)
    throttle_count = int(df_recent["throttling_active"].sum())
    if throttle_count > 0:
        score = min(100.0, score + 15.0)
        if config.get("verbose"):
            print(f"⚡ Throttling activo en {throttle_count} puntos → +15 bonus")

    if config.get("verbose"):
        print(f"📈 Consumo actual: avg_cu={avg_cu_pct:.1f}% → score_consumption={score:.1f}")

    return {
        "current_cu_pct":    avg_cu_pct,
        "score_consumption": score,
        "data_points_used":  len(df_recent),
    }


# ── CELDA 8: Urgency score final — combinación ponderada ─────────────────────

def compute_urgency_score(
    score_consumption: float,
    score_forecast:    float,
    score_anomaly:     float,
    config:            dict,
) -> float:
    """
    Combina los tres componentes con los pesos configurados.
    Aplica un boost adicional si dos o más señales son simultáneamente altas
    (convergencia de señales → situación más urgente de lo que indica cada una sola).

    Boost de convergencia:
      Si ≥ 2 componentes > 70 → +10 puntos (cap a 100)
      Si ≥ 2 componentes > 85 → +20 puntos (cap a 100)
    """
    w_c = config["weight_current_consumption"]
    w_f = config["weight_forecast"]
    w_a = config["weight_anomaly"]

    base_score = (
        score_consumption * w_c +
        score_forecast    * w_f +
        score_anomaly     * w_a
    )

    # Boost por convergencia
    high_signals = sum([
        score_consumption > 70,
        score_forecast    > 70,
        score_anomaly     > 70,
    ])
    very_high_signals = sum([
        score_consumption > 85,
        score_forecast    > 85,
        score_anomaly     > 85,
    ])

    boost = 0
    if very_high_signals >= 2:
        boost = 20
    elif high_signals >= 2:
        boost = 10

    urgency = float(np.clip(base_score + boost, 0, 100))

    if config.get("verbose"):
        print(f"\n── Urgency Score ──────────────────────────────────────")
        print(f"   score_consumption : {score_consumption:.1f} (×{w_c})")
        print(f"   score_forecast    : {score_forecast:.1f} (×{w_f})")
        print(f"   score_anomaly     : {score_anomaly:.1f} (×{w_a})")
        print(f"   boost convergencia: +{boost}")
        print(f"   ▶ URGENCY SCORE   : {urgency:.1f} / 100")
        if urgency >= config["urgency_scale_up_threshold"]:
            print(f"   ⚠️  Por encima del umbral scale_up ({config['urgency_scale_up_threshold']})")
        elif urgency <= config["urgency_scale_down_threshold"]:
            print(f"   ✅ Por debajo del umbral scale_down ({config['urgency_scale_down_threshold']})")

    return urgency


# ── CELDA 9: Escritura idempotente en Delta ───────────────────────────────────

def write_predictions(records: list, config: dict):
    if not records or config["dry_run"]:
        if config.get("verbose") and not records:
            print("ℹ️  Sin predicciones que escribir (Prophet no disponible o dry_run).")
        return

    df_spark = spark.createDataFrame(records, schema=PREDICTIONS_SCHEMA)
    df_spark.createOrReplaceTempView("predictions_incoming")

    table = config["table_predictions"]
    _upsert_or_create(
        df_spark, table,
        merge_keys="target.capacity_id = source.capacity_id "
                   "AND target.run_timestamp = source.run_timestamp "
                   "AND target.forecast_target_time = source.forecast_target_time",
        partition_by="capacity_id",
    )
    if config.get("verbose"):
        print(f"✅ {len(records)} predicciones escritas en '{table}'.")


def write_urgency_score(record: dict, config: dict):
    if config["dry_run"]:
        print(f"🔵 DRY RUN — urgency_score={record['urgency_score']:.1f} (no escrito)")
        return

    df_spark = spark.createDataFrame([record], schema=URGENCY_SCORES_SCHEMA)
    table = config["table_urgency_scores"]
    _upsert_or_create(
        df_spark, table,
        merge_keys="target.capacity_id = source.capacity_id "
                   "AND target.run_timestamp = source.run_timestamp",
        partition_by="capacity_id",
    )
    if config.get("verbose"):
        print(f"✅ Urgency score escrito en '{table}'.")


def _upsert_or_create(df_spark, table: str, merge_keys: str, partition_by: str):
    """Helper: MERGE idempotente o CREATE en primera ejecución."""
    df_spark.createOrReplaceTempView("_incoming_tmp")
    try:
        from delta.tables import DeltaTable
        if DeltaTable.isDeltaTable(spark, f"Tables/{table}"):
            spark.sql(f"""
                MERGE INTO {table} AS target
                USING _incoming_tmp AS source
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


# ── CELDA 10: Entrypoint principal ────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  FABRIC AUTO-SCALING — Capa 2: Análisis Predictivo")
    print(f"  Run UTC: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    run_ts = datetime.now(timezone.utc)

    try:
        # ── 1. Cargar historia ────────────────────────────────────────────────
        df_history = load_historical_metrics(CONFIG)

        # ── 2. Prophet forecast ───────────────────────────────────────────────
        prophet_result = run_prophet_forecast(df_history, CONFIG)

        # Score forecast: usamos yhat_upper (peor caso) para ser conservadores
        # Si Prophet no está disponible, score_forecast = score_consumption (degradado)
        if prophet_result["forecast_value_at_horizon"] is not None:
            # Convertimos yhat_upper a score con la misma curva no lineal
            yhat_upper = prophet_result["yhat_upper_at_horizon"]
            if yhat_upper <= 50:
                score_forecast = (yhat_upper / 50) * 40
            elif yhat_upper <= 80:
                score_forecast = 40 + ((yhat_upper - 50) / 30) * 35
            elif yhat_upper <= 95:
                score_forecast = 75 + ((yhat_upper - 80) / 15) * 20
            else:
                score_forecast = 95 + ((yhat_upper - 95) / 5) * 5
            score_forecast = float(np.clip(score_forecast, 0, 100))
            forecast_cu_pct_30min = prophet_result["forecast_value_at_horizon"]
        else:
            score_forecast        = 0.0
            forecast_cu_pct_30min = None

        # ── 3. Isolation Forest ───────────────────────────────────────────────
        iforest_result = run_isolation_forest(df_history, CONFIG)

        # ── 4. Consumo actual ─────────────────────────────────────────────────
        consumption_result = compute_current_consumption_score(df_history, CONFIG)

        # ── 5. Urgency score ──────────────────────────────────────────────────
        urgency = compute_urgency_score(
            score_consumption=consumption_result["score_consumption"],
            score_forecast=score_forecast,
            score_anomaly=iforest_result["score_anomaly"],
            config=CONFIG,
        )

        # ── 6. Escribir predictions ───────────────────────────────────────────
        write_predictions(prophet_result["forecast_records"], CONFIG)

        # ── 7. Escribir urgency score ─────────────────────────────────────────
        urgency_record = {
            "run_timestamp":         run_ts,
            "capacity_id":           CONFIG["capacity_id"],
            "urgency_score":         urgency,
            "score_consumption":     consumption_result["score_consumption"],
            "score_forecast":        score_forecast,
            "score_anomaly":         iforest_result["score_anomaly"],
            "current_cu_pct":        consumption_result["current_cu_pct"],
            "forecast_cu_pct_30min": forecast_cu_pct_30min,
            "anomaly_detected":      iforest_result["anomaly_detected"],
            "anomaly_score_raw":     iforest_result["anomaly_score_raw"],
            "data_points_used":      consumption_result["data_points_used"],
            "prophet_available":     PROPHET_AVAILABLE,
            "source_notebook":       "layer2_analytics",
        }
        write_urgency_score(urgency_record, CONFIG)

        print(f"\n✅ Capa 2 completada.")
        print(f"   urgency_score        : {urgency:.1f} / 100")
        print(f"   anomaly_detected     : {iforest_result['anomaly_detected']}")
        print(f"   forecast_cu_30min    : "
              f"{forecast_cu_pct_30min:.1f}%" if forecast_cu_pct_30min else "   forecast_cu_30min    : N/A")

        # Devolver el urgency_score para que Capa 3 pueda encadenarse
        # en el mismo pipeline (vía notebookutils si se usan notebooks encadenados)
        return urgency

    except ValueError as e:
        # Datos insuficientes — es un estado temporal esperado al inicio
        print(f"ℹ️  {e}")
        print("   El sistema necesita acumular historia. Reintentará en el próximo ciclo.")

    except Exception as e:
        print(f"❌ Error inesperado en Capa 2: {type(e).__name__}: {e}")
        traceback.print_exc()


main()


# ── CELDA 11: Nota sobre instalación de Prophet en Fabric ────────────────────

"""
INSTALACIÓN DE PROPHET EN FABRIC NOTEBOOKS
===========================================
Prophet no viene preinstalado en Fabric Runtime 1.3.
Añadir como primera celda del notebook:

    %pip install prophet --quiet

O configurarlo a nivel de entorno en el Lakehouse Environment:
  Workspace → Environments → [tu environment] → Libraries → pip → prophet

La segunda opción es preferida para producción porque evita reinstalar
en cada ejecución del notebook y aplica a todos los notebooks del workspace.

TIEMPO DE INSTALACIÓN PRIMERA VEZ: ~2-3 minutos
Ejecuciones posteriores con environment preconfigurado: ~0 segundos

COMPATIBILIDAD
==============
Prophet 1.1.x es compatible con:
  - Python 3.10 / 3.11   ✅
  - Pandas 1.x / 2.x     ✅ (con minor warnings en 2.x, ya silenciados)
  - PySpark 3.4           ✅ (Prophet corre en el driver, no en workers)

NOTA: Prophet entrena en pandas/CPU en el nodo driver.
Para capacities pequeñas (F2/F4) con datasets grandes (>100k puntos),
considera reducir prophet_preferred_history_h a 24h.
"""

print("📋 Notas de instalación cargadas.")
