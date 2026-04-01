"""Tests for provenance pattern matching layer."""

import json
from datetime import datetime

from src.provenance.patterns import (
    compute_pattern_match,
    deactivate_pattern,
    list_patterns,
    register_pattern,
)
from tests.conftest import make_event

W1 = datetime(2026, 3, 28, 10, 0, 0)  # Friday, 10:00 UTC


def _register_worker_pattern(db):
    """Register a standard normal-worker pattern for testing."""
    return register_pattern(
        db,
        name="normal-worker-5min",
        description="Normal worker every 5 min",
        initiator_type="SCHEDULED",
        expected_actors=["normal-worker-sa@proj.iam.gserviceaccount.com"],
        expected_zones=["SECRET", "DATA", "DATA"],
        expected_window=None,
        rate_min=2.0,
        rate_max=6.0,
        expected_duration=15,
    )


# --- CRUD ---


class TestRegisterPattern:
    def test_returns_pattern_id(self, db):
        pid = _register_worker_pattern(db)
        assert pid is not None
        assert len(pid) > 0

    def test_fields_stored(self, db):
        pid = _register_worker_pattern(db)
        row = db.execute(
            "SELECT name, initiator_type, expected_actors, expected_zones, active "
            "FROM sanctioned_patterns WHERE pattern_id = ?",
            [pid],
        ).fetchone()
        assert row[0] == "normal-worker-5min"
        assert row[1] == "SCHEDULED"
        assert json.loads(row[2]) == ["normal-worker-sa@proj.iam.gserviceaccount.com"]
        assert json.loads(row[3]) == ["SECRET", "DATA", "DATA"]
        assert row[4] is True


class TestListPatterns:
    def test_active_only(self, db):
        pid = _register_worker_pattern(db)
        deactivate_pattern(db, pid)
        register_pattern(db, name="other", description="", initiator_type="SCHEDULED",
                         expected_actors=[], expected_zones=[], expected_window=None,
                         rate_min=0, rate_max=100, expected_duration=15)
        active = list_patterns(db, include_inactive=False)
        assert len(active) == 1
        assert active[0]["name"] == "other"

    def test_include_inactive(self, db):
        _register_worker_pattern(db)
        pid2 = register_pattern(db, name="other", description="", initiator_type="SCHEDULED",
                                expected_actors=[], expected_zones=[], expected_window=None,
                                rate_min=0, rate_max=100, expected_duration=15)
        deactivate_pattern(db, pid2)
        all_patterns = list_patterns(db, include_inactive=True)
        assert len(all_patterns) == 2


class TestDeactivatePattern:
    def test_deactivates(self, db):
        pid = _register_worker_pattern(db)
        result = deactivate_pattern(db, pid)
        assert result is True
        row = db.execute(
            "SELECT active FROM sanctioned_patterns WHERE pattern_id = ?", [pid]
        ).fetchone()
        assert row[0] is False

    def test_nonexistent(self, db):
        result = deactivate_pattern(db, "nonexistent-id")
        assert result is False


# --- Component matching ---


class TestActorMatch:
    def test_exact_match(self, db):
        _register_worker_pattern(db)
        score, pid = compute_pattern_match(
            db, W1, "normal-worker-sa@proj.iam.gserviceaccount.com",
            ["SECRET", "DATA", "DATA"], event_count=3, window_ts=W1,
        )
        assert score > 0.25  # actor component alone = 0.30

    def test_no_match(self, db):
        _register_worker_pattern(db)
        score, pid = compute_pattern_match(
            db, W1, "attacker@evil.com",
            ["SECRET", "DATA", "DATA"], event_count=3, window_ts=W1,
        )
        # Actor component = 0, but zone/rate may still match
        assert score < 0.75  # without actor match, can't get full score


class TestZoneMatch:
    def test_exact_sequence(self, db):
        _register_worker_pattern(db)
        score, _ = compute_pattern_match(
            db, W1, "normal-worker-sa@proj.iam.gserviceaccount.com",
            ["SECRET", "DATA", "DATA"], event_count=3, window_ts=W1,
        )
        # All 4 components should score high
        assert score > 0.8

    def test_partial_sequence(self, db):
        _register_worker_pattern(db)
        score_exact, _ = compute_pattern_match(
            db, W1, "normal-worker-sa@proj.iam.gserviceaccount.com",
            ["SECRET", "DATA", "DATA"], event_count=3, window_ts=W1,
        )
        score_partial, _ = compute_pattern_match(
            db, W1, "normal-worker-sa@proj.iam.gserviceaccount.com",
            ["SECRET", "COMPUTE", "DATA"], event_count=3, window_ts=W1,
        )
        assert score_partial < score_exact

    def test_empty_actual(self, db):
        _register_worker_pattern(db)
        score, _ = compute_pattern_match(
            db, W1, "normal-worker-sa@proj.iam.gserviceaccount.com",
            [], event_count=0, window_ts=W1,
        )
        assert score <= 0.5  # zone match = 0, rate match = 0


