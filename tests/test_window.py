"""Tests for world model windowing layer."""

import json
import math
from datetime import datetime, timedelta

from src.ingest.dedup import insert_event
from src.schema import ActionType, ProvenanceLevel, TargetZone
from src.world.window import compute_actor_windows, compute_edges, shannon_entropy
from tests.conftest import make_event


# --- Helpers ---


def _insert_events(db, events):
    """Insert a list of CanonicalEvents into the DB."""
    for e in events:
        insert_event(db, e)


W1 = datetime(2026, 3, 28, 10, 0, 0)  # standard test window


# --- shannon_entropy ---


class TestShannonEntropy:
    def test_single_item(self):
        assert shannon_entropy([5]) == 0.0

    def test_two_equal(self):
        assert abs(shannon_entropy([3, 3]) - 1.0) < 1e-9

    def test_three_equal(self):
        assert abs(shannon_entropy([2, 2, 2]) - math.log2(3)) < 1e-9

    def test_skewed(self):
        # [9, 1] -> H = -(0.9*log2(0.9) + 0.1*log2(0.1))
        h = shannon_entropy([9, 1])
        expected = -(0.9 * math.log2(0.9) + 0.1 * math.log2(0.1))
        assert abs(h - expected) < 1e-9

    def test_empty(self):
        assert shannon_entropy([]) == 0.0


# --- compute_actor_windows ---


class TestWindowAggregation:
    def test_single_event(self, db):
        _insert_events(db, [
            make_event(event_id="e1", ts=W1 + timedelta(minutes=2),
                       window_start=W1, actor_id="sa@proj",
                       action_type=ActionType.GCS_READ,
                       target_zone=TargetZone.DATA,
                       target_id="bucket/obj1"),
        ])
        count = compute_actor_windows(db, W1)
        assert count == 1

        row = db.execute(
            "SELECT event_count, action_types, zone_sequence, target_ids "
            "FROM actor_windows WHERE window_start = ? AND actor_id = ?",
            [W1, "sa@proj"],
        ).fetchone()
        assert row[0] == 1  # event_count
        assert json.loads(row[1]) == ["GCS_READ"]
        assert json.loads(row[2]) == ["DATA"]
        assert json.loads(row[3]) == ["bucket/obj1"]

    def test_multi_event_same_actor(self, db):
        _insert_events(db, [
            make_event(event_id="e1", ts=W1 + timedelta(minutes=1),
                       window_start=W1, actor_id="sa@proj",
                       action_type=ActionType.SECRET_ACCESS,
                       target_zone=TargetZone.SECRET,
                       target_id="secret/high"),
            make_event(event_id="e2", ts=W1 + timedelta(minutes=3),
                       window_start=W1, actor_id="sa@proj",
                       action_type=ActionType.GCS_READ,
                       target_zone=TargetZone.DATA,
                       target_id="bucket/obj1"),
            make_event(event_id="e3", ts=W1 + timedelta(minutes=5),
                       window_start=W1, actor_id="sa@proj",
                       action_type=ActionType.GCS_WRITE,
                       target_zone=TargetZone.DATA,
                       target_id="bucket/out1"),
        ])
        count = compute_actor_windows(db, W1)
        assert count == 1

        row = db.execute(
            "SELECT event_count, action_types, zone_sequence, target_ids "
            "FROM actor_windows WHERE window_start = ? AND actor_id = ?",
            [W1, "sa@proj"],
        ).fetchone()
        assert row[0] == 3
        assert sorted(json.loads(row[1])) == ["GCS_READ", "GCS_WRITE", "SECRET_ACCESS"]
        assert json.loads(row[2]) == ["SECRET", "DATA", "DATA"]  # ordered by ts
        assert sorted(json.loads(row[3])) == ["bucket/obj1", "bucket/out1", "secret/high"]

    def test_two_actors_same_window(self, db):
        _insert_events(db, [
            make_event(event_id="e1", ts=W1 + timedelta(minutes=1),
                       window_start=W1, actor_id="alice@proj"),
            make_event(event_id="e2", ts=W1 + timedelta(minutes=2),
                       window_start=W1, actor_id="bob@proj"),
        ])
        count = compute_actor_windows(db, W1)
        assert count == 2

    def test_duplicate_target_ids_collapsed(self, db):
        _insert_events(db, [
            make_event(event_id="e1", ts=W1 + timedelta(minutes=1),
                       window_start=W1, actor_id="sa@proj",
                       target_id="bucket/obj1"),
            make_event(event_id="e2", ts=W1 + timedelta(minutes=2),
                       window_start=W1, actor_id="sa@proj",
                       target_id="bucket/obj1"),
        ])
        compute_actor_windows(db, W1)
        row = db.execute(
            "SELECT target_ids FROM actor_windows "
            "WHERE window_start = ? AND actor_id = ?",
            [W1, "sa@proj"],
        ).fetchone()
        assert json.loads(row[0]) == ["bucket/obj1"]


