"""Scoring fusion layer.

Combines all Phase 1 scoring signals into a single fusion_raw score.
Each signal is normalized to [0, 1] and weighted. The result is written
to risk_scores. residual_risk = fusion_raw for now (provenance discount
comes in Session E).
"""

from datetime import datetime

import duckdb

from src.schema import CanonicalEvent
from src.score.invariants import check_invariants, compute_inv_score
from src.score.novelty import compute_novelty_score, get_bridge_new
from src.score.physics import compute_delta_f

# Initial weights (calibrate in Sprint 1B)
FUSION_WEIGHTS = {
    "inv_score": 0.35,
    "novelty_score": 0.20,
    "sigma_coarse": 0.10,
    "bridge_new": 0.10,
    "delta_f": 0.10,
    "burst_per_min": 0.08,
    "breadth_entropy": 0.07,
}

# Normalization bounds (empirical, refined in Sprint 1B)
NORM_BOUNDS = {
    "inv_score": 5.0,
    "sigma_coarse": 10.0,
    "novelty_score": 10.0,
    "bridge_new": 5.0,
    "delta_f": 5.0,
    "burst_per_min": 20.0,
    "breadth_entropy": 4.0,
}


def normalize(value: float, max_bound: float) -> float:
    """Normalize a value to [0, 1] range. Clips at both ends."""
    if max_bound <= 0:
        return 0.0
    return max(0.0, min(value / max_bound, 1.0))


def compute_fusion(
    db: duckdb.DuckDBPyConnection,
    window_start: datetime,
    actor_id: str,
    known_initiators: set[str],
) -> float:
    """Orchestrate all scoring signals and insert into risk_scores.

    Returns fusion_raw score.
    """
    # Read actor_windows for burst and entropy
    aw_row = db.execute(
        "SELECT burst_per_min, breadth_entropy FROM actor_windows "
        "WHERE window_start = ? AND actor_id = ?",
        [window_start, actor_id],
    ).fetchone()
    burst_per_min = aw_row[0] if aw_row else 0.0
    breadth_entropy = aw_row[1] if aw_row else 0.0

    # Read zone_flux_windows for sigma_coarse
    zf_row = db.execute(
        "SELECT sigma_coarse, bridge_count FROM zone_flux_windows "
        "WHERE window_start = ?",
        [window_start],
    ).fetchone()
    sigma_coarse = zf_row[0] if zf_row else 0.0
    bridge_new = zf_row[1] if zf_row else 0

    # Get events for invariant checks
    event_rows = db.execute(
        "SELECT event_id, ts, window_start, actor_id, actor_type, "
        "action_type, target_id, target_type, target_zone, result, "
        "trigger_ref, provenance_level, provenance_source, "
        "correlation_confidence, delegation_chain, project_id, env, "
        "is_deploy, is_incident, is_infrastructure, risk_tags, raw_ref, "
        "coverage_flag "
        "FROM events WHERE window_start = ? AND actor_id = ?",
        [window_start, actor_id],
    ).fetchall()

    events = [
        CanonicalEvent(*row) for row in event_rows
    ]

    # Invariants
    inv_results = check_invariants(db, window_start, actor_id, events, known_initiators)
    inv_score, fired_json = compute_inv_score(inv_results)

    # Physics: delta_F
    delta_f = compute_delta_f(db, window_start, sigma_coarse)

    # Novelty
    novelty_score = compute_novelty_score(db, window_start, actor_id)

    # Normalize all signals
    signals = {
        "inv_score": normalize(inv_score, NORM_BOUNDS["inv_score"]),
        "sigma_coarse": normalize(sigma_coarse, NORM_BOUNDS["sigma_coarse"]),
        "novelty_score": normalize(novelty_score, NORM_BOUNDS["novelty_score"]),
        "bridge_new": normalize(float(bridge_new), NORM_BOUNDS["bridge_new"]),
        "delta_f": normalize(delta_f, NORM_BOUNDS["delta_f"]),
        "burst_per_min": normalize(burst_per_min, NORM_BOUNDS["burst_per_min"]),
        "breadth_entropy": normalize(breadth_entropy, NORM_BOUNDS["breadth_entropy"]),
    }

    # Weighted sum
    fusion_raw = sum(
        FUSION_WEIGHTS[k] * signals[k] for k in FUSION_WEIGHTS
    )

    # Write to risk_scores (residual_risk = fusion_raw for now)
    explanation = "; ".join(
        r.explanation for r in inv_results if r.fired
    ) or "no invariants fired"

    db.execute(
        """
        INSERT INTO risk_scores (
            window_start, actor_id, inv_score, sigma_coarse, novelty_score,
            bridge_new, delta_f, burst_per_min, breadth_entropy,
            closure_ratio, orphaned_privilege, fusion_raw, residual_risk,
            fired_invariants, explanation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (window_start, actor_id) DO UPDATE SET
            inv_score = EXCLUDED.inv_score,
            sigma_coarse = EXCLUDED.sigma_coarse,
            novelty_score = EXCLUDED.novelty_score,
            bridge_new = EXCLUDED.bridge_new,
            delta_f = EXCLUDED.delta_f,
            burst_per_min = EXCLUDED.burst_per_min,
            breadth_entropy = EXCLUDED.breadth_entropy,
            fusion_raw = EXCLUDED.fusion_raw,
            residual_risk = EXCLUDED.residual_risk,
            fired_invariants = EXCLUDED.fired_invariants,
            explanation = EXCLUDED.explanation
        """,
        [
            window_start, actor_id,
            inv_score, sigma_coarse, novelty_score,
            bridge_new, delta_f, burst_per_min, breadth_entropy,
            0.0,  # closure_ratio (Session E)
            0.0,  # orphaned_privilege (Session E)
            fusion_raw, fusion_raw,  # residual_risk = fusion_raw
            fired_json, explanation,
        ],
    )

    return fusion_raw
