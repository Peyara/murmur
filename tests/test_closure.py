"""Tests for closure system — resource state tracking, settlement, and scoring."""

import json
import math
from datetime import datetime, timedelta

from src.schema import ActionType, TargetType, TargetZone
from src.ingest.dedup import insert_event
from tests.conftest import make_event

W1 = datetime(2026, 3, 25, 10, 0, 0)
ACTOR = "test-sa@project.iam.gserviceaccount.com"
TARGET_SA = "projects/-/serviceAccounts/12345"
TARGET_KEY = "projects/-/serviceAccounts/12345/keys/key-001"


def _insert_event(db, **overrides):
    """Helper: create + insert an event, return it."""
    evt = make_event(**overrides)
    insert_event(db, evt)
    return evt


# ---------------------------------------------------------------------------
# Seed pairs
# ---------------------------------------------------------------------------
class TestSeedPairs:
    def test_seed_inserts_pairs(self, db):
        from src.score.closure import seed_pairs

        count = seed_pairs(db)
        assert count >= 2  # at least IAM_CREATE_KEY and IAM_CREATE_SA

        rows = db.execute("SELECT * FROM opening_closing_pairs").fetchall()
        action_types = {r[1] for r in rows}  # opening_action_type
        assert "IAM_CREATE_KEY" in action_types
        assert "IAM_CREATE_SA" in action_types

    def test_seed_idempotent(self, db):
        from src.score.closure import seed_pairs

        seed_pairs(db)
        seed_pairs(db)  # should not error or duplicate
        rows = db.execute("SELECT * FROM opening_closing_pairs").fetchall()
        # Count unique pair_ids
        assert len(rows) == len({r[0] for r in rows})


# ---------------------------------------------------------------------------
# Create watch
# ---------------------------------------------------------------------------
class TestCreateWatch:
    def test_opening_creates_watch(self, db):
        from src.score.closure import seed_pairs, create_watch

        seed_pairs(db)
        evt = _insert_event(
            db, event_id="e-create-key", ts=W1 + timedelta(minutes=1),
            window_start=W1, actor_id=ACTOR,
            action_type=ActionType.IAM_CREATE_KEY,
            target_id=TARGET_KEY, target_type=TargetType.SA_KEY,
            target_zone=TargetZone.IDENTITY,
        )
        created = create_watch(db, evt)
        assert created is not None

        row = db.execute("SELECT is_closed FROM closure_state WHERE resource_id = ?", [TARGET_KEY]).fetchone()
        assert row is not None
        assert row[0] is False  # is_closed

    def test_non_opening_skipped(self, db):
        from src.score.closure import seed_pairs, create_watch

        seed_pairs(db)
        evt = _insert_event(
            db, event_id="e-gcs-read", ts=W1 + timedelta(minutes=1),
            window_start=W1, actor_id=ACTOR,
            action_type=ActionType.GCS_READ,
            target_id="bucket/obj", target_type=TargetType.GCS_BUCKET,
            target_zone=TargetZone.DATA,
        )
        created = create_watch(db, evt)
        assert created is None

        count = db.execute("SELECT count(*) FROM closure_state").fetchone()[0]
        assert count == 0

    def test_duplicate_resource_idempotent(self, db):
        from src.score.closure import seed_pairs, create_watch

        seed_pairs(db)
        evt1 = _insert_event(
            db, event_id="e1", ts=W1 + timedelta(minutes=1),
            window_start=W1, actor_id=ACTOR,
            action_type=ActionType.IAM_CREATE_KEY,
            target_id=TARGET_KEY, target_type=TargetType.SA_KEY,
            target_zone=TargetZone.IDENTITY,
        )
        evt2 = _insert_event(
            db, event_id="e2", ts=W1 + timedelta(minutes=5),
            window_start=W1, actor_id=ACTOR,
            action_type=ActionType.IAM_CREATE_KEY,
            target_id=TARGET_KEY, target_type=TargetType.SA_KEY,
            target_zone=TargetZone.IDENTITY,
        )
        create_watch(db, evt1)
        create_watch(db, evt2)  # same resource — should not duplicate

        count = db.execute("SELECT count(*) FROM closure_state").fetchone()[0]
        assert count == 1

    def test_unknown_action_identity_zone_creates_watch(self, db):
        """Failsafe: unknown action in IDENTITY zone → treat as opening."""
        from src.score.closure import seed_pairs, create_watch

        seed_pairs(db)
        evt = _insert_event(
            db, event_id="e-other", ts=W1 + timedelta(minutes=1),
            window_start=W1, actor_id=ACTOR,
            action_type=ActionType.OTHER,
            target_id="projects/-/unknown-resource",
            target_type=TargetType.OTHER,
            target_zone=TargetZone.IDENTITY,
        )
        created = create_watch(db, evt)
        assert created is not None  # failsafe: unknown in IDENTITY = opening