class TestProvenanceLevel:
    def test_strongest_wins(self, db):
        _insert_events(db, [
            make_event(event_id="e1", ts=W1 + timedelta(minutes=1),
                       window_start=W1, actor_id="sa@proj",
                       provenance_level=ProvenanceLevel.NONE),
            make_event(event_id="e2", ts=W1 + timedelta(minutes=2),
                       window_start=W1, actor_id="sa@proj",
                       provenance_level=ProvenanceLevel.WEAK),
            make_event(event_id="e3", ts=W1 + timedelta(minutes=3),
                       window_start=W1, actor_id="sa@proj",
                       provenance_level=ProvenanceLevel.STRONG),
        ])
        compute_actor_windows(db, W1)
        row = db.execute(
            "SELECT provenance_level FROM actor_windows "
            "WHERE window_start = ? AND actor_id = ?",
            [W1, "sa@proj"],
        ).fetchone()
        assert row[0] == "STRONG"

    def test_none_when_all_none(self, db):
        _insert_events(db, [
            make_event(event_id="e1", ts=W1 + timedelta(minutes=1),
                       window_start=W1, actor_id="sa@proj",
                       provenance_level=ProvenanceLevel.NONE),
        ])
        compute_actor_windows(db, W1)
        row = db.execute(
            "SELECT provenance_level FROM actor_windows "
            "WHERE window_start = ? AND actor_id = ?",
            [W1, "sa@proj"],
        ).fetchone()
        assert row[0] == "NONE"


class TestBurstPerMin:
    def test_events_spread_over_window(self, db):
        """3 events over 4 minutes -> burst = 3/4 = 0.75."""
        _insert_events(db, [
            make_event(event_id="e1", ts=W1 + timedelta(minutes=1),
                       window_start=W1, actor_id="sa@proj"),
            make_event(event_id="e2", ts=W1 + timedelta(minutes=3),
                       window_start=W1, actor_id="sa@proj"),
            make_event(event_id="e3", ts=W1 + timedelta(minutes=5),
                       window_start=W1, actor_id="sa@proj"),
        ])
        compute_actor_windows(db, W1)
        row = db.execute(
            "SELECT burst_per_min FROM actor_windows "
            "WHERE window_start = ? AND actor_id = ?",
            [W1, "sa@proj"],
        ).fetchone()
        assert abs(row[0] - 3.0 / 4.0) < 1e-6

    def test_single_event_one_minute_floor(self, db):
        """1 event -> span clamped to 1 min -> burst = 1.0."""
        _insert_events(db, [
            make_event(event_id="e1", ts=W1 + timedelta(minutes=2),
                       window_start=W1, actor_id="sa@proj"),
        ])
        compute_actor_windows(db, W1)
        row = db.execute(
            "SELECT burst_per_min FROM actor_windows "
            "WHERE window_start = ? AND actor_id = ?",
            [W1, "sa@proj"],
        ).fetchone()
        assert abs(row[0] - 1.0) < 1e-6

    def test_events_in_same_second(self, db):
        """5 events at same ts -> span = 0, clamped to 1 min -> burst = 5.0."""
        events = [
            make_event(event_id=f"e{i}", ts=W1 + timedelta(minutes=2),
                       window_start=W1, actor_id="sa@proj")
            for i in range(5)
        ]
        _insert_events(db, events)
        compute_actor_windows(db, W1)
        row = db.execute(
            "SELECT burst_per_min FROM actor_windows "
            "WHERE window_start = ? AND actor_id = ?",
            [W1, "sa@proj"],
        ).fetchone()
        assert abs(row[0] - 5.0) < 1e-6


