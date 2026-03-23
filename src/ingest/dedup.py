"""Event deduplication — idempotent insertion into DuckDB.

Uses deterministic event_id (SHA-256 hash) and INSERT OR IGNORE
to ensure re-ingestion of the same log entries is safe.
"""

import hashlib

import duckdb

from src.schema import CanonicalEvent


def compute_event_id(ts: str, actor_id: str, method_name: str, resource: str, insert_id: str) -> str:
    """Deterministic event ID from content hash. 32-char hex string."""
    content = f"{ts}|{actor_id}|{method_name}|{resource}|{insert_id}"
    # Truncate to 128 bits (32 hex chars). At Murmur's scale (<1M events),
    # collision probability is ~2^-97 (birthday bound). Full 256 bits unnecessary.
    return hashlib.sha256(content.encode()).hexdigest()[:32]


def insert_event(db: duckdb.DuckDBPyConnection, event: CanonicalEvent) -> bool:
    """Insert event into DuckDB. Returns True if inserted, False if duplicate.

    Uses SELECT check + INSERT rather than COUNT(*) before/after to avoid
    O(n) table scans on every insert.
    """
    exists = db.execute(
        "SELECT 1 FROM events WHERE event_id = ?", [event.event_id]
    ).fetchone()
    if exists:
        return False

    db.execute(
        """
        INSERT INTO events (
            event_id, ts, window_start, actor_id, actor_type,
            actor_subtype, orchestrator_id, trigger_ref,
            provenance_level, provenance_source,
            action_type, action_subtype, tool_name, tool_parameters_hash, model_id,
            target_id, target_type, target_zone,
            result, project_id, env, is_deploy, is_incident,
            risk_tags, raw_ref, coverage_flag
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            event.event_id,
            event.ts,
            event.window_start,
            event.actor_id,
            str(event.actor_type.value),
            str(event.actor_subtype.value) if event.actor_subtype else None,
            event.orchestrator_id,
            event.trigger_ref,
            str(event.provenance_level.value),
            str(event.provenance_source.value),
            str(event.action_type.value),
            event.action_subtype,
            event.tool_name,
            event.tool_parameters_hash,
            event.model_id,
            event.target_id,
            str(event.target_type.value),
            str(event.target_zone.value),
            str(event.result.value),
            event.project_id,
            event.env,
            event.is_deploy,
            event.is_incident,
            event.risk_tags,
            event.raw_ref,
            event.coverage_flag,
        ],
    )
    return True
