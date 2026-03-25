"""Blob fetching and incremental ingestion pipeline.

Abstracts file discovery behind a BlobSource protocol so the same
fetch_and_ingest() orchestrator works with local files (dev/test)
and GCS (production). Checkpointing ensures idempotent re-runs.

Pipeline: list_blobs → filter by checkpoint → read → parse → enrich → insert → update checkpoint
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

import duckdb

from config.settings import SETTINGS
from src.ingest.dedup import insert_event
from src.ingest.parser import parse_audit_log
from src.ingest.provenance_ingest import enrich_provenance

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
