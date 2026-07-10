# Open Finance Data Platform 🏦

> End-to-end ELT pipeline on GCP — from public financial APIs to actionable dashboards.

![GCP](https://img.shields.io/badge/GCP-Cloud%20Run%20%7C%20BigQuery%20%7C%20GCS-4285F4?logo=google-cloud&logoColor=white)
![Dataform](https://img.shields.io/badge/Dataform-staging%20→%20mart-7B61FF?logo=google&logoColor=white)
![Terraform](https://img.shields.io/badge/Terraform-IaC-7B42BC?logo=terraform&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![Status](https://img.shields.io/badge/status-active-brightgreen)

---

## Overview

This project implements a production-style data pipeline that ingests daily stock market data from the Yahoo Finance public API, stores it in Google Cloud Storage, loads it into BigQuery, and applies multi-layer transformations using Dataform — exposing a clean analytical mart consumed by a Looker Studio dashboard.

**Why this stack?** It mirrors real-world patterns used in modern data teams: event-driven ingestion, decoupled storage from compute, SQL-first transformations with version control, and infrastructure-as-code.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Google Cloud Platform                     │
│                                                             │
│  ┌──────────────┐     ┌────────────┐     ┌──────────────┐  │
│  │  Cloud Run   │────▶│  GCS raw/  │────▶│  BigQuery    │  │
│  │  (Python)    │     │  (JSON)    │     │  raw dataset │  │
│  └──────────────┘     └────────────┘     └──────┬───────┘  │
│         ▲                                        │          │
│  ┌──────┴───────┐                       ┌────────▼───────┐  │
│  │Cloud Scheduler│                       │   Dataform     │  │
│  │  (cron daily) │                       │ staging → mart │  │
│  └──────────────┘                       └────────┬───────┘  │
│                                                   │          │
└───────────────────────────────────────────────────┼─────────┘
                                                    │
                                           ┌────────▼───────┐
                                           │ Looker Studio  │
                                           │  (dashboard)   │
                                           └────────────────┘

Infrastructure provisioned with Terraform.
```

### Data layers

| Layer | Location | Description |
|---|---|---|
| **Raw** | `GCS: raw/YYYY/MM/DD/` | Original JSON responses from the API, immutable |
| **Staging** | `BQ: staging.stg_*` | Typed, renamed, light cleaning — 1:1 with raw |
| **Mart** | `BQ: mart.fct_* / dim_*` | Business-ready tables for analysis |

---

## Tech Stack

| Component | Tool | Purpose |
|---|---|---|
| Ingestion | Python + `yfinance` | Pull daily OHLCV data for a list of tickers |
| Compute | Cloud Run (containerised) | Serverless execution, no always-on infra |
| Raw storage | Google Cloud Storage | Landing zone, partitioned by date |
| Data warehouse | BigQuery | Centralised analytical store |
| Transformation | Dataform (SQLX) | Staging + mart models, ref() lineage |
| Orchestration | Cloud Scheduler | Triggers Cloud Run daily at 07:00 UTC |
| Visualisation | Looker Studio | Free, native BigQuery connector |
| IaC | Terraform | GCS bucket + BQ datasets + IAM |

---

## Repository Structure

```
open-finance-pipeline/
├── README.md
├── infra/
│   └── terraform/
│       ├── main.tf          # GCS bucket + BQ datasets
│       ├── variables.tf
│       └── outputs.tf
├── ingestion/
│   └── cloud_run/
│       ├── main.py          # Fetches tickers → uploads to GCS → loads to BQ
│       ├── requirements.txt
│       └── Dockerfile
├── transformation/
│   └── dataform/
│       ├── dataform.json
│       ├── staging/
│       │   └── stg_prices.sqlx
│       └── mart/
│           ├── fct_daily_prices.sqlx
│           └── dim_tickers.sqlx
├── orchestration/
│   └── scheduler.yaml       # Cloud Scheduler job definition
└── docs/
    └── architecture.png
```

---

## Getting Started

### Prerequisites

- GCP project with billing enabled (free tier covers this project)
- `gcloud` CLI authenticated
- Terraform >= 1.5
- Python 3.11+
- Docker (for local testing of Cloud Run)

### 1 — Provision infrastructure

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # fill in project_id, region
terraform init
terraform apply
```

This creates:
- GCS bucket `{project_id}-finance-raw`
- BigQuery datasets: `raw`, `staging`, `mart`
- Service account with least-privilege IAM bindings

### 2 — Deploy the ingestion service

```bash
cd ingestion/cloud_run
gcloud builds submit --tag gcr.io/{PROJECT_ID}/finance-ingestion
gcloud run deploy finance-ingestion \
  --image gcr.io/{PROJECT_ID}/finance-ingestion \
  --region europe-west1 \
  --no-allow-unauthenticated
```

### 3 — Configure Dataform

```bash
cd transformation/dataform
# Link to your GCP project in the Dataform UI or via API
# Run the pipeline:
dataform run --project {PROJECT_ID} --location EU
```

### 4 — Schedule daily runs

```bash
gcloud scheduler jobs create http finance-daily-ingestion \
  --schedule="0 7 * * *" \
  --uri="https://{CLOUD_RUN_URL}/ingest" \
  --oidc-service-account-email={SA_EMAIL} \
  --location=europe-west1
```

### 5 — Connect Looker Studio

1. Open [Looker Studio](https://lookerstudio.google.com)
2. Add data source → BigQuery → `mart.fct_daily_prices`
3. Build your dashboard

---

## Key Design Decisions

**Why Cloud Run over Cloud Functions?** Cloud Run handles longer-running ingestion jobs cleanly, supports Docker-based dependencies, and is easier to test locally.

**Why Dataform over dbt?** Native GCP integration, no additional infra needed, and direct BigQuery execution — reducing latency and cost for this scale.

**Why GCS as a landing zone?** Decoupling raw storage from the warehouse gives full replayability. If a Dataform model has a bug, you can re-load from GCS without re-calling the API.

**Why Terraform?** Makes the project reproducible in any GCP account in under 5 minutes — critical for portfolio projects that reviewers may want to deploy themselves.

---

## Dashboard Preview

> *Screenshot to be added after first full pipeline run.*

Metrics visible on the dashboard:
- Daily closing price and 30-day moving average per ticker
- Daily volume vs 90-day average
- Correlation heatmap across tickers
- Data freshness indicator (last successful ingestion timestamp)

---

## Roadmap

- [ ] Add data quality checks (Great Expectations or BigQuery assertions in Dataform)
- [ ] Extend to multiple asset classes (ETFs, FX)
- [ ] Replace Cloud Scheduler with Cloud Workflows for retry logic
- [ ] Add CI/CD with GitHub Actions (lint SQLX, run Terraform plan on PR)
- [ ] Alerting with Cloud Monitoring on pipeline failures

---

## Author

**Edgar Cartolari Esteves**
Senior Data Engineer · GCP · Microsoft Fabric · BigQuery · Dataform

[LinkedIn](https://linkedin.com/in/edgaresteves) · [GitHub](https://github.com/ecartolariesteves)

---

*Built as a portfolio showcase. All data sourced from Yahoo Finance public API.*
