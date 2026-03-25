#!/usr/bin/env bash
# =============================================================================
# Murmur GCP Sandbox Teardown
# =============================================================================
# Cleanly destroys all sandbox resources. Use this for cost control or to
# start fresh (then re-run setup-sandbox.sh).
#
# Usage:
#   bash scripts/teardown-sandbox.sh
#
# This script asks for confirmation before each destructive step.
# =============================================================================

set -euo pipefail

# Load .env from project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a; source "$PROJECT_ROOT/.env"; set +a
fi

PROJECT_ID="${GCP_PROJECT_ID:?ERROR: Set GCP_PROJECT_ID in .env}"
REGION="${GCP_REGION:-us-central1}"
ZONE="${GCP_ZONE:-us-central1-a}"
BUCKET="${GCS_AUDIT_BUCKET:?ERROR: Set GCS_AUDIT_BUCKET in .env}"
SERVICE="${CLOUD_RUN_SERVICE:-normal-worker}"
VM="${VM_NAME:-murmur-vm}"

echo "=== Murmur Sandbox Teardown ==="
echo "Project: $PROJECT_ID"
echo ""
echo "This will DESTROY the following resources:"
echo "  - Cloud Scheduler job: trigger-normal-worker"
echo "  - Service account: scheduler-sa"
echo "  - Cloud Run service: $SERVICE"
echo "  - Secrets: secret_low, secret_medium, secret_high"
echo "  - Logging sink: murmur-audit-sink"
echo "  - GCS bucket: gs://$BUCKET (and all contents)"
echo "  - VM: $VM"
echo ""
read -p "Are you sure? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

info() { echo "--- $1"; }

# Teardown in reverse order of creation (dependents first)

info "Deleting Cloud Scheduler job ..."
gcloud scheduler jobs delete trigger-normal-worker \
    --location="$REGION" --project="$PROJECT_ID" --quiet 2>/dev/null || echo "    Not found, skipping."

info "Deleting service account: scheduler-sa ..."
gcloud iam service-accounts delete "scheduler-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
    --project="$PROJECT_ID" --quiet 2>/dev/null || echo "    Not found, skipping."

info "Deleting Cloud Run service: $SERVICE ..."
gcloud run services delete "$SERVICE" \
    --region="$REGION" --project="$PROJECT_ID" --quiet 2>/dev/null || echo "    Not found, skipping."

info "Deleting secrets ..."
for SECRET_NAME in secret_low secret_medium secret_high; do
    gcloud secrets delete "$SECRET_NAME" \
        --project="$PROJECT_ID" --quiet 2>/dev/null || echo "    $SECRET_NAME not found, skipping."
done

info "Deleting logging sink ..."
gcloud logging sinks delete murmur-audit-sink \
    --project="$PROJECT_ID" --quiet 2>/dev/null || echo "    Not found, skipping."

info "Deleting GCS bucket and contents ..."
gcloud storage rm -r "gs://$BUCKET" --project="$PROJECT_ID" 2>/dev/null || echo "    Not found, skipping."

info "Deleting VM: $VM ..."
gcloud compute instances delete "$VM" \
    --zone="$ZONE" --project="$PROJECT_ID" --quiet 2>/dev/null || echo "    Not found, skipping."

echo ""
echo "=== Teardown complete ==="
echo "Note: APIs are still enabled. To disable them, use: gcloud services disable <api>"
