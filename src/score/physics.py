"""Scoring physics layer.

Computes delta_F (danger potential change): the difference between
current sigma_coarse and its EMA baseline. Positive delta_F means
increasing thermodynamic irreversibility (more suspicious).
"""

from datetime import datetime

import duckdb


def compute_delta_f(
    db: duckdb.DuckDBPyConnection,
    window_start: datetime,
    current_sigma: float,
    alpha: float = 0.1,
) -> float:
    """Compute danger potential change: current sigma - EMA(sigma).

    EMA is recomputed from zone_flux_windows history (no separate state table).
    Returns 0.0 for the first window (no baseline to compare against).
    """
    rows = db.execute(
        "SELECT sigma_coarse FROM zone_flux_windows "
        "WHERE window_start < ? ORDER BY window_start",
        [window_start],
    ).fetchall()

    if not rows:
        return 0.0

    # Compute EMA over historical sigmas
    ema = rows[0][0]
    for row in rows[1:]:
        ema = alpha * row[0] + (1 - alpha) * ema

    return current_sigma - ema
