"""Provenance trigger chain resolution.

Walks the trigger chain from an event's trigger_ref back to a known
initiator. Currently handles scheduler-format trigger_refs (1-hop).
The walker supports up to max_depth hops for future orchestration patterns.
"""

from dataclasses import dataclass, field

import duckdb

# Known trigger_ref prefixes and their resolution strategies
_SCHED_PREFIX = "sched:"


@dataclass
class TriggerChain:
    resolved: bool = False
    depth: int = 0
    chain: list[str] = field(default_factory=list)
    terminal_initiator: str | None = None


def _resolve_scheduler_trigger(
    trigger_ref: str, known_initiators: set[str]
) -> tuple[bool, str | None]:
    """Resolve a scheduler trigger_ref to a known initiator.

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


def resolve_trigger_chain(
    db: duckdb.DuckDBPyConnection,
    event_trigger_ref: str | None,
    known_initiators: set[str],
    max_depth: int = 10,
) -> TriggerChain:
    """Walk the trigger chain from an event's trigger_ref.

    For scheduler triggers (sched:{job_id}:{epoch}), resolves in 1 hop
    by checking if the scheduler SA is a known initiator.

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

        if current_ref.startswith(_SCHED_PREFIX):
            resolved, initiator = _resolve_scheduler_trigger(
                current_ref, known_initiators
            )
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
