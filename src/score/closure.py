"""Closure system — resource state tracking, settlement detection, and scoring.

Platform-agnostic engine. All platform-specific knowledge lives in ClosureConfig,
which is provided by the caller (typically from MurmurSettings). The engine
operates on CanonicalEvent abstractions (TargetZone, ActionType).

Three layers:
1. Explicit pairs (seeded, high confidence): configured per platform
2. Temporal closure (clock-based): configured TTLs per action type
3. Resource-state settlement (auto-discovered): learns from observed data

Failsafe invariant: unknown = open. Discovery can only close, never open.
"""

import json as _json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

import duckdb

from src.schema import CanonicalEvent

# ---------------------------------------------------------------------------
# Configuration — platform-specific knowledge lives here
# ---------------------------------------------------------------------------

@dataclass
class ClosureConfig:
    """Platform-specific closure knowledge. The engine is generic; this is the plug.

    To add a new platform (AWS, Azure, etc.):
    1. Define a new ClosureConfig with that platform's pairs, TTLs, etc.
    2. Set it on MurmurSettings.closure
    3. The engine, discovery, and scoring work unchanged.
    """
    seeded_pairs: list[dict] = field(default_factory=list)
    temporal_ttl: dict[str, int] = field(default_factory=dict)
    opening_types: set[str] = field(default_factory=set)
    action_to_resource_type: dict[str, str] = field(default_factory=dict)
    sensitivity: dict[str, float] = field(default_factory=lambda: {"UNKNOWN": 3.0})
    settlement_hours: dict[str, int] = field(default_factory=lambda: {"UNKNOWN": 4})
    never_settle_types: set[str] = field(default_factory=set)
    failsafe_zones: set[str] = field(default_factory=lambda: {"IDENTITY", "CONTROL"})


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class ClosureResult:
    closure_ratio: float       # [0, 1] — fraction of watches that are closed
    orphaned_privilege: float  # >= 0 — weighted overdue score
    explanation: str
    open_watches: int
    closed_watches: int


# ---------------------------------------------------------------------------
# Seed pairs
# ---------------------------------------------------------------------------

def seed_pairs(db: duckdb.DuckDBPyConnection, config: ClosureConfig | None = None) -> int:
    """Insert seeded opening-closing pairs. Idempotent (ON CONFLICT ignore)."""
    if config is None:
        config = _default_config()
    count = 0
    for pair in config.seeded_pairs:
        pair_id = pair.get("pair_id", f"seed-{pair['opening_action_type']}-{pair['closing_action_type']}")
        db.execute(
            """
            INSERT INTO opening_closing_pairs (pair_id, opening_action_type, closing_action_type, window_hours, tier)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (pair_id) DO NOTHING
            """,
            [pair_id, str(pair["opening_action_type"]), str(pair["closing_action_type"]),
             pair["window_hours"], pair.get("tier", 1)],
        )
        count += 1
    return count


# ---------------------------------------------------------------------------
# Watch creation
# ---------------------------------------------------------------------------

def _is_opening(event: CanonicalEvent, db: duckdb.DuckDBPyConnection, config: ClosureConfig) -> bool:
    """Determine if an event should open a closure watch."""
    action_str = str(event.action_type)
    # Known opening types (from config)
    if action_str in config.opening_types:
        return True
    # Discovered pairs (check DB for opening_action_type matches)
    row = db.execute(
        "SELECT 1 FROM opening_closing_pairs WHERE opening_action_type = ? LIMIT 1",
        [action_str],
    ).fetchone()
    if row:
        return True
    # Failsafe: unknown action in configured sensitive zones → opening
    if str(event.target_zone) in config.failsafe_zones:
        return True
    return False


def _infer_resource_type(event: CanonicalEvent, config: ClosureConfig) -> str:
    """Infer resource type from action type."""
    return config.action_to_resource_type.get(str(event.action_type), "UNKNOWN")


def _get_expected_close_type(event: CanonicalEvent, db: duckdb.DuckDBPyConnection, config: ClosureConfig) -> str:
    """Determine expected closing action type for this opening."""
    action_str = str(event.action_type)
    # Check explicit pairs first
    row = db.execute(
        "SELECT closing_action_type FROM opening_closing_pairs WHERE opening_action_type = ? LIMIT 1",
        [action_str],
    ).fetchone()
    if row:
        return row[0]
    # Temporal types
    if action_str in config.temporal_ttl:
        return "TEMPORAL_EXPIRY"
    # Default: settlement-based
    return "SETTLEMENT"


