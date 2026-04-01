"""Scoring physics layer.

Computes delta_F (danger potential change): the difference between
current sigma_coarse and its EMA baseline. Positive delta_F means
increasing thermodynamic irreversibility (more suspicious).
"""

from datetime import datetime, timedelta

import duckdb

# EMA with alpha=0.1 converges after ~30 values. 90 days of 15-min windows
# (~8,640 rows) is more than sufficient and prevents unbounded growth.
_EMA_LOOKBACK_DAYS = 90


def compute_delta_f(
    db: duckdb.DuckDBPyConnection,
    window_start: datetime,
    current_sigma: float,
    alpha: float = 0.1,
) -> float:
    """Compute danger potential change: current sigma - EMA(sigma).

    EMA is recomputed from zone_flux_windows history (bounded to 90 days).
    Returns 0.0 for the first window (no baseline to compare against).
    """
    lookback = window_start - timedelta(days=_EMA_LOOKBACK_DAYS)
    rows = db.execute(
        "SELECT sigma_coarse FROM zone_flux_windows "
        "WHERE window_start >= ? AND window_start < ? ORDER BY window_start",
        [lookback, window_start],
    ).fetchall()

    if not rows:
        return 0.0

    # Compute EMA over historical sigmas
    ema = rows[0][0]
    for row in rows[1:]:
        ema = alpha * row[0] + (1 - alpha) * ema

    return current_sigma - ema
