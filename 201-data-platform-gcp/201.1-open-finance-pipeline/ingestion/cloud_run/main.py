"""
Open Finance Data Platform
Ingestion service — fetches daily OHLCV data from Yahoo Finance
and loads it into GCS (raw) + BigQuery (raw dataset).

Triggered by Cloud Scheduler via HTTP POST.
"""

import json
import logging
import os
from datetime import datetime, timezone

import yfinance as yf
from flask import Flask, jsonify
from google.cloud import bigquery, storage

# ── Config ────────────────────────────────────────────────────────────────────

PROJECT_ID  = os.environ["GCP_PROJECT_ID"]
GCS_BUCKET  = os.environ["GCS_BUCKET_NAME"]          # e.g. "open-finance-raw"
BQ_DATASET  = os.environ.get("BQ_DATASET", "raw")
BQ_TABLE    = os.environ.get("BQ_TABLE",   "prices")
GCS_PREFIX  = os.environ.get("GCS_PREFIX", "prices")

TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META",
    "NVDA", "TSLA", "JPM",  "V",    "JNJ",
]

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)

# ── Clients ───────────────────────────────────────────────────────────────────

gcs_client = storage.Client(project=PROJECT_ID)
bq_client  = bigquery.Client(project=PROJECT_ID)

# ── Core logic ────────────────────────────────────────────────────────────────

def fetch_prices(tickers: list[str]) -> list[dict]:
    """Download the latest trading day OHLCV for each ticker."""
    records = []
    ingested_at = datetime.now(timezone.utc).isoformat()

    for ticker in tickers:
        try:
            data = yf.Ticker(ticker).history(period="2d")  # 2d avoids weekend gaps
            if data.empty:
                log.warning("No data returned for %s — skipping", ticker)
                continue

            latest = data.iloc[-1]
            records.append({
                "ticker":       ticker,
                "date":         latest.name.date().isoformat(),
                "open":         round(float(latest["Open"]),   4),
                "high":         round(float(latest["High"]),   4),
                "low":          round(float(latest["Low"]),    4),
                "close":        round(float(latest["Close"]),  4),
                "volume":       int(latest["Volume"]),
                "ingested_at":  ingested_at,
            })
            log.info("Fetched %s — close: %.2f", ticker, latest["Close"])

        except Exception as exc:
            log.error("Failed to fetch %s: %s", ticker, exc)

    return records


def upload_to_gcs(records: list[dict], run_date: str) -> str:
    """Upload raw JSON to GCS partitioned by date. Returns the GCS URI."""
    bucket   = gcs_client.bucket(GCS_BUCKET)
    blob_path = f"{GCS_PREFIX}/date={run_date}/prices_{run_date}.json"
    blob     = bucket.blob(blob_path)

    ndjson = "\n".join(json.dumps(r) for r in records)
    blob.upload_from_string(ndjson, content_type="application/json")

    uri = f"gs://{GCS_BUCKET}/{blob_path}"
    log.info("Uploaded %d records to %s", len(records), uri)
    return uri


def load_to_bigquery(records: list[dict]) -> int:
    """Upsert today's records into BigQuery raw.prices."""
    table_id = f"{PROJECT_ID}.{BQ_DATASET}.{BQ_TABLE}"

    schema = [
        bigquery.SchemaField("ticker",      "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("date",        "DATE",      mode="REQUIRED"),
        bigquery.SchemaField("open",        "FLOAT64",   mode="NULLABLE"),
        bigquery.SchemaField("high",        "FLOAT64",   mode="NULLABLE"),
        bigquery.SchemaField("low",         "FLOAT64",   mode="NULLABLE"),
        bigquery.SchemaField("close",       "FLOAT64",   mode="NULLABLE"),
        bigquery.SchemaField("volume",      "INTEGER",   mode="NULLABLE"),
        bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="NULLABLE"),
    ]

    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        # Deduplicate on load via clustering — Dataform handles dedup downstream
        time_partitioning=bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="date",
        ),
    )

    job = bq_client.load_table_from_json(records, table_id, job_config=job_config)
    job.result()  # wait for completion

    rows_loaded = job.output_rows
    log.info("Loaded %d rows into %s", rows_loaded, table_id)
    return rows_loaded


# ── HTTP endpoint ─────────────────────────────────────────────────────────────

@app.route("/ingest", methods=["POST", "GET"])
def ingest():
    """Entry point called by Cloud Scheduler."""
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log.info("Starting ingestion run for date=%s", run_date)

    records = fetch_prices(TICKERS)

    if not records:
        return jsonify({"status": "warning", "message": "No records fetched"}), 200

    gcs_uri    = upload_to_gcs(records, run_date)
    rows_loaded = load_to_bigquery(records)

    return jsonify({
        "status":      "ok",
        "run_date":    run_date,
        "tickers":     len(records),
        "gcs_uri":     gcs_uri,
        "rows_loaded": rows_loaded,
    }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=False)