class TestBreadthEntropy:
    def test_single_target_zero_entropy(self, db):
        _insert_events(db, [
            make_event(event_id="e1", ts=W1 + timedelta(minutes=1),
                       window_start=W1, actor_id="sa@proj",
                       target_id="bucket/obj1"),
            make_event(event_id="e2", ts=W1 + timedelta(minutes=2),
                       window_start=W1, actor_id="sa@proj",
                       target_id="bucket/obj1"),
        ])
        compute_actor_windows(db, W1)
        row = db.execute(
            "SELECT breadth_entropy FROM actor_windows "
            "WHERE window_start = ? AND actor_id = ?",
            [W1, "sa@proj"],
        ).fetchone()
        assert abs(row[0]) < 1e-9

    def test_two_equal_targets(self, db):
        _insert_events(db, [
            make_event(event_id="e1", ts=W1 + timedelta(minutes=1),
                       window_start=W1, actor_id="sa@proj",
                       target_id="t1"),
            make_event(event_id="e2", ts=W1 + timedelta(minutes=2),
                       window_start=W1, actor_id="sa@proj",
                       target_id="t2"),
        ])
        compute_actor_windows(db, W1)
        row = db.execute(
            "SELECT breadth_entropy FROM actor_windows "
            "WHERE window_start = ? AND actor_id = ?",
            [W1, "sa@proj"],
        ).fetchone()
        assert abs(row[0] - 1.0) < 1e-6  # log2(2) = 1.0


# --- compute_edges ---


class TestEdgeExtraction:
    def test_consecutive_different_zones(self, db):
        """SECRET -> DATA transition produces one edge."""
        _insert_events(db, [
            make_event(event_id="e1", ts=W1 + timedelta(minutes=1),
                       window_start=W1, actor_id="sa@proj",
                       target_zone=TargetZone.SECRET, target_id="secret/high"),
            make_event(event_id="e2", ts=W1 + timedelta(minutes=2),
                       window_start=W1, actor_id="sa@proj",
                       target_zone=TargetZone.DATA, target_id="bucket/obj1"),
        ])
        compute_actor_windows(db, W1)  # edges need actor_windows first? No, just events
        count = compute_edges(db, W1)
        assert count == 1

        row = db.execute(
            "SELECT source_zone, target_zone, target_id, edge_count "
            "FROM edges_window WHERE window_start = ?",
            [W1],
        ).fetchone()
        assert row[0] == "SECRET"
        assert row[1] == "DATA"
        assert row[2] == "bucket/obj1"
        assert row[3] == 1

    def test_self_loop(self, db):
        """DATA -> DATA produces a self-loop edge."""
        _insert_events(db, [
            make_event(event_id="e1", ts=W1 + timedelta(minutes=1),
                       window_start=W1, actor_id="sa@proj",
                       target_zone=TargetZone.DATA, target_id="t1"),
            make_event(event_id="e2", ts=W1 + timedelta(minutes=2),
                       window_start=W1, actor_id="sa@proj",
                       target_zone=TargetZone.DATA, target_id="t2"),
        ])
        count = compute_edges(db, W1)
        assert count == 1

        row = db.execute(
            "SELECT source_zone, target_zone FROM edges_window WHERE window_start = ?",
            [W1],
        ).fetchone()
        assert row[0] == "DATA"
        assert row[1] == "DATA"

    def test_single_event_no_edges(self, db):
        _insert_events(db, [
            make_event(event_id="e1", ts=W1 + timedelta(minutes=1),
                       window_start=W1, actor_id="sa@proj"),
        ])
        count = compute_edges(db, W1)
        assert count == 0

    def test_edge_count_aggregation(self, db):
        """3 transitions SECRET->DATA with same target -> edge_count=3."""
        _insert_events(db, [
            make_event(event_id="e1", ts=W1 + timedelta(seconds=1),
                       window_start=W1, actor_id="sa@proj",
                       target_zone=TargetZone.SECRET, target_id="s1"),
            make_event(event_id="e2", ts=W1 + timedelta(seconds=2),
                       window_start=W1, actor_id="sa@proj",
                       target_zone=TargetZone.DATA, target_id="bucket/x"),
            make_event(event_id="e3", ts=W1 + timedelta(seconds=3),
                       window_start=W1, actor_id="sa@proj",
                       target_zone=TargetZone.SECRET, target_id="s1"),
            make_event(event_id="e4", ts=W1 + timedelta(seconds=4),
                       window_start=W1, actor_id="sa@proj",
                       target_zone=TargetZone.DATA, target_id="bucket/x"),
            make_event(event_id="e5", ts=W1 + timedelta(seconds=5),
                       window_start=W1, actor_id="sa@proj",
                       target_zone=TargetZone.SECRET, target_id="s1"),
            make_event(event_id="e6", ts=W1 + timedelta(seconds=6),
                       window_start=W1, actor_id="sa@proj",
                       target_zone=TargetZone.DATA, target_id="bucket/x"),
        ])
        compute_edges(db, W1)
        row = db.execute(
            "SELECT edge_count FROM edges_window "
            "WHERE window_start = ? AND source_zone = 'SECRET' AND target_zone = 'DATA' "
            "AND target_id = 'bucket/x'",
            [W1],
        ).fetchone()
        assert row[0] == 3

    def test_different_targets_same_zone_pair(self, db):
        """Same (SECRET, DATA) but different target_ids -> separate edge rows."""
        _insert_events(db, [
            make_event(event_id="e1", ts=W1 + timedelta(seconds=1),
                       window_start=W1, actor_id="sa@proj",
                       target_zone=TargetZone.SECRET, target_id="s1"),
            make_event(event_id="e2", ts=W1 + timedelta(seconds=2),
                       window_start=W1, actor_id="sa@proj",
                       target_zone=TargetZone.DATA, target_id="bucket/a"),
            make_event(event_id="e3", ts=W1 + timedelta(seconds=3),
                       window_start=W1, actor_id="sa@proj",
                       target_zone=TargetZone.SECRET, target_id="s1"),
            make_event(event_id="e4", ts=W1 + timedelta(seconds=4),
                       window_start=W1, actor_id="sa@proj",
                       target_zone=TargetZone.DATA, target_id="bucket/b"),
        ])
        compute_edges(db, W1)
        rows = db.execute(
            "SELECT target_id, edge_count FROM edges_window "
            "WHERE window_start = ? AND source_zone = 'SECRET' AND target_zone = 'DATA' "
            "ORDER BY target_id",
            [W1],
        ).fetchall()
        assert len(rows) == 2
        assert rows[0][0] == "bucket/a"
        assert rows[1][0] == "bucket/b"