class TestTimeMatch:
    def test_no_window_constraint(self, db):
        """Pattern with no expected_window matches any time."""
        _register_worker_pattern(db)  # expected_window=None
        score, _ = compute_pattern_match(
            db, W1, "normal-worker-sa@proj.iam.gserviceaccount.com",
            ["SECRET", "DATA", "DATA"], event_count=3, window_ts=W1,
        )
        # Time component should be 1.0 (no constraint)
        assert score > 0.8

    def test_within_window(self, db):
        """Pattern with time window, event is within."""
        register_pattern(
            db, name="business-hours", description="",
            initiator_type="SCHEDULED",
            expected_actors=["worker@proj"],
            expected_zones=["DATA"],
            expected_window=json.dumps({"days_of_week": [0, 1, 2, 3, 4], "hour_start": 8, "hour_end": 18}),
            rate_min=1, rate_max=100, expected_duration=15,
        )
        # W1 is Friday 10:00 UTC (weekday=4)
        score, _ = compute_pattern_match(
            db, W1, "worker@proj", ["DATA"], event_count=5, window_ts=W1,
        )
        assert score > 0.7

    def test_outside_window(self, db):
        """Pattern expects weekdays only, event is on weekend."""
        register_pattern(
            db, name="weekday-only", description="",
            initiator_type="SCHEDULED",
            expected_actors=["worker@proj"],
            expected_zones=["DATA"],
            expected_window=json.dumps({"days_of_week": [0, 1, 2, 3, 4], "hour_start": 8, "hour_end": 18}),
            rate_min=1, rate_max=100, expected_duration=15,
        )
        # Wednesday 10:00 (weekday=2) vs Sunday 10:00 (weekday=6)
        wednesday = datetime(2026, 3, 25, 10, 0, 0)
        sunday = datetime(2026, 3, 29, 10, 0, 0)
        score_weekday, _ = compute_pattern_match(
            db, W1, "worker@proj", ["DATA"], event_count=5, window_ts=wednesday,
        )
        score_weekend, _ = compute_pattern_match(
            db, W1, "worker@proj", ["DATA"], event_count=5, window_ts=sunday,
        )
        assert score_weekend < score_weekday


class TestRateMatch:
    def test_within_range(self, db):
        _register_worker_pattern(db)  # rate_min=2, rate_max=6
        score, _ = compute_pattern_match(
            db, W1, "normal-worker-sa@proj.iam.gserviceaccount.com",
            ["SECRET", "DATA", "DATA"], event_count=3, window_ts=W1,
        )
        assert score > 0.8

    def test_too_fast(self, db):
        _register_worker_pattern(db)  # rate_max=6
        score_normal, _ = compute_pattern_match(
            db, W1, "normal-worker-sa@proj.iam.gserviceaccount.com",
            ["SECRET", "DATA", "DATA"], event_count=3, window_ts=W1,
        )
        score_fast, _ = compute_pattern_match(
            db, W1, "normal-worker-sa@proj.iam.gserviceaccount.com",
            ["SECRET", "DATA", "DATA"], event_count=50, window_ts=W1,
        )
        assert score_fast < score_normal


class TestComposite:
    def test_no_active_patterns(self, db):
        score, pid = compute_pattern_match(
            db, W1, "anyone@proj", ["DATA"], event_count=1, window_ts=W1,
        )
        assert score == 0.0
        assert pid is None

    def test_best_pattern_wins(self, db):
        """When multiple patterns exist, highest match score wins."""
        _register_worker_pattern(db)
        register_pattern(
            db, name="bad-match", description="",
            initiator_type="SCHEDULED",
            expected_actors=["other-sa@proj"],
            expected_zones=["COMPUTE", "COMPUTE"],
            expected_window=None, rate_min=100, rate_max=200, expected_duration=15,
        )
        score, pid = compute_pattern_match(
            db, W1, "normal-worker-sa@proj.iam.gserviceaccount.com",
            ["SECRET", "DATA", "DATA"], event_count=3, window_ts=W1,
        )
        # Should match the worker pattern, not the bad one
        assert score > 0.8
        assert pid is not None