def _get_window_hours(event: CanonicalEvent, db: duckdb.DuckDBPyConnection, config: ClosureConfig) -> int:
    """Get expected closure window from pairs table or defaults."""
    action_str = str(event.action_type)
    row = db.execute(
        "SELECT window_hours FROM opening_closing_pairs WHERE opening_action_type = ? LIMIT 1",
        [action_str],
    ).fetchone()
    if row:
        return row[0]
    # Temporal
    if action_str in config.temporal_ttl:
        return config.temporal_ttl[action_str]
    # Default based on resource type
    resource_type = _infer_resource_type(event, config)
    return config.settlement_hours.get(resource_type, 24)


def create_watch(
    db: duckdb.DuckDBPyConnection, event: CanonicalEvent, config: ClosureConfig | None = None,
) -> str | None:
    """Create a closure watch for a privileged opening event.

    Returns resource_id if watch created, None if skipped.
    Idempotent: existing watch on same resource_id is not duplicated.
    """
    if config is None:
        config = _default_config()
    if not _is_opening(event, db, config):
        return None

    resource_type = _infer_resource_type(event, config)
    sensitivity = config.sensitivity.get(resource_type, config.sensitivity.get("UNKNOWN", 3.0))
    expected_close = _get_expected_close_type(event, db, config)
    window_hours = _get_window_hours(event, db, config)

    db.execute(
        """
        INSERT INTO closure_state (
            resource_id, resource_type, opening_event_id, opening_ts,
            opening_actor_id, expected_close_type, window_hours,
            is_closed, sensitivity
        ) VALUES (?, ?, ?, ?, ?, ?, ?, FALSE, ?)
        ON CONFLICT (resource_id) DO NOTHING
        """,
        [event.target_id, resource_type, event.event_id, event.ts,
         event.actor_id, expected_close, window_hours, sensitivity],
    )
    return event.target_id


# ---------------------------------------------------------------------------
# Close watch
# ---------------------------------------------------------------------------

def try_close_watch(db: duckdb.DuckDBPyConnection, event: CanonicalEvent) -> bool:
    """Try to close an existing watch with this event.

    Checks: is there an open watch on this target_id whose expected_close_type
    matches this event's action_type?
    """
    action_str = str(event.action_type)

    # Check for open watch on this resource with matching expected close type
    row = db.execute(
        """
        SELECT resource_id FROM closure_state
        WHERE resource_id = ? AND is_closed = FALSE AND expected_close_type = ?
        """,
        [event.target_id, action_str],
    ).fetchone()

    if row:
        db.execute(
            """
            UPDATE closure_state
            SET is_closed = TRUE, closing_event_id = ?, closing_ts = ?
            WHERE resource_id = ?
            """,
            [event.event_id, event.ts, event.target_id],
        )
        return True

    # Also check discovered pairs: event action_type is a known closing_action_type
    # for ANY open watch on this resource
    pair_row = db.execute(
        """
        SELECT cs.resource_id
        FROM closure_state cs
        JOIN opening_closing_pairs ocp ON cs.expected_close_type = ocp.closing_action_type
        WHERE cs.resource_id = ? AND cs.is_closed = FALSE
        LIMIT 1
        """,
        [event.target_id],
    ).fetchone()

    if not pair_row:
        # Direct match: check if there's any open watch on this resource
        # and the event's action is listed as a closing_action_type for that opening
        pair_row2 = db.execute(
            """
            SELECT cs.resource_id
            FROM closure_state cs
            JOIN opening_closing_pairs ocp
              ON ocp.opening_action_type = (
                SELECT action_type FROM events WHERE event_id = cs.opening_event_id
              )
              AND ocp.closing_action_type = ?
            WHERE cs.resource_id = ? AND cs.is_closed = FALSE
            LIMIT 1
            """,
            [action_str, event.target_id],
        ).fetchone()
        if pair_row2:
            db.execute(
                """
                UPDATE closure_state
                SET is_closed = TRUE, closing_event_id = ?, closing_ts = ?
                WHERE resource_id = ?
                """,
                [event.event_id, event.ts, event.target_id],
            )
            return True

    return False


# ---------------------------------------------------------------------------
# Temporal expiry
# ---------------------------------------------------------------------------

def check_temporal_expiry(db: duckdb.DuckDBPyConnection, current_ts: datetime) -> int:
    """Auto-close watches whose temporal TTL has expired.

    Only applies to TEMPORAL_EXPIRY type. Explicit pairs do NOT auto-close.
    Returns count of watches closed.
    """
    # Count eligible watches before update to compute delta
    before = db.execute(
        """
        SELECT count(*) FROM closure_state
        WHERE is_closed = FALSE
          AND expected_close_type = 'TEMPORAL_EXPIRY'
          AND opening_ts + INTERVAL (window_hours) HOUR <= ?
        """,
        [current_ts],
    ).fetchone()[0]

    if before > 0:
        db.execute(
            """
            UPDATE closure_state
            SET is_closed = TRUE, closing_ts = ?
            WHERE is_closed = FALSE
              AND expected_close_type = 'TEMPORAL_EXPIRY'
              AND opening_ts + INTERVAL (window_hours) HOUR <= ?
            """,
            [current_ts, current_ts],
        )
    return before