class TestIsNew30d:
    def test_new_edge_no_history(self, db):
        """First ever edge -> is_new_30d = True."""
        _insert_events(db, [
            make_event(event_id="e1", ts=W1 + timedelta(minutes=1),
                       window_start=W1, actor_id="sa@proj",
                       target_zone=TargetZone.SECRET, target_id="s1"),
            make_event(event_id="e2", ts=W1 + timedelta(minutes=2),
                       window_start=W1, actor_id="sa@proj",
                       target_zone=TargetZone.DATA, target_id="t1"),
        ])
        compute_edges(db, W1)
        row = db.execute(
            "SELECT is_new_30d FROM edges_window WHERE window_start = ?", [W1]
        ).fetchone()
        assert row[0] is True

    def test_seen_in_recent_window(self, db):
        """Edge existed 2 days ago -> is_new_30d = False."""
        old_window = W1 - timedelta(days=2)
        # Insert historical edge directly
        db.execute(
            "INSERT INTO edges_window (window_start, actor_id, source_zone, target_zone, "
            "target_id, edge_count, first_seen, is_new_30d) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [old_window, "sa@proj", "SECRET", "DATA", "old-target", 1, old_window, True],
        )
        # Now insert events for current window with same zone pair
        _insert_events(db, [
            make_event(event_id="e1", ts=W1 + timedelta(minutes=1),
                       window_start=W1, actor_id="sa@proj",
                       target_zone=TargetZone.SECRET, target_id="s1"),
            make_event(event_id="e2", ts=W1 + timedelta(minutes=2),
                       window_start=W1, actor_id="sa@proj",
                       target_zone=TargetZone.DATA, target_id="t1"),
        ])
        compute_edges(db, W1)
        row = db.execute(
            "SELECT is_new_30d FROM edges_window "
            "WHERE window_start = ? AND actor_id = 'sa@proj'",
            [W1],
        ).fetchone()
        assert row[0] is False

    def test_seen_31_days_ago_is_new(self, db):
        """Edge existed 31 days ago -> outside lookback -> is_new_30d = True."""
        old_window = W1 - timedelta(days=31)
        db.execute(
            "INSERT INTO edges_window (window_start, actor_id, source_zone, target_zone, "
            "target_id, edge_count, first_seen, is_new_30d) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [old_window, "sa@proj", "SECRET", "DATA", "old-target", 1, old_window, True],
        )
        _insert_events(db, [
            make_event(event_id="e1", ts=W1 + timedelta(minutes=1),
                       window_start=W1, actor_id="sa@proj",
                       target_zone=TargetZone.SECRET, target_id="s1"),
            make_event(event_id="e2", ts=W1 + timedelta(minutes=2),
                       window_start=W1, actor_id="sa@proj",
                       target_zone=TargetZone.DATA, target_id="t1"),
        ])
        compute_edges(db, W1)
        row = db.execute(
            "SELECT is_new_30d FROM edges_window "
            "WHERE window_start = ? AND actor_id = 'sa@proj'",
            [W1],
        ).fetchone()
        assert row[0] is True