# ---------------------------------------------------------------------------
# Explicit close
# ---------------------------------------------------------------------------
class TestExplicitClose:
    def test_matching_close_marks_closed(self, db):
        from src.score.closure import seed_pairs, create_watch, try_close_watch

        seed_pairs(db)
        # Open: create key
        evt_open = _insert_event(
            db, event_id="e-open", ts=W1 + timedelta(minutes=1),
            window_start=W1, actor_id=ACTOR,
            action_type=ActionType.IAM_CREATE_KEY,
            target_id=TARGET_KEY, target_type=TargetType.SA_KEY,
            target_zone=TargetZone.IDENTITY,
        )
        create_watch(db, evt_open)

        # Close: delete key
        evt_close = _insert_event(
            db, event_id="e-close", ts=W1 + timedelta(hours=2),
            window_start=W1, actor_id=ACTOR,
            action_type=ActionType.IAM_DELETE_KEY,
            target_id=TARGET_KEY, target_type=TargetType.SA_KEY,
            target_zone=TargetZone.IDENTITY,
        )
        closed = try_close_watch(db, evt_close)
        assert closed is True

        row = db.execute("SELECT is_closed FROM closure_state WHERE resource_id = ?", [TARGET_KEY]).fetchone()
        assert row[0] is True

    def test_non_matching_not_closed(self, db):
        from src.score.closure import seed_pairs, create_watch, try_close_watch

        seed_pairs(db)
        evt_open = _insert_event(
            db, event_id="e-open", ts=W1 + timedelta(minutes=1),
            window_start=W1, actor_id=ACTOR,
            action_type=ActionType.IAM_CREATE_KEY,
            target_id=TARGET_KEY, target_type=TargetType.SA_KEY,
            target_zone=TargetZone.IDENTITY,
        )
        create_watch(db, evt_open)

        # Unrelated event on same resource
        evt_unrelated = _insert_event(
            db, event_id="e-unrelated", ts=W1 + timedelta(hours=1),
            window_start=W1, actor_id=ACTOR,
            action_type=ActionType.GCS_READ,
            target_id=TARGET_KEY, target_type=TargetType.SA_KEY,
            target_zone=TargetZone.IDENTITY,
        )
        closed = try_close_watch(db, evt_unrelated)
        assert closed is False


# ---------------------------------------------------------------------------
# Temporal expiry
# ---------------------------------------------------------------------------
class TestTemporalExpiry:
    def test_impersonation_auto_closes_after_ttl(self, db):
        from src.score.closure import seed_pairs, create_watch, check_temporal_expiry

        seed_pairs(db)
        evt = _insert_event(
            db, event_id="e-imp", ts=W1 + timedelta(minutes=1),
            window_start=W1, actor_id=ACTOR,
            action_type=ActionType.IAM_IMPERSONATE,
            target_id=TARGET_SA, target_type=TargetType.SERVICE_ACCOUNT,
            target_zone=TargetZone.IDENTITY,
        )
        create_watch(db, evt)

        # 2 hours later — past 1h TTL
        closed_count = check_temporal_expiry(db, W1 + timedelta(hours=2))
        assert closed_count >= 1

        row = db.execute("SELECT is_closed FROM closure_state WHERE resource_id = ?", [TARGET_SA]).fetchone()
        assert row[0] is True

    def test_sa_key_does_not_auto_close(self, db):
        from src.score.closure import seed_pairs, create_watch, check_temporal_expiry

        seed_pairs(db)
        evt = _insert_event(
            db, event_id="e-key", ts=W1 + timedelta(minutes=1),
            window_start=W1, actor_id=ACTOR,
            action_type=ActionType.IAM_CREATE_KEY,
            target_id=TARGET_KEY, target_type=TargetType.SA_KEY,
            target_zone=TargetZone.IDENTITY,
        )
        create_watch(db, evt)

        # Even 30 days later — SA_KEY requires explicit deletion
        closed_count = check_temporal_expiry(db, W1 + timedelta(days=30))
        assert closed_count == 0

        row = db.execute("SELECT is_closed FROM closure_state WHERE resource_id = ?", [TARGET_KEY]).fetchone()
        assert row[0] is False


