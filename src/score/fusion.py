"""Scoring fusion layer.

Combines all Phase 1 scoring signals into a single fusion_raw score.
Each signal is normalized to [0, 1] and weighted. The result is written
to risk_scores. residual_risk = fusion_raw for now (provenance discount
comes in Session E).
"""

import math
from datetime import datetime

import duckdb

from src.schema import CanonicalEvent
from src.score.closure import compute_closure_signals
from src.score.invariants import check_invariants, compute_inv_score
from src.score.novelty import compute_novelty_score
from src.score.physics import compute_delta_f

# Calibrated weights (Sprint 3: added closure signals, rebalanced)
# burst_per_min: 0.9x discrimination — dropped
# breadth_entropy: r=-0.37 — dropped
# closure_gap + orphaned_priv: 0.15 total from proportional reduction of existing
FUSION_WEIGHTS = {
    "inv_score": 0.17,
    "inv_count": 0.13,
    "novelty_score": 0.30,
    "sigma_coarse": 0.04,
    "bridge_new": 0.13,
    "delta_f": 0.08,
    "closure_gap": 0.10,
    "orphaned_priv": 0.05,
    "burst_per_min": 0.00,
    "breadth_entropy": 0.00,
}

# Normalization bounds (empirical, refined in Sprint 1B + Sprint 3)
NORM_BOUNDS = {
    "inv_score": 5.0,
    "inv_count": 10.0,
    "novelty_score": 10.0,
    "bridge_new": 5.0,
    "delta_f": 5.0,
    "orphaned_priv": 50.0,  # SA_KEY(5) * 10 overdue = max plausible with long-lived watches
    "burst_per_min": 20.0,
    "breadth_entropy": 4.0,
}

# Sigmoid parameters for sigma_coarse (always > 0, ramps under adversarial load)
SIGMA_SIGMOID_K = 1.0   # steepness
SIGMA_SIGMOID_X0 = 3.0  # midpoint (output = 0.5 when sigma = 3.0)


def normalize(value: float, max_bound: float) -> float:
    """Normalize a value to [0, 1] range. Clips at both ends."""
    if max_bound <= 0:
        return 0.0
    return max(0.0, min(value / max_bound, 1.0))


def sigmoid_normalize(value: float, k: float = SIGMA_SIGMOID_K, x0: float = SIGMA_SIGMOID_X0) -> float:
    """Sigmoid normalization to (0, 1). Never zero — always a baseline hum."""
    exponent = max(-500.0, min(500.0, -k * (value - x0)))
    return 1.0 / (1.0 + math.exp(exponent))


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
    # Column order must match CanonicalEvent dataclass field order exactly.
    # If CanonicalEvent fields change, update this query to match.
    _EVENT_COLS = (
        "event_id, ts, window_start, actor_id, actor_type, "
        "action_type, target_id, target_type, target_zone, result, "
        "actor_subtype, orchestrator_id, "
        "trigger_ref, provenance_level, provenance_source, "
        "action_subtype, tool_name, tool_parameters_hash, model_id, "
        "correlation_confidence, delegation_chain, project_id, env, "
        "is_deploy, is_incident, is_infrastructure, risk_tags, raw_ref, "
        "coverage_flag"
    )
    event_rows = db.execute(
        f"SELECT {_EVENT_COLS} FROM events WHERE window_start = ? AND actor_id = ?",  # noqa: S608  # nosec B608 — constant column list
        [window_start, actor_id],
    ).fetchall()

    events = [CanonicalEvent(*row) for row in event_rows]

    # Invariants
    inv_results = check_invariants(db, window_start, actor_id, events, known_initiators)
    inv_score, inv_count, fired_json = compute_inv_score(inv_results)

    # Physics: delta_F
    delta_f = compute_delta_f(db, window_start, sigma_coarse)

    # Novelty
    novelty_score = compute_novelty_score(db, window_start, actor_id)

    # Closure signals
    closure = compute_closure_signals(db, window_start, actor_id)
    closure_gap = 1.0 - closure.closure_ratio  # invert: high ratio = low risk

    # Normalize all signals
    signals = {
        "inv_score": normalize(inv_score, NORM_BOUNDS["inv_score"]),
        "inv_count": normalize(float(inv_count), NORM_BOUNDS["inv_count"]),
        "sigma_coarse": sigmoid_normalize(sigma_coarse),
        "novelty_score": normalize(novelty_score, NORM_BOUNDS["novelty_score"]),
        "bridge_new": normalize(float(bridge_new), NORM_BOUNDS["bridge_new"]),
        "delta_f": normalize(delta_f, NORM_BOUNDS["delta_f"]),
        "closure_gap": closure_gap,  # already [0, 1]
        "orphaned_priv": normalize(closure.orphaned_privilege, NORM_BOUNDS["orphaned_priv"]),
        "burst_per_min": normalize(burst_per_min, NORM_BOUNDS["burst_per_min"]),
        "breadth_entropy": normalize(breadth_entropy, NORM_BOUNDS["breadth_entropy"]),
    }

    # Weighted sum
    fusion_raw = sum(
        FUSION_WEIGHTS[k] * signals[k] for k in FUSION_WEIGHTS
    )

    # Write to risk_scores (residual_risk = fusion_raw for now)
    inv_explanation = "; ".join(
        r.explanation for r in inv_results if r.fired
    ) or "no invariants fired"
    explanation = inv_explanation
    if closure.explanation != "no closure watches":
        explanation = f"{inv_explanation}; {closure.explanation}"

    db.execute(
        """
        INSERT INTO risk_scores (
            window_start, actor_id, inv_score, inv_count, sigma_coarse,
            novelty_score, bridge_new, delta_f, burst_per_min, breadth_entropy,
            closure_ratio, orphaned_privilege, fusion_raw, residual_risk,
            fired_invariants, explanation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (window_start, actor_id) DO UPDATE SET
            inv_score = EXCLUDED.inv_score,
            inv_count = EXCLUDED.inv_count,
            sigma_coarse = EXCLUDED.sigma_coarse,
            novelty_score = EXCLUDED.novelty_score,
            bridge_new = EXCLUDED.bridge_new,
            delta_f = EXCLUDED.delta_f,
            burst_per_min = EXCLUDED.burst_per_min,
            breadth_entropy = EXCLUDED.breadth_entropy,
            closure_ratio = EXCLUDED.closure_ratio,
            orphaned_privilege = EXCLUDED.orphaned_privilege,
            fusion_raw = EXCLUDED.fusion_raw,
            residual_risk = EXCLUDED.residual_risk,
            fired_invariants = EXCLUDED.fired_invariants,
            explanation = EXCLUDED.explanation
        """,
        [
            window_start, actor_id,
            inv_score, float(inv_count), sigma_coarse, novelty_score,
            bridge_new, delta_f, burst_per_min, breadth_entropy,
            closure.closure_ratio,
            closure.orphaned_privilege,
            fusion_raw, fusion_raw,  # residual_risk = fusion_raw
            fired_json, explanation,
        ],
    )

    return fusion_raw
