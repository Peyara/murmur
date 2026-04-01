"""Provenance pattern matching layer.

Manages sanctioned patterns (CRUD) and computes a 4-component match score
for actor activity against registered patterns. The match score feeds into
the residual risk discount.
"""

import json
import uuid
from datetime import datetime

import duckdb

from config.settings import SETTINGS


def register_pattern(
    db: duckdb.DuckDBPyConnection,
    name: str,
    description: str,
    initiator_type: str,
    expected_actors: list[str],
    expected_zones: list[str],
    expected_window: str | None,
    rate_min: float,
    rate_max: float,
    expected_duration: int,
    registered_by: str = "operator",
) -> str:
    """Register a sanctioned pattern. Returns the generated pattern_id."""
    pattern_id = f"pat-{uuid.uuid4().hex[:12]}"
    db.execute(
        """
        INSERT INTO sanctioned_patterns (
            pattern_id, name, description, initiator_type,
            expected_actors, expected_zones, expected_window,
            expected_rate_min, expected_rate_max, expected_duration,
            registered_by, registered_ts, active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, TRUE)
        """,
        [
            pattern_id, name, description, initiator_type,
            json.dumps(expected_actors), json.dumps(expected_zones),
            expected_window,
            rate_min, rate_max, expected_duration,
            registered_by, datetime.now(),
        ],
    )
    return pattern_id


def list_patterns(
    db: duckdb.DuckDBPyConnection, include_inactive: bool = False
) -> list[dict]:
    """List sanctioned patterns. Returns list of dicts."""
    query = "SELECT * FROM sanctioned_patterns"
    if not include_inactive:
        query += " WHERE active = TRUE"
    query += " ORDER BY registered_ts DESC"
    rows = db.execute(query).fetchall()
    cols = [desc[0] for desc in db.description]
    return [dict(zip(cols, row)) for row in rows]


def deactivate_pattern(db: duckdb.DuckDBPyConnection, pattern_id: str) -> bool:
    """Deactivate a pattern. Returns True if found and deactivated."""
    result = db.execute(
        "UPDATE sanctioned_patterns SET active = FALSE WHERE pattern_id = ? RETURNING pattern_id",
        [pattern_id],
    ).fetchone()
    return result is not None


def _match_actor(actor_id: str, expected_actors: list[str]) -> float:
    """Match actor against expected actors. Exact=1.0, same local-part=0.8, none=0.0."""
    if not expected_actors:
        return 1.0  # no constraint
    actor_local = actor_id.split("@")[0] if "@" in actor_id else actor_id
    for expected in expected_actors:
        if not expected:
            continue  # skip empty entries
        if actor_id == expected:
            return 1.0
        expected_local = expected.split("@")[0] if "@" in expected else expected
        if actor_local == expected_local:
            return 0.8
    return 0.0


def _lcs_length(a: list[str], b: list[str]) -> int:
    """Longest common subsequence length via dynamic programming."""
    if not a or not b:
        return 0
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[m][n]


def _match_zones(actual_zones: list[str], expected_zones: list[str]) -> float:
    """Match zone sequence using LCS ratio."""
    if not expected_zones:
        return 1.0  # no constraint
    if not actual_zones:
        return 0.0
    lcs_len = _lcs_length(actual_zones, expected_zones)
    max_len = max(len(actual_zones), len(expected_zones))
    return lcs_len / max_len if max_len > 0 else 0.0


def _match_time(window_ts: datetime, expected_window: str | None) -> float:
    """Match time against expected window (days_of_week + hour range)."""
    if expected_window is None:
        return 1.0  # no constraint
    window = json.loads(expected_window)
    day_of_week = window_ts.weekday()
    hour = window_ts.hour

    day_match = day_of_week in window.get("days_of_week", list(range(7)))
    hour_start = window.get("hour_start", 0)
    hour_end = window.get("hour_end", 24)
    hour_match = hour_start <= hour < hour_end

    if day_match and hour_match:
        return 1.0
    return 0.0


def _match_rate(event_count: int, rate_min: float, rate_max: float) -> float:
    """Match event rate against expected range. Within=1.0, outside=0.0."""
    if rate_min <= 0 and rate_max <= 0:
        return 1.0  # no constraint
    if rate_min <= event_count <= rate_max:
        return 1.0
    return 0.0


def compute_pattern_match(
    db: duckdb.DuckDBPyConnection,
    actor_id: str,
    zone_sequence: list[str],
    event_count: int,
    window_ts: datetime,
    cached_patterns: list[dict] | None = None,
) -> tuple[float, str | None]:
    """Compute best pattern match score for an actor's window activity.

    Pass cached_patterns to avoid re-querying on every call during batch scoring.
    Returns (pattern_match_score, matched_pattern_id). If no active patterns
    match, returns (0.0, None).
    """
    patterns = cached_patterns if cached_patterns is not None else list_patterns(db, include_inactive=False)
    if not patterns:
        return 0.0, None

    w_actor = SETTINGS.pattern_weight_actor
    w_zone = SETTINGS.pattern_weight_zone
    w_time = SETTINGS.pattern_weight_time
    w_rate = SETTINGS.pattern_weight_rate

    best_score = 0.0
    best_id = None

    for p in patterns:
        expected_actors = json.loads(p["expected_actors"]) if p["expected_actors"] else []
        expected_zones = json.loads(p["expected_zones"]) if p["expected_zones"] else []

        actor_score = _match_actor(actor_id, expected_actors)
        zone_score = _match_zones(zone_sequence, expected_zones)
        time_score = _match_time(window_ts, p["expected_window"])
        rate_score = _match_rate(event_count, p["expected_rate_min"], p["expected_rate_max"])

        composite = (
            w_actor * actor_score
            + w_zone * zone_score
            + w_time * time_score
            + w_rate * rate_score
        )

        if composite > best_score:
            best_score = composite
            best_id = p["pattern_id"]

    return best_score, best_id


def record_pattern_match(
    db: duckdb.DuckDBPyConnection,
    pattern_id: str,
    window_start: datetime,
) -> None:
    """Record a pattern match — idempotent per (pattern, window).

    Uses window_start to deduplicate: only increments match_count once
    per window even if called multiple times for the same window.
    """
    current = db.execute(
        "SELECT last_matched_ts FROM sanctioned_patterns WHERE pattern_id = ?",
        [pattern_id],
    ).fetchone()
    if current and current[0] == window_start:
        return  # already recorded for this window
    db.execute(
        "UPDATE sanctioned_patterns SET match_count = match_count + 1, "
        "last_matched_ts = ? WHERE pattern_id = ?",
        [window_start, pattern_id],
    )
