"""
generate_data.py — Generador de datos sintéticos de vuelos
"""

import numpy as np
import pandas as pd
from pathlib import Path

np.random.seed(42)
N_FLIGHTS = 5_000

AIRLINES = ["Aerolínea A", "Aerolínea B", "Aerolínea C", "Aerolínea D"]

ROUTES = [
    ("Buenos Aires", "Miami",      8950, 450),
    ("Buenos Aires", "Madrid",    10050, 520),
    ("Buenos Aires", "São Paulo",  1900,  90),
    ("Buenos Aires", "Santiago",   1140,  70),
    ("Buenos Aires", "Lima",       3150, 150),
    ("Buenos Aires", "Bogotá",     4580, 200),
    ("Buenos Aires", "Ciudad de México", 7400, 380),
    ("Buenos Aires", "Nueva York", 8530, 420),
]

DAYS_OF_WEEK = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

records = []

for _ in range(N_FLIGHTS):
    origin, destination, distance_km, base_price = ROUTES[np.random.randint(len(ROUTES))]
    airline = np.random.choice(AIRLINES)
    days_in_advance = np.random.randint(1, 181)
    day_of_week = np.random.choice(DAYS_OF_WEEK)
    departure_hour = np.random.randint(0, 24)
    num_stops = np.random.choice([0, 1, 2], p=[0.50, 0.35, 0.15])

    price = base_price
    price += distance_km * 0.03

    if days_in_advance <= 7:
        price *= 1.60
    elif days_in_advance <= 30:
        price *= 1.10
    elif days_in_advance >= 90:
        price *= 0.85

    if day_of_week in ["Viernes", "Domingo"]:
        price *= 1.20
    elif day_of_week in ["Martes", "Miércoles"]:
        price *= 0.90

    if departure_hour < 6:
        price *= 0.85
    elif 7 <= departure_hour <= 9 or 17 <= departure_hour <= 20:
        price *= 1.15

    price -= num_stops * 25

    if airline == "Aerolínea A":
        price *= 1.15
    elif airline in ["Aerolínea C", "Aerolínea D"]:
        price *= 0.80

    noise = np.random.uniform(-0.10, 0.10)
    price *= (1 + noise)
    price = max(30, round(price, 2))

    records.append({
        "origin":          origin,
        "destination":     destination,
        "distance_km":     distance_km,
        "airline":         airline,
        "days_in_advance": days_in_advance,
        "day_of_week":     day_of_week,
        "departure_hour":  departure_hour,
        "num_stops":       num_stops,
        "price_usd":       price,
    })

Path("data").mkdir(exist_ok=True)
df = pd.DataFrame(records)
df.to_csv("data/flights_synthetic.csv", index=False)

print("✅ Dataset generado: data/flights_synthetic.csv")
print(f"   Filas: {len(df):,}")
print(f"\n📊 Estadísticas del precio (USD):")
print(df["price_usd"].describe().round(2).to_string())
print(f"\n🛫 Precio promedio por aerolínea:")
print(df.groupby("airline")["price_usd"].mean().round(2).to_string())
print(f"\n📅 Precio promedio por día de la semana:")
print(df.groupby("day_of_week")["price_usd"].mean().round(2).sort_values(ascending=False).to_string())