# ---------------------------------------------------------------------------
# Settlement detection
# ---------------------------------------------------------------------------

def _detect_settlement(
    db: duckdb.DuckDBPyConnection,
    resource_id: str,
    opening_ts: datetime,
    current_ts: datetime,
    settlement_hours: int = 4,
) -> float:
    """Return settlement confidence [0.0, 1.0].

    0.0 = still active or insufficient data
    >0.0 = evidence of settlement (resource went quiet)
    """
    hours_elapsed = (current_ts - opening_ts).total_seconds() / 3600

    # Too early to assess
    if hours_elapsed < settlement_hours:
        return 0.0

    # Check for post-opening activity on this resource
    post_events = db.execute(
        "SELECT ts FROM events WHERE target_id = ? AND ts > ? AND ts <= ? ORDER BY ts DESC LIMIT 1",
        [resource_id, opening_ts, current_ts],
    ).fetchall()

    if not post_events:
        # No activity since opening, enough time passed
        return 0.6  # moderate confidence

    # Check gap since last activity
    last_activity = post_events[0][0]
    gap_hours = (current_ts - last_activity).total_seconds() / 3600

    if gap_hours >= settlement_hours:
        # Was active, then went quiet
        return min(1.0, 0.5 + 0.1 * (gap_hours / settlement_hours))

    # Still active
    return 0.0


# ---------------------------------------------------------------------------
# Compute closure signals
# ---------------------------------------------------------------------------

def compute_closure_signals(
    db: duckdb.DuckDBPyConnection,
    window_start: datetime,
    actor_id: str,
    config: ClosureConfig | None = None,
) -> ClosureResult:
    """Compute closure_ratio and orphaned_privilege for an (actor, window).

    Examines all closure watches opened by this actor.
    Runs settlement detection on open watches.
    """
    if config is None:
        config = _default_config()

    # Check temporal expiry first
    check_temporal_expiry(db, window_start)

    # Check settlement for open, settleable watches
    open_watches_rows = db.execute(
        """
        SELECT resource_id, resource_type, opening_ts, window_hours
        FROM closure_state
        WHERE opening_actor_id = ? AND is_closed = FALSE
        """,
        [actor_id],
    ).fetchall()

    for resource_id, resource_type, opening_ts, window_hours in open_watches_rows:
        if resource_type in config.never_settle_types:
            continue
        s_hours = config.settlement_hours.get(resource_type, 4)
        confidence = _detect_settlement(db, resource_id, opening_ts, window_start, s_hours)
        if confidence >= 0.5:
            db.execute(
                """
                UPDATE closure_state
                SET is_closed = TRUE, closing_ts = ?
                WHERE resource_id = ? AND is_closed = FALSE
                """,
                [window_start, resource_id],
            )

    # Compute ratio and orphaned score from all watches for this actor
    all_watches = db.execute(
        """
        SELECT is_closed, sensitivity, opening_ts, window_hours, resource_type
        FROM closure_state
        WHERE opening_actor_id = ?
        """,
        [actor_id],
    ).fetchall()

    if not all_watches:
        return ClosureResult(
            closure_ratio=1.0,
            orphaned_privilege=0.0,
            explanation="no closure watches",
            open_watches=0,
            closed_watches=0,
        )

    closed_count = sum(1 for w in all_watches if w[0])
    total = len(all_watches)
    closure_ratio = closed_count / total

    # Orphaned privilege: weighted score for unclosed, overdue watches
    orphaned = 0.0
    for is_closed, sensitivity, opening_ts, window_hours, resource_type in all_watches:
        if is_closed:
            continue
        hours_elapsed = (window_start - opening_ts).total_seconds() / 3600
        if hours_elapsed > window_hours:
            overdue_factor = 1.0 + math.log2(max(1.0, hours_elapsed / window_hours))
            orphaned += sensitivity * overdue_factor

    explanation_parts = [f"watches: {closed_count}/{total} closed"]
    if orphaned > 0:
        explanation_parts.append(f"orphaned_privilege={orphaned:.2f}")

    return ClosureResult(
        closure_ratio=closure_ratio,
        orphaned_privilege=orphaned,
        explanation="; ".join(explanation_parts),
        open_watches=total - closed_count,
        closed_watches=closed_count,
    )


# ---------------------------------------------------------------------------
# Discovery: pair mining (platform-agnostic)
# ---------------------------------------------------------------------------

