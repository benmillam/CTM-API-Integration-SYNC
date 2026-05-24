#!/bin/bash
set -euo pipefail

PROJECT_ID="data-etl-to-bigquery"
REGION="us-central1"
JOB_NAME="ctm-accounts-sync-job"
IMAGE_NAME="gcr.io/$PROJECT_ID/$JOB_NAME"
SCHEDULER_JOB_NAME="ctm-accounts-sync-daily-schedule"
RUN_URI="https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/$JOB_NAME:run"
SCHEDULER_SERVICE_ACCOUNT="$PROJECT_ID@appspot.gserviceaccount.com"

echo "Deploying CTM accounts sync job..."

gcloud config set project "$PROJECT_ID"

gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  containerregistry.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com

gcloud builds submit --tag "$IMAGE_NAME" .

if gcloud run jobs describe "$JOB_NAME" --region="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud run jobs update "$JOB_NAME" \
    --image="$IMAGE_NAME" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --memory=2Gi \
    --cpu=1 \
    --max-retries=3 \
    --task-timeout=3600 \
    --parallelism=1 \
    --set-env-vars="PROJECT_ID=$PROJECT_ID" \
    --set-secrets="CTM_ACCESS_KEY=CTM_ACCESS_KEY:latest,CTM_SECRET_KEY=CTM_SECRET_KEY:latest"
else
  gcloud run jobs create "$JOB_NAME" \
    --image="$IMAGE_NAME" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --memory=2Gi \
    --cpu=1 \
    --max-retries=3 \
    --task-timeout=3600 \
    --parallelism=1 \
    --set-env-vars="PROJECT_ID=$PROJECT_ID" \
    --set-secrets="CTM_ACCESS_KEY=CTM_ACCESS_KEY:latest,CTM_SECRET_KEY=CTM_SECRET_KEY:latest"
fi

if gcloud scheduler jobs describe "$SCHEDULER_JOB_NAME" --location="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "$SCHEDULER_JOB_NAME" \
    --location="$REGION" \
    --project="$PROJECT_ID" \
    --schedule="0 0 * * *" \
    --time-zone="UTC" \
    --uri="$RUN_URI" \
    --http-method=POST \
    --oauth-service-account-email="$SCHEDULER_SERVICE_ACCOUNT" \
    --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform"
else
  gcloud scheduler jobs create http "$SCHEDULER_JOB_NAME" \
    --location="$REGION" \
    --project="$PROJECT_ID" \
    --schedule="0 0 * * *" \
    --time-zone="UTC" \
    --uri="$RUN_URI" \
    --http-method=POST \
    --oauth-service-account-email="$SCHEDULER_SERVICE_ACCOUNT" \
    --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
    --description="Daily CTM accounts sync at 12:00 AM UTC"
fi

echo "Deployment complete for $JOB_NAME."
