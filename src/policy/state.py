"""Policy state dataclass — the output of risk energy computation."""

from dataclasses import dataclass


@dataclass
class PolicyState:
    alert_level: str         # ALERT_HIGH | ALERT_MED | WATCH | NORMAL
    risk_energy: float       # scalar risk score
    fusion_raw: float
    residual_risk: float
    closure_ratio: float
    orphaned_privilege: float
