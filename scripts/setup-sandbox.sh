#!/usr/bin/env bash
# =============================================================================
# Murmur GCP Sandbox Setup
# =============================================================================
# Recreates the entire GCP sandbox from scratch. Idempotent — safe to re-run.
#
# Prerequisites:
#   - gcloud CLI installed and authenticated (gcloud auth login)
#   - A GCP project with billing enabled
#   - A .env file in the project root (copy from .env.example)
#
# Usage:
#   bash scripts/setup-sandbox.sh
#
# What this script does (in order):
#   1. Enables required GCP APIs (unlocks services for the project)
#   2. Creates a GCS bucket (storage for exported audit logs)
#   3. Creates a logging sink (pipes audit logs to the bucket)
#   4. Enables Data Access audit logs (so read/write ops are logged)
#   5. Creates test secrets (targets for adversarial scenarios)
#   6. Deploys a Cloud Run service (the "normal worker" container)
#   7. Creates a Cloud Scheduler job (triggers the worker every 5 min)
#   8. Provisions an e2-micro VM (future home of the ingestion pipeline)
#
# After running, set up a $25 billing budget alert manually in the GCP Console:
#   https://console.cloud.google.com/billing
# =============================================================================

set -euo pipefail

# ---- Load .env if it exists --------------------------------------------------
# "set -a" means every variable assigned after this line is automatically exported
# (visible to child processes). "set +a" turns that off again.
# We look for .env in the project root (one directory up from scripts/).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# ---- Configuration from environment (.env) -----------------------------------
# These variables MUST be set. The script fails immediately if they're missing.
# The :? syntax means "if this variable is empty or unset, print the error and exit."

PROJECT_ID="${GCP_PROJECT_ID:?ERROR: Set GCP_PROJECT_ID in .env}"
REGION="${GCP_REGION:-us-central1}"
ZONE="${GCP_ZONE:-us-central1-a}"
BUCKET="${GCS_AUDIT_BUCKET:?ERROR: Set GCS_AUDIT_BUCKET in .env}"
SERVICE="${CLOUD_RUN_SERVICE:-normal-worker}"
VM="${VM_NAME:-murmur-vm}"

echo "=== Murmur Sandbox Setup ==="
echo "Project:  $PROJECT_ID"
echo "Region:   $REGION"
echo "Zone:     $ZONE"
echo "Bucket:   $BUCKET"
echo ""

# ---- Helper function ---------------------------------------------------------
# "info" prints a step header so you can see progress.
info() { echo "--- [$1] $2"; }

# ---- Step 1: Enable APIs ----------------------------------------------------
# GCP locks all services by default. We need to "enable" (unlock) each API
# before we can use it. Think of it as unlocking doors in a building.
#
# This is idempotent — enabling an already-enabled API is a no-op.

info "1/8" "Enabling GCP APIs..."

gcloud services enable \
    logging.googleapis.com \
    storage.googleapis.com \
    iam.googleapis.com \
    secretmanager.googleapis.com \
    run.googleapis.com \
    cloudscheduler.googleapis.com \
    cloudresourcemanager.googleapis.com \
    compute.googleapis.com \
    artifactregistry.googleapis.com \
    --project="$PROJECT_ID" \
    --quiet

echo "    APIs enabled."

# ---- Step 2: Create GCS bucket ----------------------------------------------
# Google Cloud Storage (GCS) is like a giant file system in the cloud.
# A "bucket" is a top-level container (like a folder) with a globally unique name.
# We store exported audit logs here so our ingestion pipeline can read them.
#
# --uniform-bucket-level-access: use IAM for access control (simpler, more secure).

info "2/8" "Creating GCS bucket gs://$BUCKET ..."

if gcloud storage buckets describe "gs://$BUCKET" --project="$PROJECT_ID" &>/dev/null; then
    echo "    Bucket already exists, skipping."
else
    gcloud storage buckets create "gs://$BUCKET" \
        --location="$REGION" \
        --uniform-bucket-level-access \
        --project="$PROJECT_ID"
    echo "    Bucket created."
fi

