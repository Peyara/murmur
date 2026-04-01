"""Scoring invariants layer.

10 invariants (INV_001-INV_010) that detect suspicious patterns in
audit log events within a 15-min window. Each invariant is a pure
function returning an InvariantResult.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

import duckdb

from src.schema import ActionType, CanonicalEvent


@dataclass
class InvariantResult:
    id: str
    fired: bool
    severity: int  # 0 if not fired
    explanation: str


def _inv_001(events: list[CanonicalEvent]) -> InvariantResult:
    """IAM policy change outside deploy window."""
    for e in events:
        if e.action_type == ActionType.IAM_SET_POLICY.value and not e.is_deploy:
            return InvariantResult(
                "INV_001", True, 5,
                f"IAM policy change by {e.actor_id} outside deploy window",
            )
    return InvariantResult("INV_001", False, 0, "")


def _inv_002(events: list[CanonicalEvent]) -> InvariantResult:
    """Service account key created."""
    for e in events:
        if e.action_type == ActionType.IAM_CREATE_KEY.value:
            return InvariantResult(
                "INV_002", True, 5,
                f"SA key created targeting {e.target_id}",
            )
    return InvariantResult("INV_002", False, 0, "")


def _inv_003(events: list[CanonicalEvent], known_initiators: set[str]) -> InvariantResult:
    """Key created by novel (unknown) actor."""
    for e in events:
        if e.action_type == ActionType.IAM_CREATE_KEY.value:
            if e.actor_id not in known_initiators:
                return InvariantResult(
                    "INV_003", True, 5,
                    f"SA key created by novel actor {e.actor_id}",
                )
    return InvariantResult("INV_003", False, 0, "")


def _inv_004(events: list[CanonicalEvent]) -> InvariantResult:
    """Impersonation token generated."""
    for e in events:
        if e.action_type == ActionType.IAM_IMPERSONATE.value:
            return InvariantResult(
                "INV_004", True, 4,
                f"Impersonation by {e.actor_id} targeting {e.target_id}",
            )
    return InvariantResult("INV_004", False, 0, "")


def _inv_005(
    db: duckdb.DuckDBPyConnection,
    window_start: datetime,
    actor_id: str,
    events: list[CanonicalEvent],
) -> InvariantResult:
    """Impersonation rate spike (>2x rolling 30-day average)."""
    current_count = sum(
        1 for e in events if e.action_type == ActionType.IAM_IMPERSONATE.value
    )
    if current_count == 0:
        return InvariantResult("INV_005", False, 0, "")

    # 30-day lookback: average impersonation count per window for this actor
    lookback = window_start - timedelta(days=30)
    row = db.execute(
        "SELECT AVG(cnt) FROM ("
        "  SELECT COUNT(*) as cnt FROM events "
        "  WHERE actor_id = ? AND action_type = ? "
        "  AND window_start >= ? AND window_start < ? "
        "  GROUP BY window_start"
        ")",
        [actor_id, ActionType.IAM_IMPERSONATE.value, lookback, window_start],
    ).fetchone()

    baseline = row[0] if row and row[0] is not None else 0.0

    if baseline == 0 or current_count > 2 * baseline:
        return InvariantResult(
            "INV_005", True, 5,
            f"Impersonation spike: {current_count} events (baseline={baseline:.1f})",
        )
    return InvariantResult("INV_005", False, 0, "")


def _inv_006(
    db: duckdb.DuckDBPyConnection,
    window_start: datetime,
    actor_id: str,
    events: list[CanonicalEvent],
) -> InvariantResult:
    """Secret accessed by actor who hasn't accessed this target in 30 days."""
    secret_targets = list({
        e.target_id for e in events
        if e.action_type == ActionType.SECRET_ACCESS.value
    })
    if not secret_targets:
        return InvariantResult("INV_006", False, 0, "")

    lookback = window_start - timedelta(days=30)
    placeholders = ", ".join("?" for _ in secret_targets)
    # S608 false positive: placeholders are "?" literals, all values parameterized
    query = (
        f"SELECT DISTINCT target_id FROM events "  # noqa: S608
        f"WHERE actor_id = ? AND action_type = ? "
        f"AND target_id IN ({placeholders}) "
        f"AND window_start >= ? AND window_start < ?"
    )
    rows = db.execute(
        query,
        [actor_id, ActionType.SECRET_ACCESS.value, *secret_targets,
         lookback, window_start],
    ).fetchall()
    known_targets = {r[0] for r in rows}

    for tid in secret_targets:
        if tid not in known_targets:
            return InvariantResult(
                "INV_006", True, 5,
                f"New actor {actor_id} accessing secret {tid}",
            )
    return InvariantResult("INV_006", False, 0, "")


