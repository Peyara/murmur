"""Tests for event deduplication."""

import pytest
from datetime import datetime

from src.schema import ActionType, ActorType, TargetType, TargetZone
from src.ingest.dedup import compute_event_id, insert_event
from tests.conftest import make_event


class TestComputeEventId:
    def test_deterministic(self):
        id1 = compute_event_id("2026-01-01T00:00:00Z", "actor", "method", "resource", "insert1")
        id2 = compute_event_id("2026-01-01T00:00:00Z", "actor", "method", "resource", "insert1")
        assert id1 == id2

    def test_different_inputs_different_ids(self):
        id1 = compute_event_id("2026-01-01T00:00:00Z", "actor", "method", "resource", "insert1")
        id2 = compute_event_id("2026-01-01T00:00:00Z", "actor", "method", "resource", "insert2")
        assert id1 != id2

    def test_non_empty(self):
        eid = compute_event_id("ts", "actor", "method", "resource", "insert")
        assert len(eid) > 0


class TestInsertEvent:
    def test_insert_new_event(self, db):
        event = make_event(event_id="unique-001")
        inserted = insert_event(db, event)
        assert inserted is True
        count = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert count == 1

    def test_duplicate_rejected(self, db):
        event = make_event(event_id="dup-001")
        assert insert_event(db, event) is True
        assert insert_event(db, event) is False
        count = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert count == 1

    def test_different_events_both_inserted(self, db):
        e1 = make_event(event_id="evt-a")
        e2 = make_event(event_id="evt-b")
        assert insert_event(db, e1) is True
        assert insert_event(db, e2) is True
        count = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert count == 2

    def test_inserted_event_has_correct_fields(self, db):
        event = make_event(
            event_id="verify-001",
            actor_id="test-actor@example.com",
            action_type=ActionType.SECRET_ACCESS,
            target_zone=TargetZone.SECRET,
        )
        insert_event(db, event)
        row = db.execute(
            "SELECT actor_id, action_type, target_zone FROM events WHERE event_id = 'verify-001'"
        ).fetchone()
        assert row[0] == "test-actor@example.com"
        assert row[1] == "SECRET_ACCESS"
        assert row[2] == "SECRET"
