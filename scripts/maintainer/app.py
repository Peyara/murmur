"""Murmur maintainer: hourly maintenance service for zone-diverse audit log generation.

Single endpoint:
  GET /maintain — Rotate secret version, create+delete SA key, toggle IAM binding

Produces audit events in IDENTITY, CONTROL, and SECRET zones each invocation.
"""

import json
import logging
import os
from datetime import UTC, datetime

from flask import Flask, jsonify
from google.cloud import compute_v1, iam_admin_v1, iam_credentials_v1, secretmanager
from google.iam.v1 import iam_policy_pb2

app = Flask(__name__)
logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
MAINTENANCE_SECRET = os.environ.get("MAINTENANCE_SECRET", "secret_maintenance")
# The SA whose keys/policy we cycle — the maintainer operates on itself
MAINTENANCE_SA_EMAIL = os.environ.get(
    "MAINTENANCE_SA_EMAIL",
    f"maintenance-sa@{PROJECT_ID}.iam.gserviceaccount.com",
)
# Benign role to toggle in IAM policy
TOGGLE_ROLE = "roles/iam.serviceAccountUser"
TOGGLE_MEMBER = f"serviceAccount:{MAINTENANCE_SA_EMAIL}"

# VM for metadata update (COMPUTE zone)
VM_NAME = os.environ.get("VM_NAME", "murmur-vm")
VM_ZONE = os.environ.get("GCP_ZONE", "us-central1-a")

_sm_client: secretmanager.SecretManagerServiceClient | None = None
_iam_client: iam_admin_v1.IAMClient | None = None
_cred_client: iam_credentials_v1.IAMCredentialsClient | None = None
_compute_client: compute_v1.InstancesClient | None = None


def _get_secret_client() -> secretmanager.SecretManagerServiceClient:
    global _sm_client  # noqa: PLW0603
    if _sm_client is None:
        _sm_client = secretmanager.SecretManagerServiceClient()
    return _sm_client


def _get_iam_client() -> iam_admin_v1.IAMClient:
    global _iam_client  # noqa: PLW0603
    if _iam_client is None:
        _iam_client = iam_admin_v1.IAMClient()
    return _iam_client


def _get_credentials_client() -> iam_credentials_v1.IAMCredentialsClient:
    global _cred_client  # noqa: PLW0603
    if _cred_client is None:
        _cred_client = iam_credentials_v1.IAMCredentialsClient()
    return _cred_client


def _get_compute_client() -> compute_v1.InstancesClient:
    global _compute_client  # noqa: PLW0603
    if _compute_client is None:
        _compute_client = compute_v1.InstancesClient()
    return _compute_client


def _rotate_secret() -> str:
    """Add a new secret version (SECRET zone: AddSecretVersion)."""
    client = _get_secret_client()
    parent = f"projects/{PROJECT_ID}/secrets/{MAINTENANCE_SECRET}"
    now = datetime.now(UTC)
    payload = json.dumps({"rotated_at": now.isoformat(), "value": "maintenance-cycle"}).encode()
    response = client.add_secret_version(
        request={"parent": parent, "payload": {"data": payload}}
    )
    return response.name


def _generate_token() -> str:
    """Generate a short-lived access token for self (IDENTITY zone: GenerateAccessToken)."""
    client = _get_credentials_client()
    sa_resource = f"projects/-/serviceAccounts/{MAINTENANCE_SA_EMAIL}"
    response = client.generate_access_token(
        request={
            "name": sa_resource,
            "scope": ["https://www.googleapis.com/auth/cloud-platform"],
            "lifetime": {"seconds": 300},
        }
    )
    # Token is ephemeral — we don't use it, just generate for the audit event
    return f"token_expires={response.expire_time.isoformat()}"


def _toggle_iam_binding() -> str:
    """Add then remove an IAM binding on the SA (CONTROL zone: SetIamPolicy x2)."""
    client = _get_iam_client()
    sa_resource = f"projects/{PROJECT_ID}/serviceAccounts/{MAINTENANCE_SA_EMAIL}"

    # Get current policy
    policy = client.get_iam_policy(request=iam_policy_pb2.GetIamPolicyRequest(resource=sa_resource))

    # Add binding
    binding = policy.bindings.add()
    binding.role = TOGGLE_ROLE
    binding.members.append(TOGGLE_MEMBER)
    client.set_iam_policy(
        request=iam_policy_pb2.SetIamPolicyRequest(resource=sa_resource, policy=policy)
    )

    # Remove binding (re-fetch to avoid etag conflicts)
    policy = client.get_iam_policy(request=iam_policy_pb2.GetIamPolicyRequest(resource=sa_resource))
    keep = []
    for b in policy.bindings:
        if b.role == TOGGLE_ROLE and TOGGLE_MEMBER in b.members and len(b.members) == 1:
            continue
        keep.append(b)
    del policy.bindings[:]
    for b in keep:
        new_b = policy.bindings.add()
        new_b.role = b.role
        new_b.members.extend(b.members)
    client.set_iam_policy(
        request=iam_policy_pb2.SetIamPolicyRequest(resource=sa_resource, policy=policy)
    )

    return "toggled"


def _update_vm_label() -> str:
    """Update a VM label (COMPUTE zone: setLabels → compute metadata audit event)."""
    client = _get_compute_client()
    now = datetime.now(UTC)

    instance = client.get(project=PROJECT_ID, zone=VM_ZONE, instance=VM_NAME)

    # Update the maintenance timestamp label
    labels = dict(instance.labels) if instance.labels else {}
    labels["last-maintenance"] = now.strftime("%Y%m%dt%H%M")

    label_fingerprint = instance.label_fingerprint
    request = compute_v1.SetLabelsInstanceRequest(
        project=PROJECT_ID,
        zone=VM_ZONE,
        instance=VM_NAME,
        instances_set_labels_request_resource=compute_v1.InstancesSetLabelsRequest(
            labels=labels,
            label_fingerprint=label_fingerprint,
        ),
    )
    client.set_labels(request=request)
    return f"label updated: last-maintenance={labels['last-maintenance']}"


@app.route("/maintain")
def maintain():
    """Run hourly maintenance cycle: secret rotation + token gen + IAM toggle + VM label."""
    now = datetime.now(UTC)
    results = {}

    try:
        # 1. SECRET zone: AddSecretVersion
        results["secret_version"] = _rotate_secret()

        # 2. IDENTITY zone: GenerateAccessToken (IAM_IMPERSONATE)
        results["token_generated"] = _generate_token()

        # 3. CONTROL zone: SetIamPolicy (add) + SetIamPolicy (remove)
        results["iam_toggled"] = _toggle_iam_binding()

        # 4. COMPUTE zone: VM label update (setLabels → compute metadata change)
        try:
            results["vm_label"] = _update_vm_label()
        except Exception as e:
            # Non-fatal — VM may not exist in all environments
            logger.warning("VM label update failed (non-fatal): %s", e)
            results["vm_label"] = f"skipped: {e}"

        results["status"] = "ok"
        results["ts"] = now.isoformat()
        return jsonify(results), 200

    except Exception as e:
        logger.exception("Maintenance failed: %s", e)
        return jsonify({"status": "error", "detail": str(e), "ts": now.isoformat()}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))  # noqa: S104
