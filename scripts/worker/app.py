"""Murmur normal-worker: realistic Cloud Run service for audit log generation.

Three endpoints:
  GET /        — Main worker: read secret → read GCS input → write GCS output
  GET /health  — Health check: verify secret + bucket access
  GET /cleanup — Cleanup: delete output objects older than 1 day
"""

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta

from flask import Flask, jsonify
from google.cloud import secretmanager, storage

app = Flask(__name__)

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
INPUT_BUCKET = os.environ.get("INPUT_BUCKET", "murmur-input-sandbox")
OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET", "murmur-output-sandbox")
SECRET_NAME = os.environ.get("SECRET_NAME", "secret_high")
HEALTH_SECRET = os.environ.get("HEALTH_SECRET", "secret_low")


def _read_secret(secret_name: str) -> str:
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{PROJECT_ID}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8")


def _get_storage_client():
    return storage.Client(project=PROJECT_ID)


@app.route("/")
def main_worker():
    """Main worker: read secret, read input, process, write output."""
    now = datetime.now(UTC)

    # 1. Read secret
    secret_value = _read_secret(SECRET_NAME)

    # 2. Read a file from input bucket
    client = _get_storage_client()
    input_bucket = client.bucket(INPUT_BUCKET)
    blobs = list(input_bucket.list_blobs())
    if not blobs:
        return jsonify({"status": "ok", "detail": "no input files", "ts": now.isoformat()}), 200

    # Pick a file (rotate through them based on minute)
    blob = blobs[now.minute % len(blobs)]
    content = blob.download_as_text()

    # 3. Process: hash content with secret as salt + timestamp
    digest = hashlib.sha256(f"{secret_value}:{content}:{now.isoformat()}".encode()).hexdigest()[:16]
    result = {
        "source": blob.name,
        "digest": digest,
        "processed_at": now.isoformat(),
        "input_size": len(content),
    }

    # 4. Write result to output bucket
    output_bucket = client.bucket(OUTPUT_BUCKET)
    output_name = f"results/{now.strftime('%Y-%m-%d')}/{now.strftime('%H%M%S')}_{digest}.json"
    output_blob = output_bucket.blob(output_name)
    output_blob.upload_from_string(json.dumps(result), content_type="application/json")

    return jsonify({"status": "ok", "input": blob.name, "output": output_name, "ts": now.isoformat()}), 200


@app.route("/health")
def health_check():
    """Health check: verify secret access + bucket access."""
    now = datetime.now(UTC)

    # Read a low-sensitivity secret (verifies Secret Manager access)
    _read_secret(HEALTH_SECRET)

    # List input bucket (verifies GCS access)
    client = _get_storage_client()
    input_bucket = client.bucket(INPUT_BUCKET)
    blob_count = sum(1 for _ in input_bucket.list_blobs())

    return jsonify({"status": "healthy", "input_blobs": blob_count, "ts": now.isoformat()}), 200


@app.route("/cleanup")
def cleanup():
    """Cleanup: delete output objects older than 1 day."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=1)

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

    # Write summary
    summary = {"deleted": deleted, "kept": kept, "cutoff": cutoff.isoformat(), "ts": now.isoformat()}
    summary_blob = output_bucket.blob(f"cleanup/{now.strftime('%Y-%m-%d')}_summary.json")
    summary_blob.upload_from_string(json.dumps(summary), content_type="application/json")

    return jsonify({"status": "ok", **summary}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
