"""Blob fetching and incremental ingestion pipeline.

Abstracts file discovery behind a BlobSource protocol so the same
fetch_and_ingest() orchestrator works with local files (dev/test)
and GCS (production). Checkpointing ensures idempotent re-runs.

Pipeline (single-format): list_blobs → filter → read → parse → enrich → insert → checkpoint
Pipeline (multi-format): per-prefix fetch → dispatch parse → correlate → enrich → insert
"""

import dataclasses
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

import duckdb

from config.settings import SETTINGS
from src.ingest.cloudrun_parser import CloudRunRequest
from src.ingest.correlate import ServiceWorkerMap, correlate_events
from src.ingest.dedup import insert_event
from src.ingest.multi_parser import dispatch_parse
from src.ingest.parser import parse_audit_log
from src.ingest.provenance_ingest import enrich_provenance
from src.ingest.scheduler_parser import SchedulerExecution
from src.schema import CanonicalEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# BlobSource protocol — the abstraction that lets us swap GCS for local
# ---------------------------------------------------------------------------


@runtime_checkable
class BlobSource(Protocol):
    def list_blobs(self, prefix: str | None = None) -> list[str]:
        """Return sorted blob names, optionally filtered by prefix."""
        ...

    def read_blob(self, name: str) -> str:
        """Return the full text content of a blob."""
        ...


# ---------------------------------------------------------------------------
# LocalFetcher — reads from a directory on disk
# ---------------------------------------------------------------------------


class LocalFetcher:
    """BlobSource backed by a local directory. For dev and testing."""

    def __init__(self, directory: str) -> None:
        self._dir = Path(directory)
        if self._dir.exists() and not self._dir.is_dir():
            raise ValueError(f"Path is not a directory: {self._dir}")

    def list_blobs(self, prefix: str | None = None) -> list[str]:
        if not self._dir.exists():
            return []
        names = sorted(
            f.name
            for f in self._dir.iterdir()
            if f.is_file() and f.suffix in (".json", ".jsonl")
        )
        if prefix is not None:
            names = [n for n in names if n.startswith(prefix)]
        return names

    def read_blob(self, name: str) -> str:
        path = self._dir / name
        if not path.exists():
            raise FileNotFoundError(f"Blob not found: {path}")
        return path.read_text()


# ---------------------------------------------------------------------------
# SingleFileFetcher — wraps a single file as a BlobSource
# ---------------------------------------------------------------------------


class SingleFileFetcher:
    """BlobSource backed by a single file on disk."""

    def __init__(self, file_path: str) -> None:
        self._path = Path(file_path)
        if not self._path.is_file():
            raise FileNotFoundError(f"File not found: {self._path}")

    def list_blobs(self, prefix: str | None = None) -> list[str]:
        name = self._path.name
        if prefix is not None and not name.startswith(prefix):
            return []
        return [name]

    def read_blob(self, name: str) -> str:
        if name != self._path.name:
            raise FileNotFoundError(f"Blob not found: {name}")
        return self._path.read_text()


# ---------------------------------------------------------------------------
# GCSFetcher — reads from a GCS bucket
# ---------------------------------------------------------------------------


class GCSFetcher:
    """BlobSource backed by a Google Cloud Storage bucket."""

    def __init__(self, bucket_name: str) -> None:
        from google.cloud import storage

        client = storage.Client()
        self._bucket = client.bucket(bucket_name)

    def list_blobs(self, prefix: str | None = None) -> list[str]:
        blobs = self._bucket.list_blobs(prefix=prefix)
        return sorted(b.name for b in blobs)

    def read_blob(self, name: str) -> str:
        from google.cloud.exceptions import NotFound

        blob = self._bucket.blob(name)
        try:
            return blob.download_as_text()
        except NotFound:
            raise FileNotFoundError(f"Blob not found: {name}")


# ---------------------------------------------------------------------------
# Checkpoint — tracks last-processed blob per source in DuckDB
# ---------------------------------------------------------------------------


def get_checkpoint(db: duckdb.DuckDBPyConnection, source_id: str) -> str | None:
    """Return last_blob_name for a source, or None if never ingested."""
    row = db.execute(
        "SELECT last_blob_name FROM ingest_checkpoints WHERE source_id = ?",
        [source_id],
    ).fetchone()
    return row[0] if row else None


def set_checkpoint(
    db: duckdb.DuckDBPyConnection, source_id: str, blob_name: str
) -> None:
    """Upsert the checkpoint for a source."""
    db.execute(
        """
        INSERT INTO ingest_checkpoints (source_id, last_blob_name, last_fetched_ts)
        VALUES (?, ?, ?)
        ON CONFLICT (source_id) DO UPDATE
        SET last_blob_name = excluded.last_blob_name,
            last_fetched_ts = excluded.last_fetched_ts
        """,
        [source_id, blob_name, datetime.now(UTC)],
    )


# ---------------------------------------------------------------------------
# fetch_and_ingest — the orchestrator
# ---------------------------------------------------------------------------