def _inv_007(events: list[CanonicalEvent]) -> InvariantResult:
    """Secret access in same window as IAM policy change."""
    has_policy = any(e.action_type == ActionType.IAM_SET_POLICY.value for e in events)
    has_secret = any(e.action_type == ActionType.SECRET_ACCESS.value for e in events)
    if has_policy and has_secret:
        return InvariantResult(
            "INV_007", True, 5,
            "Secret access co-occurs with IAM policy change in same window",
        )
    return InvariantResult("INV_007", False, 0, "")


def _inv_008(
    db: duckdb.DuckDBPyConnection,
    window_start: datetime,
    actor_id: str,
    events: list[CanonicalEvent],
) -> InvariantResult:
    """KMS decrypt by actor who hasn't decrypted this key in 30 days."""
    kms_targets = list({
        e.target_id for e in events
        if e.action_type == ActionType.KMS_DECRYPT.value
    })
    if not kms_targets:
        return InvariantResult("INV_008", False, 0, "")

    lookback = window_start - timedelta(days=30)
    placeholders = ", ".join("?" for _ in kms_targets)
    # S608 false positive: placeholders are "?" literals, all values parameterized
    query = (
        f"SELECT DISTINCT target_id FROM events "  # noqa: S608
        f"WHERE actor_id = ? AND action_type = ? "
        f"AND target_id IN ({placeholders}) "
        f"AND window_start >= ? AND window_start < ?"
    )
    rows = db.execute(
        query,
        [actor_id, ActionType.KMS_DECRYPT.value, *kms_targets,
         lookback, window_start],
    ).fetchall()
    known_targets = {r[0] for r in rows}

    for tid in kms_targets:
        if tid not in known_targets:
            return InvariantResult(
                "INV_008", True, 4,
                f"New actor {actor_id} decrypting {tid}",
            )
    return InvariantResult("INV_008", False, 0, "")


def _inv_009(events: list[CanonicalEvent]) -> InvariantResult:
    """Compute metadata change."""
    for e in events:
        if e.action_type == ActionType.COMPUTE_METADATA_CHANGE.value:
            return InvariantResult(
                "INV_009", True, 5,
                f"Compute metadata change on {e.target_id}",
            )
    return InvariantResult("INV_009", False, 0, "")


def _inv_010(
    db: duckdb.DuckDBPyConnection,
    window_start: datetime,
    actor_id: str,
) -> InvariantResult:
    """New edge to SECRET or EXFIL_RISK zone."""
    row = db.execute(
        "SELECT source_zone, target_zone FROM edges_window "
        "WHERE window_start = ? AND actor_id = ? AND is_new_30d = TRUE "
        "AND target_zone IN ('SECRET', 'EXFIL_RISK')",
        [window_start, actor_id],
    ).fetchone()
    if row:
        return InvariantResult(
            "INV_010", True, 5,
            f"New edge {row[0]}->{row[1]} for actor {actor_id}",
        )
    return InvariantResult("INV_010", False, 0, "")


def check_invariants(
    db: duckdb.DuckDBPyConnection,
    window_start: datetime,
    actor_id: str,
    events: list[CanonicalEvent],
    known_initiators: set[str],
) -> list[InvariantResult]:
    """Run all 10 invariants for a (window, actor) pair."""
    return [
        _inv_001(events),
        _inv_002(events),
        _inv_003(events, known_initiators),
        _inv_004(events),
        _inv_005(db, window_start, actor_id, events),
        _inv_006(db, window_start, actor_id, events),
        _inv_007(events),
        _inv_008(db, window_start, actor_id, events),
        _inv_009(events),
        _inv_010(db, window_start, actor_id),
    ]


def compute_inv_score(results: list[InvariantResult]) -> tuple[float, str]:
    """Compute inv_score (max severity) and fired_invariants JSON."""
    fired = [r for r in results if r.fired]
    if not fired:
        return 0.0, "[]"
    score = max(r.severity for r in fired)
    fired_ids = sorted(r.id for r in fired)
    return float(score), json.dumps(fired_ids)
