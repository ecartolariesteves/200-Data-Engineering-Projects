variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Run and GCS"
  type        = string
  default     = "europe-west1"   # Belgium — closest to Turin, lowest latency
}

variable "bq_location" {
  description = "BigQuery dataset location"
  type        = string
  default     = "EU"
}
