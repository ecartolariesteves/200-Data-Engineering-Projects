output "gcs_bucket_name" {
  description = "Name of the raw GCS bucket"
  value       = google_storage_bucket.raw.name
}

output "bq_raw_dataset" {
  description = "BigQuery raw dataset ID"
  value       = google_bigquery_dataset.raw.dataset_id
}

output "ingestion_sa_email" {
  description = "Service account email to use in Cloud Run deployment"
  value       = google_service_account.ingestion.email
}
