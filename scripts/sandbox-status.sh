#!/usr/bin/env bash
# =============================================================================
# Murmur GCP Sandbox Status
# =============================================================================
# Shows the current state of all sandbox resources in one shot.
# Run this anytime to answer "what's up with my sandbox?"
#
# Usage:
#   bash scripts/sandbox-status.sh
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

echo "=== Murmur Sandbox Status ==="
echo "Project: $PROJECT_ID"
echo "Checked: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

# ---- Cloud Run ---------------------------------------------------------------
echo "--- Cloud Run: $SERVICE"
if gcloud run services describe "$SERVICE" --region="$REGION" --project="$PROJECT_ID" &>/dev/null; then
    URL=$(gcloud run services describe "$SERVICE" --region="$REGION" --project="$PROJECT_ID" --format='value(status.url)')
    echo "    Status: DEPLOYED"
    echo "    URL:    $URL"
    # Quick health check
    if HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$URL" 2>/dev/null); then
        echo "    Health: HTTP $HTTP_CODE"
    else
        echo "    Health: UNREACHABLE"
    fi
else
    echo "    Status: NOT FOUND"
fi
echo ""

# ---- Cloud Scheduler ---------------------------------------------------------
echo "--- Cloud Scheduler: trigger-normal-worker"
if gcloud scheduler jobs describe trigger-normal-worker --location="$REGION" --project="$PROJECT_ID" &>/dev/null; then
    STATE=$(gcloud scheduler jobs describe trigger-normal-worker --location="$REGION" --project="$PROJECT_ID" --format='value(state)')
    LAST=$(gcloud scheduler jobs describe trigger-normal-worker --location="$REGION" --project="$PROJECT_ID" --format='value(lastAttemptTime)')
    STATUS=$(gcloud scheduler jobs describe trigger-normal-worker --location="$REGION" --project="$PROJECT_ID" --format='value(status.code)')
    NEXT=$(gcloud scheduler jobs describe trigger-normal-worker --location="$REGION" --project="$PROJECT_ID" --format='value(scheduleTime)')
    echo "    State:      $STATE"
    echo "    Last fired: ${LAST:-never}"
    echo "    Last code:  ${STATUS:-ok (empty=success)}"
    echo "    Next fire:  $NEXT"
else
    echo "    Status: NOT FOUND"
fi
echo ""

# ---- Secrets -----------------------------------------------------------------
echo "--- Secrets"
for SECRET_NAME in secret_low secret_medium secret_high; do
    if gcloud secrets describe "$SECRET_NAME" --project="$PROJECT_ID" &>/dev/null; then
        VERSIONS=$(gcloud secrets versions list "$SECRET_NAME" --project="$PROJECT_ID" --format='value(name)' 2>/dev/null | wc -l | tr -d ' ')
        echo "    $SECRET_NAME: EXISTS ($VERSIONS versions)"
    else
        echo "    $SECRET_NAME: NOT FOUND"
    fi
done
echo ""

# ---- GCS Bucket + Audit Logs -------------------------------------------------
echo "--- GCS Bucket: gs://$BUCKET"
if gcloud storage buckets describe "gs://$BUCKET" --project="$PROJECT_ID" &>/dev/null; then
    echo "    Status: EXISTS"
    # Count objects (audit log files)
    OBJ_COUNT=$(gcloud storage ls -r "gs://$BUCKET/" 2>/dev/null | grep -c "\.json$" || echo "0")
    echo "    Audit log files: $OBJ_COUNT"
    # Show latest file if any exist
    LATEST=$(gcloud storage ls -r "gs://$BUCKET/" 2>/dev/null | tail -1)
    if [ -n "$LATEST" ]; then
        echo "    Latest: $LATEST"
    fi
else
    echo "    Status: NOT FOUND"
fi
echo ""

# ---- Logging Sink ------------------------------------------------------------
echo "--- Logging Sink: murmur-audit-sink"
if gcloud logging sinks describe murmur-audit-sink --project="$PROJECT_ID" &>/dev/null; then
    DEST=$(gcloud logging sinks describe murmur-audit-sink --project="$PROJECT_ID" --format='value(destination)')
    echo "    Status:      ACTIVE"
    echo "    Destination: $DEST"
else
    echo "    Status: NOT FOUND"
fi
echo ""

# ---- VM ----------------------------------------------------------------------
echo "--- VM: $VM"
if gcloud compute instances describe "$VM" --zone="$ZONE" --project="$PROJECT_ID" &>/dev/null; then
    VM_STATUS=$(gcloud compute instances describe "$VM" --zone="$ZONE" --project="$PROJECT_ID" --format='value(status)')
    VM_IP=$(gcloud compute instances describe "$VM" --zone="$ZONE" --project="$PROJECT_ID" --format='value(networkInterfaces[0].accessConfigs[0].natIP)')
    echo "    Status:      $VM_STATUS"
    echo "    External IP: ${VM_IP:-none}"
else
    echo "    Status: NOT FOUND"
fi
echo ""

# ---- Data Access Audit Logs --------------------------------------------------
echo "--- Data Access Audit Logs"
HAS_AUDIT=$(gcloud projects get-iam-policy "$PROJECT_ID" --format=json 2>/dev/null | \
    python3 -c "
import sys, json
p = json.load(sys.stdin)
for c in p.get('auditConfigs', []):
    if c.get('service') == 'allServices':
        types = {e.get('logType') for e in c.get('auditLogConfigs', [])}
        if 'DATA_READ' in types and 'DATA_WRITE' in types:
            print('ENABLED'); sys.exit(0)
print('DISABLED')
" 2>/dev/null || echo "UNKNOWN")
echo "    Status: $HAS_AUDIT"
echo ""

echo "=== Done ==="
