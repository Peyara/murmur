"""Murmur normal-worker: realistic Cloud Run service for audit log generation.

Three endpoints:
  GET  /        — Main worker: read secret → read GCS input → write GCS output
  GET  /health  — Health check: verify secret + bucket access
  POST /cleanup — Cleanup: delete output objects older than 1 day
"""

import base64
import hashlib
import json
import logging
import os
from datetime import UTC, datetime, timedelta

from flask import Flask, jsonify
from google.cloud import kms, secretmanager, storage

app = Flask(__name__)
logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
INPUT_BUCKET = os.environ.get("INPUT_BUCKET", "murmur-input-sandbox")
OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET", "murmur-output-sandbox")
SECRET_NAME = os.environ.get("SECRET_NAME", "secret_high")
HEALTH_SECRET = os.environ.get("HEALTH_SECRET", "secret_low")
KMS_LOCATION = os.environ.get("GCP_REGION", "us-central1")
KMS_KEYRING = os.environ.get("KMS_KEYRING", "murmur-keyring")
KMS_KEY = os.environ.get("KMS_KEY", "worker-encrypt-key")

# Module-level singletons — clients are thread-safe and reusable
_sm_client: secretmanager.SecretManagerServiceClient | None = None
_gcs_client: storage.Client | None = None
_kms_client: kms.KeyManagementServiceClient | None = None


def _get_secret_client() -> secretmanager.SecretManagerServiceClient:
    global _sm_client  # noqa: PLW0603
    if _sm_client is None:
        _sm_client = secretmanager.SecretManagerServiceClient()
    return _sm_client


def _get_storage_client() -> storage.Client:
    global _gcs_client  # noqa: PLW0603
    if _gcs_client is None:
        _gcs_client = storage.Client(project=PROJECT_ID)
    return _gcs_client


def _get_kms_client() -> kms.KeyManagementServiceClient:
    global _kms_client  # noqa: PLW0603
    if _kms_client is None:
        _kms_client = kms.KeyManagementServiceClient()
    return _kms_client


def _kms_encrypt(plaintext: str) -> str:
    """Encrypt data using Cloud KMS. Generates KMS_DECRYPT audit events."""
    client = _get_kms_client()
    key_name = client.crypto_key_path(PROJECT_ID, KMS_LOCATION, KMS_KEYRING, KMS_KEY)
    response = client.encrypt(request={"name": key_name, "plaintext": plaintext.encode()})
    return base64.b64encode(response.ciphertext).decode()


def _read_secret(secret_name: str) -> str:
    client = _get_secret_client()
    name = f"projects/{PROJECT_ID}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8")


@app.route("/")
def main_worker():
    """Main worker: read secret, read input, process, write output."""
    now = datetime.now(UTC)
    try:
        # 1. Read secret (generates SECRET_ACCESS audit event)
        _read_secret(SECRET_NAME)

        # 2. Read a file from input bucket
        client = _get_storage_client()
        input_bucket = client.bucket(INPUT_BUCKET)
        blobs = list(input_bucket.list_blobs())
        if not blobs:
            return jsonify({"status": "ok", "detail": "no input files", "ts": now.isoformat()}), 200

        # Pick a file (rotate through them based on minute)
        blob = blobs[now.minute % len(blobs)]
        content = blob.download_as_text()

        # 3. Process: hash content + timestamp (secret read is for audit generation, not processing)
        digest = hashlib.sha256(f"{content}:{now.isoformat()}".encode()).hexdigest()[:16]

        # 4. Encrypt digest via KMS (generates KMS audit event in SECRET zone)
        encrypted_digest = _kms_encrypt(digest)

        result = {
            "source": blob.name,
            "digest": digest,
            "encrypted_digest": encrypted_digest,
            "processed_at": now.isoformat(),
            "input_size": len(content),
        }

        # 5. Write result to output bucket
        output_bucket = client.bucket(OUTPUT_BUCKET)
        output_name = f"results/{now.strftime('%Y-%m-%d')}/{now.strftime('%H%M%S')}_{digest}.json"
        output_blob = output_bucket.blob(output_name)
        output_blob.upload_from_string(json.dumps(result), content_type="application/json")

        return jsonify({"status": "ok", "input": blob.name, "output": output_name, "ts": now.isoformat()}), 200

    except Exception as e:
        logger.exception("Worker failed: %s", e)
        return jsonify({"status": "error", "detail": str(e), "ts": now.isoformat()}), 500


@app.route("/health")
def health_check():
    """Health check: verify secret access + bucket access."""
    now = datetime.now(UTC)
    try:
        _read_secret(HEALTH_SECRET)

        client = _get_storage_client()
        input_bucket = client.bucket(INPUT_BUCKET)
        blob_count = sum(1 for _ in input_bucket.list_blobs())

        return jsonify({"status": "healthy", "input_blobs": blob_count, "ts": now.isoformat()}), 200

    except Exception as e:
        logger.exception("Health check failed: %s", e)
        return jsonify({"status": "unhealthy", "detail": str(e), "ts": now.isoformat()}), 500


@app.route("/cleanup", methods=["POST"])
def cleanup():
    """Cleanup: delete output objects older than 1 day."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=1)
    try:
        client = _get_storage_client()
        output_bucket = client.bucket(OUTPUT_BUCKET)

        deleted = 0
        kept = 0
        for blob in output_bucket.list_blobs(prefix="results/"):
            if blob.time_created and blob.time_created < cutoff:
                blob.delete()
                deleted += 1
            else:
                kept += 1

        summary = {"deleted": deleted, "kept": kept, "cutoff": cutoff.isoformat(), "ts": now.isoformat()}
        summary_blob = output_bucket.blob(f"cleanup/{now.strftime('%Y-%m-%d_%H%M%S')}_summary.json")
        summary_blob.upload_from_string(json.dumps(summary), content_type="application/json")

        return jsonify({"status": "ok", **summary}), 200

    except Exception as e:
        logger.exception("Cleanup failed: %s", e)
        return jsonify({"status": "error", "detail": str(e), "ts": now.isoformat()}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))  # noqa: S104