# ---------------------------------------------------------------------------
# Settlement detection
# ---------------------------------------------------------------------------
class TestSettlement:
    def test_quiet_resource_settles(self, db):
        """Resource with no activity after opening → settlement confidence > 0."""
        from src.score.closure import _detect_settlement

        # No events on this resource after opening — 6 hours later
        confidence = _detect_settlement(db, TARGET_SA, W1, W1 + timedelta(hours=6))
        assert confidence > 0.0

    def test_active_resource_does_not_settle(self, db):
        """Resource with recent activity → confidence = 0."""
        from src.score.closure import _detect_settlement

        # Insert activity on the target just 30 min ago
        _insert_event(
            db, event_id="e-recent", ts=W1 + timedelta(hours=5, minutes=30),
            window_start=W1 + timedelta(hours=5, minutes=15),
            actor_id=ACTOR, target_id=TARGET_SA,
            action_type=ActionType.IAM_SET_POLICY,
            target_zone=TargetZone.IDENTITY, target_type=TargetType.SERVICE_ACCOUNT,
        )
        # Check at 6 hours — only 30 min since last activity
        confidence = _detect_settlement(db, TARGET_SA, W1, W1 + timedelta(hours=6))
        assert confidence == 0.0

    def test_early_check_insufficient_data(self, db):
        """Too early to tell → confidence = 0."""
        from src.score.closure import _detect_settlement

        # Only 30 min after opening
        confidence = _detect_settlement(db, TARGET_SA, W1, W1 + timedelta(minutes=30))
        assert confidence == 0.0


# ---------------------------------------------------------------------------
# Closure ratio
# ---------------------------------------------------------------------------
class TestClosureRatio:
    def test_all_closed(self, db):
        from src.score.closure import seed_pairs, create_watch, try_close_watch, compute_closure_signals

        seed_pairs(db)
        # Open and close a key
        evt_open = _insert_event(
            db, event_id="e-open", ts=W1 + timedelta(minutes=1),
            window_start=W1, actor_id=ACTOR,
            action_type=ActionType.IAM_CREATE_KEY,
            target_id=TARGET_KEY, target_type=TargetType.SA_KEY,
            target_zone=TargetZone.IDENTITY,
        )
        create_watch(db, evt_open)

        evt_close = _insert_event(
            db, event_id="e-close", ts=W1 + timedelta(hours=1),
            window_start=W1, actor_id=ACTOR,
            action_type=ActionType.IAM_DELETE_KEY,
            target_id=TARGET_KEY, target_type=TargetType.SA_KEY,
            target_zone=TargetZone.IDENTITY,
        )
        try_close_watch(db, evt_close)

        result = compute_closure_signals(db, W1 + timedelta(hours=2), ACTOR)
        assert result.closure_ratio == 1.0

    def test_none_closed(self, db):
        from src.score.closure import seed_pairs, create_watch, compute_closure_signals

        seed_pairs(db)
        evt = _insert_event(
            db, event_id="e-open", ts=W1 + timedelta(minutes=1),
            window_start=W1, actor_id=ACTOR,
            action_type=ActionType.IAM_CREATE_KEY,
            target_id=TARGET_KEY, target_type=TargetType.SA_KEY,
            target_zone=TargetZone.IDENTITY,
        )
        create_watch(db, evt)

        # Check immediately — nothing closed, too early for settlement
        result = compute_closure_signals(db, W1 + timedelta(minutes=5), ACTOR)
        assert result.closure_ratio == 0.0

    def test_mixed(self, db):
        from src.score.closure import seed_pairs, create_watch, try_close_watch, compute_closure_signals

        seed_pairs(db)
        # Open two watches
        evt1 = _insert_event(
            db, event_id="e1", ts=W1 + timedelta(minutes=1),
            window_start=W1, actor_id=ACTOR,
            action_type=ActionType.IAM_CREATE_KEY,
            target_id=TARGET_KEY, target_type=TargetType.SA_KEY,
            target_zone=TargetZone.IDENTITY,
        )
        evt2 = _insert_event(
            db, event_id="e2", ts=W1 + timedelta(minutes=2),
            window_start=W1, actor_id=ACTOR,
            action_type=ActionType.IAM_CREATE_SA,
            target_id="projects/-/serviceAccounts/new-sa",
            target_type=TargetType.SERVICE_ACCOUNT,
            target_zone=TargetZone.IDENTITY,
        )
        create_watch(db, evt1)
        create_watch(db, evt2)

        # Close only the first
        evt_close = _insert_event(
            db, event_id="e-close", ts=W1 + timedelta(hours=1),
            window_start=W1, actor_id=ACTOR,
            action_type=ActionType.IAM_DELETE_KEY,
            target_id=TARGET_KEY, target_type=TargetType.SA_KEY,
            target_zone=TargetZone.IDENTITY,
        )
        try_close_watch(db, evt_close)

        result = compute_closure_signals(db, W1 + timedelta(hours=1, minutes=5), ACTOR)
        assert result.closure_ratio == 0.5

    def test_empty_db_default(self, db):
        """No watches at all → ratio=1.0, orphaned=0.0 (no penalty)."""
        from src.score.closure import compute_closure_signals

        result = compute_closure_signals(db, W1, ACTOR)
        assert result.closure_ratio == 1.0
        assert result.orphaned_privilege == 0.0


