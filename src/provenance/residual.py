"""Provenance residual risk computation.

Applies a provenance discount to fusion_raw based on pattern matching
and trigger chain resolution. The discount reduces residual_risk for
activity that is explained by sanctioned patterns.
"""

import json
from datetime import datetime

import duckdb

from config.settings import MurmurSettings
from src.provenance.patterns import compute_pattern_match, record_pattern_match
from src.provenance.trigger_chain import resolve_trigger_chain

# Boosted multiplier for WEAK provenance when trigger chain resolves
_WEAK_RESOLVED_MULTIPLIER = 0.8


def compute_residual_risk(
    db: duckdb.DuckDBPyConnection,
    window_start: datetime,
    actor_id: str,
    fusion_raw: float,
    known_initiators: set[str],
    settings: MurmurSettings,
    cached_patterns: list[dict] | None = None,
) -> float:
    """Compute residual_risk by applying provenance discount to fusion_raw.

    Updates actor_windows (pattern_match_score, matched_pattern_id,
    trigger_chain_resolved) and risk_scores (residual_risk).

    Formula:
        provenance_discount = pattern_match_score * effective_multiplier
        residual_risk = fusion_raw * (1 - trigger_penalty_weight * provenance_discount)

    Returns residual_risk.
    """
    # Read actor_windows for zone_sequence and event_count
    aw_row = db.execute(
        "SELECT zone_sequence, event_count FROM actor_windows "
        "WHERE window_start = ? AND actor_id = ?",
        [window_start, actor_id],
    ).fetchone()

    if not aw_row:
        return fusion_raw

    zone_sequence = json.loads(aw_row[0]) if aw_row[0] else []
    event_count = aw_row[1] or 0

    # Pattern matching (use cached_patterns to avoid N queries per scoring run)
    match_score, matched_pattern_id = compute_pattern_match(
        db, actor_id, zone_sequence, event_count, window_start,
        cached_patterns=cached_patterns,
    )

    # Record match idempotently (once per window per pattern)
    if matched_pattern_id and match_score > 0:
        record_pattern_match(db, matched_pattern_id, window_start)

    # Get dominant provenance_level and trigger_ref for this actor's events
    prov_row = db.execute(
        "SELECT provenance_level, trigger_ref FROM events "
        "WHERE window_start = ? AND actor_id = ? "
        "ORDER BY CASE provenance_level "
        "  WHEN 'STRONG' THEN 3 WHEN 'WEAK' THEN 2 ELSE 1 END DESC "
        "LIMIT 1",
        [window_start, actor_id],
    ).fetchone()

    provenance_level = prov_row[0] if prov_row else "NONE"
    trigger_ref = prov_row[1] if prov_row else None

    # Trigger chain resolution
    chain = resolve_trigger_chain(db, trigger_ref, known_initiators,
                                  max_depth=settings.trigger_chain_max_depth)

    # Determine effective multiplier
    base_multiplier = settings.discount_multipliers.get(provenance_level, 0.0)
    if provenance_level == "WEAK" and chain.resolved:
        effective_multiplier = _WEAK_RESOLVED_MULTIPLIER
    else:
        effective_multiplier = base_multiplier

    # Apply formula
    provenance_discount = match_score * effective_multiplier
    residual_risk = fusion_raw * (1 - settings.trigger_penalty_weight * provenance_discount)

    # Update actor_windows
    db.execute(
        "UPDATE actor_windows SET pattern_match_score = ?, "
        "matched_pattern_id = ?, trigger_chain_resolved = ? "
        "WHERE window_start = ? AND actor_id = ?",
        [match_score, matched_pattern_id, chain.resolved, window_start, actor_id],
    )

    # Update risk_scores
    db.execute(
        "UPDATE risk_scores SET residual_risk = ? "
        "WHERE window_start = ? AND actor_id = ?",
        [residual_risk, window_start, actor_id],
    )

    return residual_risk
