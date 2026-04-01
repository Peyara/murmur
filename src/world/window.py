"""World model windowing layer.

Groups events into 15-min windows per actor, computes activity aggregates
(burst rate, breadth entropy), and extracts zone transition edges.
"""

import json
import math
from collections import Counter
from datetime import datetime, timedelta
from itertools import groupby

import duckdb

_PROVENANCE_RANK = {"NONE": 0, "WEAK": 1, "STRONG": 2}
_PROVENANCE_BY_RANK = {v: k for k, v in _PROVENANCE_RANK.items()}


def shannon_entropy(counts: list[int]) -> float:
    """Shannon entropy in bits over a count distribution.

    Returns 0.0 for empty or single-element distributions.
    """
    total = sum(counts)
    if total == 0 or len(counts) <= 1:
        return 0.0
    h = 0.0
    for c in counts:
        if c > 0:
            p = c / total
            h -= p * math.log2(p)
    return h


def compute_actor_windows(db: duckdb.DuckDBPyConnection, window_start: datetime) -> int:
    """Compute actor_windows aggregates for a given 15-min window.

    Queries events, groups by actor, computes per-actor metrics,
    inserts into actor_windows. Returns number of rows inserted.
    """
    rows = db.execute(
        "SELECT actor_id, ts, action_type, target_id, target_zone, provenance_level "
        "FROM events WHERE window_start = ? ORDER BY actor_id, ts",
        [window_start],
    ).fetchall()

    if not rows:
        return 0

    inserted = 0
    for actor_id, group_iter in groupby(rows, key=lambda r: r[0]):
        events = list(group_iter)
        event_count = len(events)

        # Action types (sorted set)
        action_types = sorted(set(e[2] for e in events))

        # Zone sequence (ordered by ts)
        zone_sequence = [e[4] for e in events]

        # Target IDs (sorted set)
        target_ids = sorted(set(e[3] for e in events))

        # Burst per minute: events / actual span (1-min floor)
        timestamps = [e[1] for e in events]
        span_minutes = max(1.0, (timestamps[-1] - timestamps[0]).total_seconds() / 60.0)
        burst_per_min = event_count / span_minutes

        # Breadth entropy over target_id distribution
        target_counts = Counter(e[3] for e in events)
        breadth_entropy = shannon_entropy(list(target_counts.values()))

        # Strongest provenance level
        max_rank = max(_PROVENANCE_RANK.get(e[5], 0) for e in events)
        provenance_level = _PROVENANCE_BY_RANK[max_rank]

        db.execute(
            """
            INSERT INTO actor_windows (
                window_start, actor_id, event_count, action_types,
                zone_sequence, target_ids, burst_per_min, breadth_entropy,
                provenance_level
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (window_start, actor_id) DO UPDATE SET
                event_count = EXCLUDED.event_count,
                action_types = EXCLUDED.action_types,
                zone_sequence = EXCLUDED.zone_sequence,
                target_ids = EXCLUDED.target_ids,
                burst_per_min = EXCLUDED.burst_per_min,
                breadth_entropy = EXCLUDED.breadth_entropy,
                provenance_level = EXCLUDED.provenance_level
            """,
            [
                window_start,
                actor_id,
                event_count,
                json.dumps(action_types),
                json.dumps(zone_sequence),
                json.dumps(target_ids),
                burst_per_min,
                breadth_entropy,
                provenance_level,
            ],
        )
        inserted += 1

    return inserted


def compute_edges(db: duckdb.DuckDBPyConnection, window_start: datetime) -> int:
    """Extract zone transition edges for a given window.

    For each consecutive pair of events by the same actor (ordered by ts),
    records (source_zone, target_zone) as a transition edge. Computes
    is_new_30d at the zone-pair level.

    Returns number of edge rows inserted.
    """
    rows = db.execute(
        "SELECT actor_id, ts, target_zone, target_id "
        "FROM events WHERE window_start = ? ORDER BY actor_id, ts",
        [window_start],
    ).fetchall()

    if not rows:
        return 0

    # Aggregate edges: (actor_id, source_zone, target_zone, target_id) -> (count, first_ts)
    edge_agg: dict[tuple[str, str, str, str], tuple[int, datetime]] = {}

    for actor_id, group_iter in groupby(rows, key=lambda r: r[0]):
        events = list(group_iter)
        for i in range(1, len(events)):
            prev = events[i - 1]
            curr = events[i]
            key = (actor_id, prev[2], curr[2], curr[3])  # (actor, src_zone, tgt_zone, target_id)
            if key in edge_agg:
                count, first_ts = edge_agg[key]
                edge_agg[key] = (count + 1, min(first_ts, curr[1]))
            else:
                edge_agg[key] = (1, curr[1])

    if not edge_agg:
        return 0

    # Determine is_new_30d: check if (actor, source_zone, target_zone) exists
    # in edges_window within the past 30 days (excluding current window)
    lookback_start = window_start - timedelta(days=30)
    existing_pairs = set()
    historical = db.execute(
        "SELECT DISTINCT actor_id, source_zone, target_zone FROM edges_window "
        "WHERE window_start >= ? AND window_start < ?",
        [lookback_start, window_start],
    ).fetchall()
    for r in historical:
        existing_pairs.add((r[0], r[1], r[2]))

    inserted = 0
    for (actor_id, src_zone, tgt_zone, target_id), (count, first_ts) in edge_agg.items():
        is_new = (actor_id, src_zone, tgt_zone) not in existing_pairs

        db.execute(
            """
            INSERT INTO edges_window (
                window_start, actor_id, source_zone, target_zone,
                target_id, edge_count, first_seen, is_new_30d
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (window_start, actor_id, source_zone, target_zone, target_id)
            DO UPDATE SET
                edge_count = EXCLUDED.edge_count,
                first_seen = EXCLUDED.first_seen,
                is_new_30d = EXCLUDED.is_new_30d
            """,
            [window_start, actor_id, src_zone, tgt_zone, target_id, count, first_ts, is_new],
        )
        inserted += 1

    return inserted
