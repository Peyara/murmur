"""World model zone flux graph layer.

Builds a 6x6 zone flux matrix per window from edge data, computes
Schnakenberg entropy production (sigma_coarse) with tiered confidence,
and detects new cross-zone bridges.
"""

import json
import math
from datetime import datetime

import duckdb

from src.schema import TargetZone

# Deterministic zone ordering for matrix indices
ZONE_ORDER = [
    TargetZone.CONTROL,
    TargetZone.IDENTITY,
    TargetZone.SECRET,
    TargetZone.DATA,
    TargetZone.COMPUTE,
    TargetZone.EXFIL_RISK,
]
ZONE_COUNT = len(ZONE_ORDER)
_ZONE_INDEX = {z.value: i for i, z in enumerate(ZONE_ORDER)}

# Tiered confidence thresholds
_COLD_THRESHOLD = 5
_WARM_THRESHOLD = 50


def schnakenberg_entropy(
    flux: list[list[float]],
    obs_counts: dict[tuple[int, int], int],
) -> float:
    """Schnakenberg entropy production on a flux matrix with tiered confidence.

    sigma = sum_{i<j} weight * (J_ij - J_ji) * ln(J_ij / J_ji)

    Pairs with zero in either direction are skipped (no ln(0)).
    Tier weighting:
      - Cold (<5 cumulative observations): skip (weight=0)
      - Warm (5-50): weight=0.5
      - Calibrated (>50): weight=1.0
      - No obs data (empty dict): all pairs treated as calibrated
    """
    sigma = 0.0
    has_obs = len(obs_counts) > 0

    for i in range(ZONE_COUNT):
        for j in range(i + 1, ZONE_COUNT):
            j_ij = flux[i][j]
            j_ji = flux[j][i]
            if j_ij == 0 or j_ji == 0:
                continue

            if has_obs:
                pair_key = (i, j)
                obs = obs_counts.get(pair_key, 0)
                if obs < _COLD_THRESHOLD:
                    continue
                weight = 0.5 if obs < _WARM_THRESHOLD else 1.0
            else:
                weight = 1.0

            sigma += weight * (j_ij - j_ji) * math.log(j_ij / j_ji)

    return sigma


def build_flux_matrix(db: duckdb.DuckDBPyConnection, window_start: datetime) -> list[list[float]]:
    """Build 6x6 zone flux matrix from edges_window for a given window."""
    matrix = [[0.0] * ZONE_COUNT for _ in range(ZONE_COUNT)]

    rows = db.execute(
        "SELECT source_zone, target_zone, SUM(edge_count) "
        "FROM edges_window WHERE window_start = ? "
        "GROUP BY source_zone, target_zone",
        [window_start],
    ).fetchall()

    for src, tgt, total in rows:
        i = _ZONE_INDEX.get(src)
        j = _ZONE_INDEX.get(tgt)
        if i is not None and j is not None:
            matrix[i][j] = float(total)

    return matrix


def _get_cumulative_obs_counts(
    db: duckdb.DuckDBPyConnection, window_start: datetime
) -> dict[tuple[int, int], int]:
    """Get cumulative observation counts per zone pair up to and including this window."""
    rows = db.execute(
        "SELECT source_zone, target_zone, SUM(edge_count) "
        "FROM edges_window WHERE window_start <= ? "
        "GROUP BY source_zone, target_zone",
        [window_start],
    ).fetchall()

    obs: dict[tuple[int, int], int] = {}
    for src, tgt, total in rows:
        i = _ZONE_INDEX.get(src)
        j = _ZONE_INDEX.get(tgt)
        if i is not None and j is not None:
            # Normalize to (min, max) pair key for symmetric lookup
            pair_key = (min(i, j), max(i, j))
            obs[pair_key] = obs.get(pair_key, 0) + int(total)

    return obs


def _count_bridges(db: duckdb.DuckDBPyConnection, window_start: datetime) -> int:
    """Count new cross-zone edges (is_new_30d AND source != target zone)."""
    row = db.execute(
        "SELECT COUNT(DISTINCT (source_zone || '_' || target_zone)) "
        "FROM edges_window "
        "WHERE window_start = ? AND is_new_30d = TRUE AND source_zone != target_zone",
        [window_start],
    ).fetchone()
    return row[0] if row else 0


def compute_zone_flux(db: duckdb.DuckDBPyConnection, window_start: datetime) -> dict:
    """Build zone flux matrix, compute sigma_coarse, insert into zone_flux_windows.

    Returns dict with flux_matrix, net_currents, sigma_coarse, bridge_count.
    """
    matrix = build_flux_matrix(db, window_start)
    obs_counts = _get_cumulative_obs_counts(db, window_start)
    sigma = schnakenberg_entropy(matrix, obs_counts)
    bridge_count = _count_bridges(db, window_start)

    # Net currents for each (i,j) pair where i<j
    net_currents: dict[str, float] = {}
    for i in range(ZONE_COUNT):
        for j in range(i + 1, ZONE_COUNT):
            net = matrix[i][j] - matrix[j][i]
            if net != 0:
                net_currents[f"{i}_{j}"] = net

    db.execute(
        """
        INSERT INTO zone_flux_windows (
            window_start, flux_matrix, net_currents, sigma_coarse, bridge_count
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (window_start) DO UPDATE SET
            flux_matrix = EXCLUDED.flux_matrix,
            net_currents = EXCLUDED.net_currents,
            sigma_coarse = EXCLUDED.sigma_coarse,
            bridge_count = EXCLUDED.bridge_count
        """,
        [
            window_start,
            json.dumps(matrix),
            json.dumps(net_currents),
            sigma,
            bridge_count,
        ],
    )

    return {
        "flux_matrix": matrix,
        "net_currents": net_currents,
        "sigma_coarse": sigma,
        "bridge_count": bridge_count,
    }
