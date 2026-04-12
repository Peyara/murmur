"""Risk energy function — combines fusion, provenance, and closure into a single score.

risk_energy = residual_risk * 10 * closure_penalty
where closure_penalty amplifies risk when closure is poor.

Thresholds:
  > 8.0 → ALERT_HIGH
  > 5.0 → ALERT_MED
  > 3.0 → WATCH
  <= 3.0 → NORMAL
"""

from src.policy.state import PolicyState


def risk_energy(
    fusion_raw: float,
    residual_risk: float,
    closure_ratio: float,
    orphaned_privilege: float,
) -> PolicyState:
    """Compute risk energy and alert level.

    The energy is driven primarily by residual_risk (which already includes
    provenance discounting). Closure modulates it:
    - closure_ratio near 1.0 → no amplification
    - closure_ratio near 0.0 → up to 1.5x amplification
    - orphaned_privilege adds directly (scaled)
    """
    # Closure penalty: ranges from 1.0 (clean) to 1.5 (all open)
    closure_penalty = 1.0 + 0.5 * (1.0 - closure_ratio)

    # Orphaned contribution (scaled down to comparable range)
    orphaned_contrib = orphaned_privilege / 10.0

    # Risk energy: base 10x residual_risk, amplified by closure, plus orphaned
    energy = residual_risk * 10.0 * closure_penalty + orphaned_contrib

    # Classify
    if energy > 8.0:
        level = "ALERT_HIGH"
    elif energy > 5.0:
        level = "ALERT_MED"
    elif energy > 3.0:
        level = "WATCH"
    else:
        level = "NORMAL"

    return PolicyState(
        alert_level=level,
        risk_energy=energy,
        fusion_raw=fusion_raw,
        residual_risk=residual_risk,
        closure_ratio=closure_ratio,
        orphaned_privilege=orphaned_privilege,
    )