# ---------------------------------------------------------------------------
# Bare config (pure discovery mode — zero platform knowledge)
# ---------------------------------------------------------------------------
class TestBareConfig:
    def test_bare_config_no_crash(self, db):
        """Empty ClosureConfig works — engine runs with zero platform knowledge."""
        from src.score.closure import ClosureConfig, seed_pairs, compute_closure_signals

        bare = ClosureConfig()  # all defaults: empty lists/sets
        count = seed_pairs(db, bare)
        assert count == 0  # no seeded pairs

        result = compute_closure_signals(db, W1, ACTOR, config=bare)
        assert result.closure_ratio == 1.0
        assert result.orphaned_privilege == 0.0

    def test_bare_config_failsafe_still_works(self, db):
        """Even with bare config, failsafe zones create watches on unknown actions."""
        from src.score.closure import ClosureConfig, create_watch

        bare = ClosureConfig()  # failsafe_zones defaults to {"IDENTITY", "CONTROL"}
        evt = _insert_event(
            db, event_id="e-bare", ts=W1 + timedelta(minutes=1),
            window_start=W1, actor_id=ACTOR,
            action_type=ActionType.OTHER,
            target_id="unknown-resource",
            target_type=TargetType.OTHER,
            target_zone=TargetZone.IDENTITY,
        )
        created = create_watch(db, evt, config=bare)
        assert created is not None  # failsafe works even with bare config


# ---------------------------------------------------------------------------
# Orphaned privilege
# ---------------------------------------------------------------------------
class TestOrphanedPrivilege:
    def test_overdue_sa_key_scores_high(self, db):
        from src.score.closure import seed_pairs, create_watch, compute_closure_signals

        seed_pairs(db)
        evt = _insert_event(
            db, event_id="e-key", ts=W1,
            window_start=W1, actor_id=ACTOR,
            action_type=ActionType.IAM_CREATE_KEY,
            target_id=TARGET_KEY, target_type=TargetType.SA_KEY,
            target_zone=TargetZone.IDENTITY,
        )
        create_watch(db, evt)

        # 60 days later — way past 720h window
        result = compute_closure_signals(db, W1 + timedelta(days=60), ACTOR)
        assert result.orphaned_privilege > 0.0
        # sensitivity(SA_KEY) = 5.0, overdue_factor > 1.0
        assert result.orphaned_privilege >= 5.0

    def test_within_window_no_orphan_score(self, db):
        from src.score.closure import seed_pairs, create_watch, compute_closure_signals

        seed_pairs(db)
        evt = _insert_event(
            db, event_id="e-key", ts=W1,
            window_start=W1, actor_id=ACTOR,
            action_type=ActionType.IAM_CREATE_KEY,
            target_id=TARGET_KEY, target_type=TargetType.SA_KEY,
            target_zone=TargetZone.IDENTITY,
        )
        create_watch(db, evt)

        # 1 day later — still within 720h window
        result = compute_closure_signals(db, W1 + timedelta(days=1), ACTOR)
        assert result.orphaned_privilege == 0.0

    def test_closed_watch_no_orphan_score(self, db):
        from src.score.closure import seed_pairs, create_watch, try_close_watch, compute_closure_signals

        seed_pairs(db)
        evt_open = _insert_event(
            db, event_id="e-open", ts=W1,
            window_start=W1, actor_id=ACTOR,
            action_type=ActionType.IAM_CREATE_KEY,
            target_id=TARGET_KEY, target_type=TargetType.SA_KEY,
            target_zone=TargetZone.IDENTITY,
        )
        create_watch(db, evt_open)

        evt_close = _insert_event(
            db, event_id="e-close", ts=W1 + timedelta(hours=1),
            window_start=W1, actor_id=ACTOR,
            action_type=ActionType.IAM_DELETE_KEY,
            target_id=TARGET_KEY, target_type=TargetType.SA_KEY,
            target_zone=TargetZone.IDENTITY,
        )
        try_close_watch(db, evt_close)

        # 60 days later — but it's closed, so no orphan score
        result = compute_closure_signals(db, W1 + timedelta(days=60), ACTOR)
        assert result.orphaned_privilege == 0.0