# ---- Step 3: Create logging sink --------------------------------------------
# Cloud Logging is a river — all audit events flow through it.
# A "sink" is a pipe that diverts matching events to a destination.
# Our sink copies all Cloud Audit Log events to the GCS bucket.
#
# After creating the sink, we grant its auto-generated service account
# permission to write files into the bucket.

info "3/8" "Creating audit log sink -> GCS ..."

if gcloud logging sinks describe murmur-audit-sink --project="$PROJECT_ID" &>/dev/null; then
    echo "    Sink already exists, skipping."
else
    # Create the sink. gcloud prints the service account that needs bucket access.
    SINK_OUTPUT=$(gcloud logging sinks create murmur-audit-sink \
        "storage.googleapis.com/$BUCKET" \
        --log-filter='logName:"cloudaudit.googleapis.com"' \
        --project="$PROJECT_ID" 2>&1)
    echo "    Sink created."

    # Extract the sink's service account and grant it write access.
    # The sink can see events but can't write to the bucket without this.
    SINK_SA=$(gcloud logging sinks describe murmur-audit-sink \
        --project="$PROJECT_ID" \
        --format='value(writerIdentity)')
    gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
        --member="$SINK_SA" \
        --role="roles/storage.objectCreator" \
        --quiet
    echo "    Granted sink write access to bucket."
fi

# ---- Step 4: Enable Data Access audit logs -----------------------------------
# GCP has two kinds of audit logs:
#   - Admin Activity: "someone changed something" (always on)
#   - Data Access: "someone read something" (OFF by default)
#
# For Murmur, Data Access logs are critical — an attacker reading a secret
# is a Data Access event. Without these, we're blind to read operations.
#
# We modify the project's IAM policy to add an "auditConfigs" section
# that enables DATA_READ and DATA_WRITE logging for all services.

info "4/8" "Enabling Data Access audit logs ..."

# Fetch current policy, check if auditConfigs already set
CURRENT_POLICY=$(gcloud projects get-iam-policy "$PROJECT_ID" --format=json 2>/dev/null)

if echo "$CURRENT_POLICY" | python3 -c "import sys,json; p=json.load(sys.stdin); sys.exit(0 if 'auditConfigs' in p else 1)" 2>/dev/null; then
    echo "    Data Access audit logs already enabled, skipping."
