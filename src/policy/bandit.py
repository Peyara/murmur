"""Shadow bandit — suggests actions but NEVER executes them.

Logs suggestions to policy_suggestions table for human review.
This is observation-only: the bandit learns what it would recommend,
building a dataset for future RL optimization.
"""

import uuid
from datetime import datetime

import duckdb

from src.policy.state import PolicyState

# Action mapping by alert level
_ACTION_MAP = {
    "ALERT_HIGH": "ISOLATE_ACTOR",
    "ALERT_MED": "REQUEST_REVIEW",
    "WATCH": "INCREASE_MONITORING",
}


def suggest_action(state: PolicyState) -> str | None:
    """Suggest an action based on policy state. Returns None for NORMAL."""
    return _ACTION_MAP.get(state.alert_level)


def log_suggestion(
    db: duckdb.DuckDBPyConnection,
    window_start: datetime,
    actor_id: str,
    state: PolicyState,
    action: str,
) -> None:
    """Log a shadow suggestion to the DB. Never executes the action."""
    db.execute(
        """
        INSERT INTO policy_suggestions (
            suggestion_id, window_start, actor_id, risk_energy,
            alert_level, suggested_action, explanation, created_ts
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            str(uuid.uuid4()),
            window_start,
            actor_id,
            state.risk_energy,
            state.alert_level,
            action,
            f"fusion={state.fusion_raw:.3f} residual={state.residual_risk:.3f} "
            f"closure={state.closure_ratio:.2f} orphaned={state.orphaned_privilege:.1f}",
            datetime.now(tz=None),
        ],
    )
