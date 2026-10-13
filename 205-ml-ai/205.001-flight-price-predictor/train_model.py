"""
train_model.py — Pipeline completo de entrenamiento
"""

import joblib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer

print("=" * 55)
print("  PASO 1: ML CLÁSICO — Predictor de Precios de Vuelos")
print("=" * 55)

csv_path = Path("data/flights_synthetic.csv")
if not csv_path.exists():
    raise FileNotFoundError("Ejecutá primero: python generate_data.py")

df = pd.read_csv(csv_path)
print(f"\n✅ Datos cargados: {len(df):,} vuelos, {df.shape[1]} columnas")

CATEGORICAL_FEATURES = ["origin", "destination", "airline", "day_of_week"]
NUMERICAL_FEATURES   = ["distance_km", "days_in_advance", "departure_hour", "num_stops"]
TARGET = "price_usd"

X = df[CATEGORICAL_FEATURES + NUMERICAL_FEATURES]
y = df[TARGET]

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
print(f"\n✂️  Train: {len(X_train):,} · Test: {len(X_test):,}")

preprocessor = ColumnTransformer(transformers=[
    ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES),
    ("num", StandardScaler(), NUMERICAL_FEATURES),
])

models = {
    "LinearRegression": Pipeline([
        ("preprocessor", preprocessor),
        ("model", LinearRegression()),
    ]),
    "RandomForest": Pipeline([
        ("preprocessor", preprocessor),
        ("model", RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)),
    ]),
}

results = {}

for name, pipeline in models.items():
    print(f"\n⏳ Entrenando {name}...")
    pipeline.fit(X_train, y_train)
    y_pred = pipeline.predict(X_test)

    mae  = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2   = r2_score(y_test, y_pred)

    results[name] = {"mae": mae, "rmse": rmse, "r2": r2, "pipeline": pipeline, "y_pred": y_pred}
    print(f"   MAE:  ${mae:.2f} · RMSE: ${rmse:.2f} · R²: {r2:.4f}")

best_name = min(results, key=lambda k: results[k]["mae"])
print(f"\n🏆 Mejor modelo: {best_name} (MAE ${results[best_name]['mae']:.2f})")

# Feature importance
rf_pipeline = results["RandomForest"]["pipeline"]
rf_model    = rf_pipeline.named_steps["model"]
prep        = rf_pipeline.named_steps["preprocessor"]
cat_names   = prep.named_transformers_["cat"].get_feature_names_out(CATEGORICAL_FEATURES)
feature_names = list(cat_names) + NUMERICAL_FEATURES

feat_df = pd.DataFrame({"feature": feature_names, "importance": rf_model.feature_importances_})
feat_df = feat_df.sort_values("importance", ascending=False).head(10)

print("\n📊 Top 10 features más importantes (RandomForest):")
for _, row in feat_df.iterrows():
    bar = "█" * int(row["importance"] * 100)
    print(f"   {row['feature']:<30} {bar} {row['importance']:.4f}")

Path("models").mkdir(exist_ok=True)
joblib.dump(results[best_name]["pipeline"], "models/flight_model.pkl")
print("\n💾 Modelo guardado en: models/flight_model.pkl")

# Gráfico
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle("Evaluación del modelo — Predictor de Precios de Vuelos")
for idx, (name, res) in enumerate(results.items()):
    ax = axes[idx]
    ax.scatter(y_test, res["y_pred"], alpha=0.4, s=8, color="#1E88E5")
    lims = [min(y_test.min(), res["y_pred"].min()), max(y_test.max(), res["y_pred"].max())]
    ax.plot(lims, lims, "r--", linewidth=1, label="Predicción perfecta")
    ax.set_xlabel("Precio real (USD)")
    ax.set_ylabel("Precio predicho (USD)")
    ax.set_title(f"{name}\nMAE: ${res['mae']:.2f} | R²: {res['r2']:.4f}")
    ax.legend(fontsize=8)
plt.tight_layout()
plt.savefig("data/evaluation_plot.png", dpi=150, bbox_inches="tight")
print("📈 Gráfico guardado en: data/evaluation_plot.png")
print("\n✅ Listo. Corré: streamlit run app/streamlit_app.py")