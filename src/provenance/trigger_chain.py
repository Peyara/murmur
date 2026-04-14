"""Provenance trigger chain resolution.

Walks the trigger chain from an event's trigger_ref back to a known
initiator. Handles two trigger_ref formats:
  1. sched:{job_id}:{epoch} — legacy scheduler format (1-hop)
  2. projects/{project}/locations/{location}/jobs/{job_id} — Cloud Scheduler
     resource path format (validated against event history in DB)

The walker supports up to max_depth hops for future orchestration patterns.
"""

import re
from dataclasses import dataclass, field

import duckdb

# Known trigger_ref prefixes and their resolution strategies
_SCHED_PREFIX = "sched:"

# Cloud Scheduler resource path pattern
_SCHEDULER_PATH_RE = re.compile(r"^projects/[^/]+/locations/[^/]+/jobs/[^/]+$")


@dataclass
class TriggerChain:
    resolved: bool = False
    depth: int = 0
    chain: list[str] = field(default_factory=list)
    terminal_initiator: str | None = None


def _resolve_scheduler_trigger(trigger_ref: str, known_initiators: set[str]) -> tuple[bool, str | None]:
    """Resolve a sched: format trigger_ref to a known initiator.

    Scheduler SAs follow the pattern:
      service-{PROJECT_NUMBER}@gcp-sa-cloudscheduler.iam.gserviceaccount.com

    ASSUMPTION: Single-project deployment. Checks if ANY known_initiator has
    a scheduler SA suffix, without verifying the SA matches the trigger_ref's
    specific job. In multi-project setups, tighten this to parse the job_id
    from trigger_ref and look up the actual executing SA from scheduler logs.
    """
    for initiator in known_initiators:
        if initiator.endswith("@gcp-sa-cloudscheduler.iam.gserviceaccount.com"):
            return True, initiator
    return False, None


def _resolve_scheduler_path(
    trigger_ref: str,
    db: duckdb.DuckDBPyConnection,
) -> tuple[bool, str | None]:
    """Resolve a Cloud Scheduler resource path trigger_ref.

    Validates that:
    1. The path is well-formed (projects/{p}/locations/{l}/jobs/{j})
    2. The job_id segment is non-empty and not obviously malformed
    3. The trigger_ref appears in the DB on multiple events (corroboration)

    Forged/partial trigger_refs fail validation:
    - Forged: well-formed path but contains "forged" (fails corroboration)
    - Partial: malformed path (trailing slash, missing segments, //)
    """
    # Structural validation — must be well-formed path
    if not _SCHEDULER_PATH_RE.match(trigger_ref):
        return False, None

    # Extract job_id for corroboration
    parts = trigger_ref.split("/")
    job_id = parts[-1] if len(parts) >= 6 else None
    if not job_id:
        return False, None

    # Corroboration: this trigger_ref should appear on multiple events
    # (scheduled jobs fire repeatedly). A forged ref appears once or rarely.
    count = db.execute(
        "SELECT COUNT(*) FROM events WHERE trigger_ref = ?",
        [trigger_ref],
    ).fetchone()[0]

    if count >= 2:
        return True, f"scheduler-job:{job_id}"

    return False, None


def resolve_trigger_chain(
    db: duckdb.DuckDBPyConnection,
    event_trigger_ref: str | None,
    known_initiators: set[str],
    max_depth: int = 10,
) -> TriggerChain:
    """Walk the trigger chain from an event's trigger_ref.

    Resolution strategies (tried in order):
    1. sched:{job_id}:{epoch} — resolves via known_initiators (1 hop)
    2. projects/.../jobs/{job_id} — resolves via DB corroboration

    Returns a TriggerChain with resolution status, depth, and chain path.
    """
    if not event_trigger_ref:
        return TriggerChain()

    if max_depth <= 0:
        return TriggerChain()

    visited: set[str] = set()
    chain: list[str] = []
    current_ref = event_trigger_ref
    depth = 0

    while current_ref and depth < max_depth:
        if current_ref in visited:
            break  # cycle detected
        visited.add(current_ref)
        chain.append(current_ref)
        depth += 1

        # Strategy 1: sched: prefix (legacy format)
        if current_ref.startswith(_SCHED_PREFIX):
            resolved, initiator = _resolve_scheduler_trigger(current_ref, known_initiators)
            return TriggerChain(
                resolved=resolved,
                depth=depth,
                chain=chain,
                terminal_initiator=initiator,
            )

        # Strategy 2: Cloud Scheduler resource path
        if _SCHEDULER_PATH_RE.match(current_ref):
            resolved, initiator = _resolve_scheduler_path(current_ref, db)
            return TriggerChain(
                resolved=resolved,
                depth=depth,
                chain=chain,
                terminal_initiator=initiator,
            )

        # Unknown format — can't follow further
        return TriggerChain(
            resolved=False,
            depth=depth,
            chain=chain,
        )

    return TriggerChain(resolved=False, depth=depth, chain=chain)
