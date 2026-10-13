"""
generate_data.py
----------------
Generates synthetic financial data for the DW Star Schema project.
Outputs CSV files to ./raw/ simulating a source transactional system.

Tables generated:
  - accounts.csv       : bank accounts (customers)
  - products.csv       : financial products (savings, credit, etc.)
  - transactions.csv   : financial transactions
  - account_changes.csv: account attribute changes (for SCD Type 2 demo)
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

from faker import Faker

# ── Config ─────────────────────────────────────────────────────────────────────
SEED            = 42
N_ACCOUNTS      = 500
N_PRODUCTS      = 12
N_TRANSACTIONS  = 50_000
START_DATE      = date(2022, 1, 1)
END_DATE        = date(2024, 12, 31)
OUTPUT_DIR      = Path(__file__).parent / "raw"

fake = Faker("es_ES")
Faker.seed(SEED)
random.seed(SEED)

OUTPUT_DIR.mkdir(exist_ok=True)

# ── Helpers ────────────────────────────────────────────────────────────────────
def rand_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))

def fmt(d: date) -> str:
    return d.strftime("%Y-%m-%d")

# ── 1. Products ────────────────────────────────────────────────────────────────
PRODUCT_CATALOG = [
    ("PRD-001", "Cuenta Corriente",      "Depósito",   0.00,  0.00),
    ("PRD-002", "Cuenta de Ahorro",      "Depósito",   2.50,  0.00),
    ("PRD-003", "Cuenta Ahorro Plus",    "Depósito",   4.10,  0.00),
    ("PRD-004", "Tarjeta de Crédito",    "Crédito",    0.00, 28.99),
    ("PRD-005", "Tarjeta Black",         "Crédito",    0.00, 22.50),
    ("PRD-006", "Préstamo Personal",     "Crédito",    0.00, 12.75),
    ("PRD-007", "Préstamo Hipotecario",  "Hipoteca",   0.00,  5.25),
    ("PRD-008", "Préstamo Automotriz",   "Crédito",    0.00,  9.99),
    ("PRD-009", "Fondo de Inversión A",  "Inversión",  6.80,  0.00),
    ("PRD-010", "Fondo de Inversión B",  "Inversión",  9.20,  0.00),
    ("PRD-011", "Plazo Fijo 30d",        "Depósito",   5.50,  0.00),
    ("PRD-012", "Plazo Fijo 90d",        "Depósito",   6.30,  0.00),
]

with open(OUTPUT_DIR / "products.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["product_id","product_name","product_category",
                "interest_rate_pct","fee_rate_pct","is_active","created_at"])
    for pid, name, cat, ir, fr in PRODUCT_CATALOG:
        w.writerow([pid, name, cat, ir, fr, True, "2022-01-01"])

print(f"✓ products.csv       — {len(PRODUCT_CATALOG)} rows")

# ── 2. Accounts ────────────────────────────────────────────────────────────────
SEGMENTS    = ["Retail", "Premium", "Empresas", "Pyme"]
RISK_LEVELS = ["Bajo", "Medio", "Alto"]
BRANCHES    = ["Madrid", "Barcelona", "Valencia", "Sevilla",
               "Bilbao", "Zaragoza", "Málaga", "Alicante"]

accounts = []
for i in range(1, N_ACCOUNTS + 1):
    open_date = rand_date(START_DATE, date(2023, 6, 30))
    product   = random.choice(PRODUCT_CATALOG)
    accounts.append({
        "account_id":    f"ACC-{i:05d}",
        "customer_name": fake.name(),
        "email":         fake.email(),
        "phone":         fake.phone_number(),
        "branch":        random.choice(BRANCHES),
        "segment":       random.choice(SEGMENTS),
        "risk_level":    random.choice(RISK_LEVELS),
        "product_id":    product[0],
        "open_date":     fmt(open_date),
        "status":        random.choices(["Activa", "Inactiva", "Cerrada"],
                                        weights=[80, 15, 5])[0],
        "credit_limit":  round(random.uniform(0, 500_000), 2),
        "balance":       round(random.uniform(-50_000, 2_000_000), 2),
        "created_at":    fmt(open_date),
        "updated_at":    fmt(open_date),
    })

with open(OUTPUT_DIR / "accounts.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=accounts[0].keys())
    w.writeheader()
    w.writerows(accounts)

print(f"✓ accounts.csv       — {len(accounts)} rows")

# ── 3. Account changes (SCD Type 2 source) ─────────────────────────────────────
# Simulate ~30% of accounts getting segment or risk_level changes over time
CHANGES = []
for acc in accounts:
    if random.random() < 0.30:
        change_date = rand_date(
            date.fromisoformat(acc["open_date"]) + timedelta(days=90),
            END_DATE
        )
        old_segment   = acc["segment"]
        new_segment   = random.choice([s for s in SEGMENTS if s != old_segment])
        old_risk      = acc["risk_level"]
        new_risk      = random.choice([r for r in RISK_LEVELS if r != old_risk])
        CHANGES.append({
            "change_id":    f"CHG-{len(CHANGES)+1:06d}",
            "account_id":   acc["account_id"],
            "change_date":  fmt(change_date),
            "field_changed": random.choice(["segment", "risk_level"]),
            "old_value":    old_segment if random.random() < 0.5 else old_risk,
            "new_value":    new_segment if random.random() < 0.5 else new_risk,
            "new_segment":  new_segment,
            "new_risk_level": new_risk,
            "changed_by":   "SYSTEM",
        })

with open(OUTPUT_DIR / "account_changes.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=CHANGES[0].keys())
    w.writeheader()
    w.writerows(CHANGES)

print(f"✓ account_changes.csv — {len(CHANGES)} rows")

# ── 4. Transactions ────────────────────────────────────────────────────────────
TXN_TYPES = [
    ("Transferencia Entrante",  "Crédito",  True),
    ("Transferencia Saliente",  "Débito",   True),
    ("Pago de Servicio",        "Débito",   True),
    ("Pago de Tarjeta",         "Débito",   True),
    ("Depósito en Efectivo",    "Crédito",  True),
    ("Extracción ATM",          "Débito",   True),
    ("Débito Automático",       "Débito",   True),
    ("Acreditación de Sueldo",  "Crédito",  True),
    ("Compra con Débito",       "Débito",   True),
    ("Interés Acreditado",      "Crédito",  False),
    ("Comisión Bancaria",       "Débito",   False),
    ("Ajuste Manual",           "Crédito",  False),
]

CURRENCIES   = ["ARS", "USD", "EUR"]
CHANNELS     = ["App Móvil", "Web", "ATM", "Sucursal", "Homebanking", "API"]
STATUS_POOL  = ["Completada", "Completada", "Completada",
                "Completada", "Pendiente", "Rechazada"]

# Build lookup: account_id → open_date (transactions must be >= open_date)
account_open = {a["account_id"]: date.fromisoformat(a["open_date"]) for a in accounts}
account_ids  = list(account_open.keys())

transactions = []
for i in range(1, N_TRANSACTIONS + 1):
    acc_id     = random.choice(account_ids)
    open_dt    = account_open[acc_id]
    txn_date   = rand_date(open_dt, END_DATE)  # always >= open_date
    txn_type   = random.choice(TXN_TYPES)
    currency   = random.choices(CURRENCIES, weights=[70, 25, 5])[0]
    amount     = round(random.lognormvariate(8, 2), 2)   # realistic skew
    fee        = round(amount * random.uniform(0, 0.015), 2) if txn_type[2] else 0.0
    transactions.append({
        "transaction_id":   f"TXN-{i:08d}",
        "account_id":       acc_id,
        "transaction_date": fmt(txn_date),
        "transaction_type": txn_type[0],
        "direction":        txn_type[1],
        "amount":           amount,
        "fee_amount":       fee,
        "net_amount":       round(amount - fee, 2),
        "currency":         currency,
        "exchange_rate":    round(random.uniform(0.9, 1.1), 6) if currency != "ARS" else 1.0,
        "channel":          random.choice(CHANNELS),
        "status":           random.choice(STATUS_POOL),
        "description":      fake.sentence(nb_words=5),
        "reference_id":     fake.uuid4(),
        "created_at":       fmt(txn_date),
    })

with open(OUTPUT_DIR / "transactions.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=transactions[0].keys())
    w.writeheader()
    w.writerows(transactions)

print(f"✓ transactions.csv   — {len(transactions):,} rows")
print(f"\n✅ All raw files written to: {OUTPUT_DIR.resolve()}")
