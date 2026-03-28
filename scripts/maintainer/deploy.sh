#!/usr/bin/env bash
# Deploy the Murmur maintainer service to GCP Cloud Run.
#
# Produces hourly audit events in IDENTITY, CONTROL, and SECRET zones:
#   - SECRET: AddSecretVersion on secret_maintenance
#   - IDENTITY: GenerateAccessToken (self-impersonation)
#   - CONTROL: SetIamPolicy x2 (add + remove binding on itself)
#
# Prerequisites:
#   - gcloud CLI authenticated with project owner/editor
#   - Cloud Run, IAM, Secret Manager, Cloud Scheduler APIs enabled
#   - scheduler-sa already exists (created during normal-worker deploy)
#
# Usage: ./deploy.sh

set -euo pipefail

# --- Configuration (edit these if replicating in a different project) ---
PROJECT="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID in .env or environment}"
REGION="us-central1"
SA_NAME="maintenance-sa"
SA_EMAIL="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
SCHEDULER_SA="scheduler-sa@${PROJECT}.iam.gserviceaccount.com"
SECRET_NAME="secret_maintenance"
SERVICE_NAME="maintainer"
SCHEDULE="0 * * * *"  # Every hour

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Deploying Murmur Maintainer ==="
echo "Project: $PROJECT"
echo "Region:  $REGION"
echo "SA:      $SA_EMAIL"
echo ""

# --- Step 1: Create service account ---
echo "--- Step 1: Create service account ---"
if gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT" &>/dev/null; then
    echo "Service account $SA_NAME already exists, skipping."
else
    gcloud iam service-accounts create "$SA_NAME" \
        --display-name="Murmur Maintenance SA" \
        --project="$PROJECT"
    echo "Created $SA_NAME."
fi

# --- Step 2: Grant permissions ---
echo "--- Step 2: Grant permissions ---"

# Secret version adder (project-level, for AddSecretVersion)
gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/secretmanager.secretVersionAdder" \
    --quiet > /dev/null 2>&1
echo "  Granted secretmanager.secretVersionAdder"

# SA key admin on itself (for key create/delete if org policy allows)
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/iam.serviceAccountKeyAdmin" \
    --project="$PROJECT" \
    --quiet > /dev/null 2>&1
echo "  Granted iam.serviceAccountKeyAdmin (on self)"

# SA admin on itself (for SetIamPolicy toggle)
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/iam.serviceAccountAdmin" \
    --project="$PROJECT" \
    --quiet > /dev/null 2>&1
echo "  Granted iam.serviceAccountAdmin (on self)"

# Token creator on itself (for GenerateAccessToken)
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/iam.serviceAccountTokenCreator" \
    --project="$PROJECT" \
    --quiet > /dev/null 2>&1
echo "  Granted iam.serviceAccountTokenCreator (on self)"

# --- Step 3: Create secret ---
echo "--- Step 3: Create secret ---"
if gcloud secrets describe "$SECRET_NAME" --project="$PROJECT" &>/dev/null; then
    echo "Secret $SECRET_NAME already exists, skipping."
else
    gcloud secrets create "$SECRET_NAME" \
        --replication-policy="automatic" \
        --project="$PROJECT"
    echo -n "{\"initial\": true}" | \
        gcloud secrets versions add "$SECRET_NAME" \
            --data-file=- \
            --project="$PROJECT"
    echo "Created $SECRET_NAME with initial version."
fi

# --- Step 4: Deploy Cloud Run service ---
echo "--- Step 4: Deploy Cloud Run service ---"
gcloud run deploy "$SERVICE_NAME" \
    --source="$SCRIPT_DIR" \
    --region="$REGION" \
    --project="$PROJECT" \
    --service-account="$SA_EMAIL" \
    --set-env-vars="GCP_PROJECT_ID=$PROJECT,MAINTENANCE_SECRET=$SECRET_NAME,MAINTENANCE_SA_EMAIL=$SA_EMAIL" \
    --no-allow-unauthenticated \
    --min-instances=0 \
    --max-instances=1 \
    --memory=256Mi \
    --timeout=60 \
    --quiet

SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
    --region="$REGION" --project="$PROJECT" --format='value(status.url)')
echo "Deployed at: $SERVICE_URL"

# --- Step 5: Grant scheduler-sa invoker permission ---
echo "--- Step 5: Grant invoker permission ---"
gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
    --region="$REGION" \
    --member="serviceAccount:$SCHEDULER_SA" \
    --role="roles/run.invoker" \
    --project="$PROJECT" \
    --quiet > /dev/null 2>&1
echo "  Granted run.invoker to $SCHEDULER_SA"

# --- Step 6: Create scheduler job ---
echo "--- Step 6: Create scheduler job ---"
JOB_NAME="trigger-${SERVICE_NAME}"
if gcloud scheduler jobs describe "$JOB_NAME" --location="$REGION" --project="$PROJECT" &>/dev/null; then
    echo "Scheduler job $JOB_NAME already exists. Updating..."
    gcloud scheduler jobs update http "$JOB_NAME" \
        --location="$REGION" \
        --schedule="$SCHEDULE" \
        --uri="${SERVICE_URL}/maintain" \
        --http-method=GET \
        --oidc-service-account-email="$SCHEDULER_SA" \
        --oidc-token-audience="$SERVICE_URL" \
        --project="$PROJECT" \
        --quiet
else
    gcloud scheduler jobs create http "$JOB_NAME" \
        --location="$REGION" \
        --schedule="$SCHEDULE" \
        --uri="${SERVICE_URL}/maintain" \
        --http-method=GET \
        --oidc-service-account-email="$SCHEDULER_SA" \
        --oidc-token-audience="$SERVICE_URL" \
        --project="$PROJECT" \
        --quiet
fi
echo "Scheduler job: $JOB_NAME ($SCHEDULE)"

# --- Step 7: Test invocation ---
echo ""
echo "--- Step 7: Test invocation ---"
echo "Running manual test..."
RESULT=$(curl -s -H "Authorization: Bearer $(gcloud auth print-identity-token)" "${SERVICE_URL}/maintain")
echo "$RESULT" | python3 -m json.tool

echo ""
echo "=== Deployment complete ==="
echo "Service: $SERVICE_URL"
echo "Scheduler: $JOB_NAME ($SCHEDULE)"
echo "SA: $SA_EMAIL"
echo "Secret: $SECRET_NAME"
echo ""
echo "Expected audit events per invocation:"
echo "  - SECRET zone: AddSecretVersion"
echo "  - IDENTITY zone: GenerateAccessToken (self-impersonation)"
echo "  - CONTROL zone: SetIamPolicy x2 (add + remove binding)"
