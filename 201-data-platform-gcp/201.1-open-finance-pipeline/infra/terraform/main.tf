terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ── GCS bucket — raw landing zone ─────────────────────────────────────────────

resource "google_storage_bucket" "raw" {
  name          = "${var.project_id}-finance-raw"
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true

  lifecycle_rule {
    condition { age = 90 }               # keep raw files 90 days, then delete
    action    { type = "Delete" }
  }

  labels = {
    project = "open-finance-pipeline"
    layer   = "raw"
  }
}

# ── BigQuery datasets ──────────────────────────────────────────────────────────

resource "google_bigquery_dataset" "raw" {
  dataset_id  = "raw"
  description = "Raw tables — direct load from GCS, no transformations"
  location    = var.bq_location

  labels = {
    project = "open-finance-pipeline"
    layer   = "raw"
  }
}

resource "google_bigquery_dataset" "staging" {
  dataset_id  = "staging"
  description = "Staging tables — typed and cleaned, managed by Dataform"
  location    = var.bq_location

  labels = {
    project = "open-finance-pipeline"
    layer   = "staging"
  }
}

resource "google_bigquery_dataset" "mart" {
  dataset_id  = "mart"
  description = "Analytical mart — business-ready facts and dims"
  location    = var.bq_location

  labels = {
    project = "open-finance-pipeline"
    layer   = "mart"
  }
}

# ── Service account for Cloud Run ─────────────────────────────────────────────

resource "google_service_account" "ingestion" {
  account_id   = "finance-ingestion-sa"
  display_name = "Open Finance — Ingestion Service Account"
}

# Least-privilege IAM bindings
resource "google_storage_bucket_iam_member" "ingestion_gcs" {
  bucket = google_storage_bucket.raw.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.ingestion.email}"
}

resource "google_bigquery_dataset_iam_member" "ingestion_bq_raw" {
  dataset_id = google_bigquery_dataset.raw.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.ingestion.email}"
}

resource "google_project_iam_member" "ingestion_bq_job" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.ingestion.email}"
}
