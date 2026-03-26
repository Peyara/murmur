"""Event deduplication — idempotent insertion into DuckDB.

Uses deterministic event_id (SHA-256 hash) and ON CONFLICT DO NOTHING
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

    Uses ON CONFLICT (event_id) DO NOTHING with RETURNING to atomically
    skip duplicates without a separate SELECT round-trip.
    """
    result = db.execute(
        """
        INSERT INTO events (
            event_id, ts, window_start, actor_id, actor_type,
            actor_subtype, orchestrator_id, trigger_ref,
            provenance_level, provenance_source,
            action_type, action_subtype, tool_name, tool_parameters_hash, model_id,
            target_id, target_type, target_zone,
            correlation_confidence,
            result, project_id, env, is_deploy, is_incident, is_infrastructure,
            risk_tags, raw_ref, coverage_flag
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (event_id) DO NOTHING
        RETURNING event_id
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
            event.correlation_confidence,
            str(event.result.value),
            event.project_id,
            event.env,
            event.is_deploy,
            event.is_incident,
            event.is_infrastructure,
            event.risk_tags,
            event.raw_ref,
            event.coverage_flag,
        ],
    )
    return result.fetchone() is not None
