#!/usr/bin/env bash
# deploy.sh — deploys Cloud Run service and creates the Cloud Scheduler job
# Usage: ./orchestration/deploy.sh YOUR_PROJECT_ID

set -euo pipefail

PROJECT_ID="${1:?Usage: ./deploy.sh YOUR_PROJECT_ID}"
REGION="europe-west1"
SERVICE_NAME="finance-ingestion"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# Pull the service account email from Terraform output
SA_EMAIL=$(terraform -chdir=infra/terraform output -raw ingestion_sa_email)
BUCKET_NAME=$(terraform -chdir=infra/terraform output -raw gcs_bucket_name)

echo "▶ Building and pushing container image..."
gcloud builds submit ingestion/cloud_run \
  --tag "${IMAGE}" \
  --project "${PROJECT_ID}"

echo "▶ Deploying Cloud Run service..."
gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --no-allow-unauthenticated \
  --service-account "${SA_EMAIL}" \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID},GCS_BUCKET_NAME=${BUCKET_NAME}" \
  --memory 512Mi \
  --cpu 1 \
  --timeout 120 \
  --max-instances 1 \
  --project "${PROJECT_ID}"

SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region "${REGION}" \
  --format "value(status.url)" \
  --project "${PROJECT_ID}")

echo "▶ Cloud Run deployed at: ${SERVICE_URL}"

echo "▶ Creating Cloud Scheduler job..."
gcloud scheduler jobs create http finance-daily-ingestion \
  --schedule="0 7 * * 1-5" \
  --uri="${SERVICE_URL}/ingest" \
  --oidc-service-account-email="${SA_EMAIL}" \
  --location="${REGION}" \
  --time-zone="UTC" \
  --attempt-deadline=180s \
  --project "${PROJECT_ID}" 2>/dev/null || \
gcloud scheduler jobs update http finance-daily-ingestion \
  --schedule="0 7 * * 1-5" \
  --uri="${SERVICE_URL}/ingest" \
  --oidc-service-account-email="${SA_EMAIL}" \
  --location="${REGION}" \
  --project "${PROJECT_ID}"

echo "✅ Done. Pipeline runs Mon–Fri at 07:00 UTC."
echo "   Manual trigger: gcloud scheduler jobs run finance-daily-ingestion --location=${REGION}"
