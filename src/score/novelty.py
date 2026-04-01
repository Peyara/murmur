"""Scoring novelty layer.

Computes novelty_score from zone-weighted new edges and bridge_new count.
"""

from datetime import datetime

import duckdb

from src.schema import TargetZone

ZONE_WEIGHTS = {
    TargetZone.SECRET.value: 2.0,
    TargetZone.EXFIL_RISK.value: 2.0,
    TargetZone.IDENTITY.value: 1.5,
    TargetZone.CONTROL.value: 1.5,
    TargetZone.DATA.value: 1.0,
    TargetZone.COMPUTE.value: 1.0,
}


def compute_novelty_score(
    db: duckdb.DuckDBPyConnection,
    window_start: datetime,
    actor_id: str,
) -> float:
    """Weighted sum of new edges (is_new_30d) for this actor in this window.

    Weight is determined by the target_zone of the edge:
      SECRET/EXFIL_RISK = 2.0, IDENTITY/CONTROL = 1.5, DATA/COMPUTE = 1.0.
    """
    rows = db.execute(
        "SELECT target_zone FROM edges_window "
        "WHERE window_start = ? AND actor_id = ? AND is_new_30d = TRUE",
        [window_start, actor_id],
    ).fetchall()

    return sum(ZONE_WEIGHTS.get(r[0], 1.0) for r in rows)


def get_bridge_new(db: duckdb.DuckDBPyConnection, window_start: datetime) -> int:
    """Return bridge_count from zone_flux_windows for this window."""
    row = db.execute(
        "SELECT bridge_count FROM zone_flux_windows WHERE window_start = ?",
        [window_start],
    ).fetchone()
    return row[0] if row else 0
