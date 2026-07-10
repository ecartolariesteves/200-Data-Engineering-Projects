"""
ingestion/load_to_bigquery.py
------------------------------
Simula la capa de ingesta (Cloud Run en producción).
Lee los CSVs de /data/<origen>/ y los carga en BigQuery
en datasets separados por origen: raw_allard, raw_sap_1, etc.

USO:
    pip install -r requirements.txt
    cp ../.env.example ../.env
    python load_to_bigquery.py

    # Cargar solo un origen:
    python load_to_bigquery.py --origen sap_1

REQUISITOS:
    - Fichero .env con las variables (ver .env.example)
    - Autenticación GCP via ADC (VS Code / gcloud auth application-default login)
"""

import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv
from google.cloud import bigquery

# ── Cargar variables de entorno ──────────────────────────────────────────────
load_dotenv(Path(__file__).parent.parent / ".env")

PROJECT_ID = os.getenv("GCP_PROJECT_ID")
LOCATION   = os.getenv("GCP_REGION", "europe-west6")
DATA_DIR   = Path(__file__).parent.parent / "data"

# ── Orígenes configurados ────────────────────────────────────────────────────
# clave: nombre carpeta en /data  →  nombre dataset RAW en BigQuery
ORIGINS = {
    "allard":     "raw_allard",
    "as400_1":    "raw_as400_1",
    "gesbox":     "raw_gesbox",
    "hist_as400": "raw_hist_as400",
    "nav":        "raw_nav",
    "rts_1":      "raw_rts_1",
    "rts_2":      "raw_rts_2",
    "rts_3":      "raw_rts_3",
    "sap_1":      "raw_sap_1",
    "sap_2":      "raw_sap_2",
    "sis":        "raw_sis",
}

TABLES = ["customers", "orders"]


def get_client() -> bigquery.Client:
    keyfile = os.getenv("GCP_KEYFILE_PATH")
    if keyfile:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = keyfile
    return bigquery.Client(project=PROJECT_ID)


def ensure_dataset(client: bigquery.Client, dataset_id: str) -> None:
    full_id = f"{PROJECT_ID}.{dataset_id}"
    dataset = bigquery.Dataset(full_id)
    dataset.location = LOCATION
    client.create_dataset(dataset, exists_ok=True)
    print(f"  ✅ Dataset listo: {dataset_id}")


def load_csv(client: bigquery.Client, csv_path: Path, table_id: str) -> None:
    if not csv_path.exists():
        print(f"  ⚠️  No encontrado: {csv_path.name} — saltando")
        return

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        autodetect=True,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )

    with open(csv_path, "rb") as f:
        job = client.load_table_from_file(f, table_id, job_config=job_config)

    job.result()
    table = client.get_table(table_id)
    print(f"  ✅ {csv_path.name} → {table_id.split('.')[-1]} ({table.num_rows} filas)")


def load_origin(client: bigquery.Client, origin: str, dataset: str) -> None:
    print(f"\n📦 Origen: {origin.upper()} → {dataset}")
    ensure_dataset(client, dataset)
    for table_name in TABLES:
        csv_path = DATA_DIR / origin / f"{table_name}.csv"
        table_id = f"{PROJECT_ID}.{dataset}.{table_name}"
        load_csv(client, csv_path, table_id)


def main():
    parser = argparse.ArgumentParser(description="Carga datos RAW en BigQuery por origen")
    parser.add_argument("--origen", help="Cargar solo un origen (ej: sap_1)", default=None)
    args = parser.parse_args()

    if not PROJECT_ID:
        print("❌ GCP_PROJECT_ID no está definido en .env")
        sys.exit(1)

    if args.origen and args.origen not in ORIGINS:
        print(f"❌ Origen '{args.origen}' no existe. Disponibles: {list(ORIGINS.keys())}")
        sys.exit(1)

    origins_to_load = {args.origen: ORIGINS[args.origen]} if args.origen else ORIGINS

    print(f"\n🚀 Iniciando ingesta hacia BigQuery")
    print(f"   Proyecto : {PROJECT_ID}")
    print(f"   Región   : {LOCATION}")
    print(f"   Orígenes : {len(origins_to_load)}")

    client = get_client()

    for origin, dataset in origins_to_load.items():
        load_origin(client, origin, dataset)

    print(f"\n🎉 Ingesta completada — {len(origins_to_load)} origen(es) cargados")
    print(f"   Ahora ejecuta: cd ../dbt_poc && dbt run\n")


if __name__ == "__main__":
    main()