else
    # Add auditConfigs to the existing policy
    UPDATED_POLICY=$(echo "$CURRENT_POLICY" | python3 -c "
import sys, json
policy = json.load(sys.stdin)
policy['auditConfigs'] = [{
    'service': 'allServices',
    'auditLogConfigs': [
        {'logType': 'DATA_READ'},
        {'logType': 'DATA_WRITE'}
    ]
}]
json.dump(policy, sys.stdout, indent=2)
")
    TMP_POLICY_FILE="$(mktemp "${TMPDIR:-/tmp}/murmur-iam-policy.XXXXXX.json")"
    trap 'rm -f "$TMP_POLICY_FILE"' EXIT
    echo "$UPDATED_POLICY" > "$TMP_POLICY_FILE"
    gcloud projects set-iam-policy "$PROJECT_ID" "$TMP_POLICY_FILE" --quiet
    rm -f "$TMP_POLICY_FILE"
    echo "    Data Access audit logs enabled."
fi

# ---- Step 5: Create test secrets ---------------------------------------------
# Secret Manager stores sensitive values (passwords, API keys, etc.).
# We create 3 secrets at different "sensitivity levels" for Murmur's
# adversarial scenarios. The values are placeholders — what matters is
# that accessing them generates audit log events we can detect.

info "5/8" "Creating test secrets ..."

for SECRET_NAME in secret_low secret_medium secret_high; do
    if gcloud secrets describe "$SECRET_NAME" --project="$PROJECT_ID" &>/dev/null; then
        echo "    $SECRET_NAME already exists, skipping."
    else
        echo -n "${SECRET_NAME}-value" | gcloud secrets create "$SECRET_NAME" \
            --data-file=- \
            --replication-policy=automatic \
            --project="$PROJECT_ID"
        echo "    $SECRET_NAME created."
    fi
done

# ---- Step 6: Deploy Cloud Run service ----------------------------------------
# Cloud Run is like a vending machine for code — give it a container,
# it runs it only when someone sends a request (scales to zero otherwise).
#
# We deploy Google's pre-built "hello" container as our normal-worker.
# Cloud Scheduler will call it every 5 minutes, creating the "legitimate
# scheduled activity" baseline that Murmur should recognize as normal.

info "6/8" "Deploying Cloud Run service: $SERVICE ..."

gcloud run deploy "$SERVICE" \
    --image=us-docker.pkg.dev/cloudrun/container/hello \
    --region="$REGION" \
    --no-allow-unauthenticated \
    --max-instances=1 \
    --project="$PROJECT_ID" \
    --quiet

SERVICE_URL=$(gcloud run services describe "$SERVICE" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --format='value(status.url)')
echo "    Deployed at: $SERVICE_URL"

# ---- Step 7: Create Cloud Scheduler job --------------------------------------
# Cloud Scheduler is a cron job in the cloud — runs tasks on a schedule.
#
# We create a dedicated service account (scheduler-sa) for it, following
# the "principle of least privilege" — it only has permission to invoke
# our Cloud Run service, nothing else.
#
# The OIDC token means the scheduler authenticates itself when calling
# Cloud Run. This is the trigger_ref experiment: does the scheduler's
# execution context appear in the triggered action's audit logs?

info "7/8" "Creating Cloud Scheduler job ..."

SCHEDULER_SA_EMAIL="scheduler-sa@${PROJECT_ID}.iam.gserviceaccount.com"

# Create the service account (skip if exists)
if gcloud iam service-accounts describe "$SCHEDULER_SA_EMAIL" --project="$PROJECT_ID" &>/dev/null; then
    echo "    scheduler-sa already exists."
else
    gcloud iam service-accounts create scheduler-sa \
        --display-name="Scheduler SA" \
        --project="$PROJECT_ID"
    echo "    scheduler-sa created."
fi

# Grant invoker role
gcloud run services add-iam-policy-binding "$SERVICE" \
    --region="$REGION" \
    --member="serviceAccount:$SCHEDULER_SA_EMAIL" \
    --role="roles/run.invoker" \
    --project="$PROJECT_ID" \
    --quiet

# Create the job (skip if exists)
if gcloud scheduler jobs describe trigger-normal-worker --location="$REGION" --project="$PROJECT_ID" &>/dev/null; then
    echo "    Scheduler job already exists, skipping."
else
    gcloud scheduler jobs create http trigger-normal-worker \
        --location="$REGION" \
        --schedule="*/5 * * * *" \
        --uri="$SERVICE_URL" \
        --http-method=GET \
        --oidc-service-account-email="$SCHEDULER_SA_EMAIL" \
        --project="$PROJECT_ID"
    echo "    Scheduler job created (every 5 min)."
fi

# ---- Step 8: Provision e2-micro VM ------------------------------------------
# A Virtual Machine running in Google's data center. e2-micro is the smallest
# (2 shared vCPUs, 1GB RAM) — free tier eligible.
#
# Eventually the Murmur ingestion pipeline runs continuously on this VM,
# fetching logs from GCS, parsing, and inserting into DuckDB.

info "8/8" "Provisioning VM: $VM ..."

if gcloud compute instances describe "$VM" --zone="$ZONE" --project="$PROJECT_ID" &>/dev/null; then
    echo "    VM already exists, skipping."
else
    gcloud compute instances create "$VM" \
        --zone="$ZONE" \
        --machine-type=e2-micro \
        --image-family=debian-12 \
        --image-project=debian-cloud \
        --boot-disk-size=10GB \
        --project="$PROJECT_ID"
    echo "    VM created."
fi

# ---- Done --------------------------------------------------------------------
echo ""
echo "=== Sandbox setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Set up a \$25 billing budget alert in the GCP Console"
echo "  2. Wait 10-30 min for audit logs to appear in gs://$BUCKET"
echo "  3. Run: bash scripts/sandbox-status.sh  (to check resource status)"