def mine_candidate_pairs(
    db: duckdb.DuckDBPyConnection,
    lookback_days: int = 30,
    min_observations: int = 3,
    config: ClosureConfig | None = None,
) -> list[dict]:
    """Discover opening-closing patterns from observed event sequences.

    Platform-agnostic: scans events in sensitive zones (from config),
    grouped by target_id. Finds recurring (action_A → action_B) sequences.
    """
    if config is None:
        config = _default_config()

    # Build zone filter from config failsafe_zones + SECRET
    sensitive_zones = list(config.failsafe_zones | {"SECRET"})
    placeholders = ", ".join("?" for _ in sensitive_zones)

    sensitive = db.execute(
        f"SELECT target_id, action_type, ts FROM events "  # noqa: S608  # nosec B608
        f"WHERE target_zone IN ({placeholders}) ORDER BY target_id, ts",
        sensitive_zones,
    ).fetchall()

    # Group by target_id and find (action_A → next different action_B) sequences
    target_sequences: dict[str, list[tuple]] = defaultdict(list)
    for target_id, action_type, ts in sensitive:
        target_sequences[target_id].append((action_type, ts))

    pair_counts: dict[tuple[str, str], list[float]] = defaultdict(list)
    for target_id, seq in target_sequences.items():
        for i, (a_type, a_ts) in enumerate(seq):
            for j in range(i + 1, len(seq)):
                b_type, b_ts = seq[j]
                if b_type == a_type:
                    continue
                gap_hours = (b_ts - a_ts).total_seconds() / 3600.0
                if gap_hours > 720:
                    break
                pair_counts[(a_type, b_type)].append(gap_hours)
                break

    # Filter by min_observations
    rows = []
    for (opening, closing), gaps in pair_counts.items():
        if len(gaps) >= min_observations:
            sorted_gaps = sorted(gaps)
            median_gap = sorted_gaps[len(sorted_gaps) // 2]
            rows.append((opening, closing, len(gaps), median_gap))

    candidates = []
    for opening_type, closing_type, obs_count, median_gap in rows:
        candidate_id = f"cp-{opening_type}-{closing_type}"

        now = datetime.now(tz=None)
        sig = _json.dumps({"opening": opening_type, "closing": closing_type, "median_gap_hours": round(median_gap, 1)})
        db.execute(
            """
            INSERT INTO candidate_patterns (
                candidate_id, cluster_signature, composite_score,
                run_count, first_seen, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (candidate_id) DO UPDATE SET
                run_count = EXCLUDED.run_count,
                composite_score = EXCLUDED.composite_score,
                last_seen = EXCLUDED.last_seen
            """,
            [candidate_id, sig, float(obs_count), obs_count, now, now],
        )

        candidates.append({
            "candidate_id": candidate_id,
            "opening_action_type": opening_type,
            "closing_action_type": closing_type,
            "obs_count": obs_count,
            "median_gap_hours": median_gap,
        })

    return candidates


def promote_candidates(
    db: duckdb.DuckDBPyConnection,
    min_observations: int = 5,
) -> int:
    """Promote qualified candidates to opening_closing_pairs (tier=2).

    Platform-agnostic: operates purely on candidate_patterns table.
    """

    rows = db.execute(
        """
        SELECT candidate_id, cluster_signature, run_count, composite_score
        FROM candidate_patterns
        WHERE run_count >= ?
          AND promoted_to IS NULL
          AND (rejected IS NULL OR rejected = FALSE)
        """,
        [min_observations],
    ).fetchall()

    promoted = 0
    for candidate_id, sig_json, run_count, score in rows:
        sig = _json.loads(sig_json)
        opening = sig.get("opening")
        closing = sig.get("closing")
        median_gap = sig.get("median_gap_hours", 24)

        if not opening or not closing:
            continue

        existing = db.execute(
            "SELECT 1 FROM opening_closing_pairs WHERE opening_action_type = ? AND closing_action_type = ?",
            [opening, closing],
        ).fetchone()
        if existing:
            db.execute(
                "UPDATE candidate_patterns SET promoted_to = 'existing' WHERE candidate_id = ?",
                [candidate_id],
            )
            continue

        pair_id = f"disc-{opening}-{closing}"
        window_hours = max(1, int(median_gap * 2))

        db.execute(
            """
            INSERT INTO opening_closing_pairs (pair_id, opening_action_type, closing_action_type, window_hours, tier)
            VALUES (?, ?, ?, ?, 2)
            ON CONFLICT (pair_id) DO NOTHING
            """,
            [pair_id, opening, closing, window_hours],
        )

        db.execute(
            "UPDATE candidate_patterns SET promoted_to = ? WHERE candidate_id = ?",
            [pair_id, candidate_id],
        )
        promoted += 1

    return promoted


# ---------------------------------------------------------------------------
# Default config (loaded lazily from settings)
# ---------------------------------------------------------------------------

def _default_config() -> ClosureConfig:
    """Load default ClosureConfig from SETTINGS. Lazy to avoid circular imports."""
    from config.settings import SETTINGS
    return SETTINGS.closure