def fetch_and_ingest(
    db: duckdb.DuckDBPyConnection,
    source: BlobSource,
    source_id: str,
) -> dict:
    """Fetch blobs from source, parse, enrich, insert. Returns stats dict.

    Resumes from last checkpoint. Updates checkpoint after each blob.
    """
    known_initiators = SETTINGS.load_known_initiators()
    checkpoint = get_checkpoint(db, source_id)

    all_blobs = source.list_blobs()

    # Filter to blobs after checkpoint (lexicographic ordering)
    if checkpoint is not None:
        all_blobs = [b for b in all_blobs if b > checkpoint]

    stats = {"blobs_processed": 0, "inserted": 0, "skipped": 0, "parse_errors": 0}

    for blob_name in all_blobs:
        logger.info("Processing blob: %s", blob_name)
        content = source.read_blob(blob_name)
        blob_inserted, blob_skipped, blob_errors = _ingest_content(
            db, content, known_initiators, blob_name
        )
        stats["inserted"] += blob_inserted
        stats["skipped"] += blob_skipped
        stats["parse_errors"] += blob_errors
        stats["blobs_processed"] += 1
        set_checkpoint(db, source_id, blob_name)

    return stats


def _ingest_content(
    db: duckdb.DuckDBPyConnection,
    content: str,
    known_initiators: set[str],
    blob_name: str,
) -> tuple[int, int, int]:
    """Parse and ingest JSONL content. Returns (inserted, skipped, errors)."""
    inserted = 0
    skipped = 0
    errors = 0

    for line_num, line in enumerate(content.split("\n"), 1):
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
            event = parse_audit_log(raw)
            event = enrich_provenance(event, known_initiators)
            if insert_event(db, event):
                inserted += 1
            else:
                skipped += 1
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            errors += 1
            logger.warning("%s:%d parse error: %s", blob_name, line_num, e)

    return inserted, skipped, errors


# ---------------------------------------------------------------------------
# Multi-format pipeline helpers
# ---------------------------------------------------------------------------


def _parse_blob_entries(content: str) -> list[dict]:
    """Parse blob content as NDJSON or JSON array. Returns only dict entries."""
    content = content.strip()
    if not content:
        return []

    entries: list[dict] = []

    # Try NDJSON first (most common for GCS sink)
    if content.startswith("{"):
        for line_num, line in enumerate(content.split("\n"), 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("NDJSON line %d: parse error, skipping", line_num)
                continue
            if isinstance(obj, dict):
                entries.append(obj)
            else:
                logger.warning("NDJSON line %d: expected object, got %s", line_num, type(obj).__name__)
        return entries

    # Try JSON array
    if content.startswith("["):
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    entries.append(item)
            return entries

    return []


def fetch_and_ingest_multi(
    db: duckdb.DuckDBPyConnection,
    source: BlobSource,
    source_id_prefix: str,
    prefixes: list[str] | None = None,
    service_worker_map: ServiceWorkerMap | None = None,
) -> dict:
    """Multi-format fetch + correlate + ingest pipeline.

    For each GCS prefix:
      1. Fetch new blobs (using per-prefix checkpoints)
      2. Parse using multi-format dispatcher
    Then correlate scheduler + Cloud Run + audit events, and insert.

    Returns stats dict with per-type counts.
    """
    if prefixes is None:
        prefixes = SETTINGS.gcs_prefixes
    if service_worker_map is None:
        service_worker_map = SETTINGS.service_worker_map

    known_initiators = SETTINGS.load_known_initiators()

    # Collect parsed entries by type across all prefixes
    all_scheduler: list[SchedulerExecution] = []
    all_cloudrun: list[CloudRunRequest] = []
    all_audit: list[CanonicalEvent] = []

    stats = {
        "blobs_processed": 0,
        "audit_parsed": 0,
        "scheduler_parsed": 0,
        "cloudrun_parsed": 0,
        "parse_errors": 0,
        "inserted": 0,
        "skipped": 0,
        "correlated": 0,
    }

    # Phase 1: Fetch and parse from each prefix
    for prefix in prefixes:
        checkpoint_id = f"{source_id_prefix}:{prefix}"
        checkpoint = get_checkpoint(db, checkpoint_id)
        all_blobs = source.list_blobs(prefix=prefix)

        if checkpoint is not None:
            all_blobs = [b for b in all_blobs if b > checkpoint]

        for blob_name in all_blobs:
            logger.info("Processing blob: %s", blob_name)
            content = source.read_blob(blob_name)
            raw_entries = _parse_blob_entries(content)

            for raw in raw_entries:
                try:
                    result = dispatch_parse(raw)
                    if isinstance(result, SchedulerExecution):
                        all_scheduler.append(result)
                        stats["scheduler_parsed"] += 1
                    elif isinstance(result, CloudRunRequest):
                        all_cloudrun.append(result)
                        stats["cloudrun_parsed"] += 1
                    elif isinstance(result, CanonicalEvent):
                        all_audit.append(result)
                        stats["audit_parsed"] += 1
                    else:
                        stats["parse_errors"] += 1
                except (KeyError, ValueError) as e:
                    stats["parse_errors"] += 1
                    logger.warning("%s parse error: %s", blob_name, e)

            stats["blobs_processed"] += 1
            set_checkpoint(db, checkpoint_id, blob_name)

    # Phase 2: Correlate
    correlation_results = correlate_events(
        scheduler_entries=all_scheduler,
        cloudrun_entries=all_cloudrun,
        audit_events=all_audit,
        service_worker_map=service_worker_map,
    )

    # Phase 3: Apply correlation, enrich, insert
    for cr in correlation_results:
        event = cr.event
        if cr.trigger_ref:
            event = dataclasses.replace(
                event,
                trigger_ref=cr.trigger_ref,
                correlation_confidence=cr.correlation_confidence,
            )
            stats["correlated"] += 1

        event = enrich_provenance(event, known_initiators)
        if insert_event(db, event):
            stats["inserted"] += 1
        else:
            stats["skipped"] += 1

    return stats
