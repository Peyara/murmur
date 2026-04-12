"""Tests for closure auto-discovery — pair mining and promotion."""

from datetime import datetime, timedelta

from src.ingest.dedup import insert_event
from src.schema import ActionType, TargetType, TargetZone
from tests.conftest import make_event

W1 = datetime(2026, 3, 25, 10, 0, 0)
ACTOR = "test-sa@project.iam.gserviceaccount.com"


def _insert_event(db, **overrides):
    evt = make_event(**overrides)
    insert_event(db, evt)
    return evt


def _create_open_close_sequence(db, target_id, open_type, close_type, count, base_ts=W1):
    """Create N open-close sequences on the same target across different times."""
    for i in range(count):
        t = base_ts + timedelta(days=i)
        _insert_event(
            db, event_id=f"e-open-{i}", ts=t,
            window_start=t, actor_id=ACTOR,
            action_type=open_type,
            target_id=f"{target_id}-{i}",  # different resource instances
            target_type=TargetType.SERVICE_ACCOUNT,
            target_zone=TargetZone.IDENTITY,
        )
        _insert_event(
            db, event_id=f"e-close-{i}", ts=t + timedelta(hours=2),
            window_start=t, actor_id=ACTOR,
            action_type=close_type,
            target_id=f"{target_id}-{i}",
            target_type=TargetType.SERVICE_ACCOUNT,
            target_zone=TargetZone.IDENTITY,
        )


class TestMineCandidates:
    def test_discovers_recurring_pattern(self, db):
        """Repeated (open, close) on same target_id type → candidate pair."""
        from src.score.closure import mine_candidate_pairs

        # Create 6 instances of IAM_CREATE_SA → DeleteSA pattern
        _create_open_close_sequence(
            db, "projects/-/sa/test",
            ActionType.IAM_CREATE_SA, ActionType.OTHER,  # using OTHER as proxy for delete
            count=6,
        )
        candidates = mine_candidate_pairs(db, lookback_days=30)
        # Should find at least one candidate: IAM_CREATE_SA → OTHER
        opening_types = [c["opening_action_type"] for c in candidates]
        assert "IAM_CREATE_SA" in opening_types

    def test_ignores_data_zone(self, db):
        """Events in DATA zone should not produce candidates."""
        from src.score.closure import mine_candidate_pairs

        for i in range(10):
            t = W1 + timedelta(days=i)
            _insert_event(
                db, event_id=f"e-read-{i}", ts=t,
                window_start=t, actor_id=ACTOR,
                action_type=ActionType.GCS_READ,
                target_id=f"bucket/obj-{i}",
                target_type=TargetType.GCS_BUCKET,
                target_zone=TargetZone.DATA,
            )
            _insert_event(
                db, event_id=f"e-write-{i}", ts=t + timedelta(hours=1),
                window_start=t, actor_id=ACTOR,
                action_type=ActionType.GCS_WRITE,
                target_id=f"bucket/obj-{i}",
                target_type=TargetType.GCS_BUCKET,
                target_zone=TargetZone.DATA,
            )
        candidates = mine_candidate_pairs(db, lookback_days=30)
        # No candidates from DATA zone
        assert len(candidates) == 0

    def test_insufficient_observations_no_candidate(self, db):
        """Fewer than min_observations → no candidate returned."""
        from src.score.closure import mine_candidate_pairs

        # Only 2 instances — below threshold
        _create_open_close_sequence(
            db, "projects/-/sa/sparse",
            ActionType.IAM_CREATE_SA, ActionType.OTHER,
            count=2,
        )
        candidates = mine_candidate_pairs(db, lookback_days=30, min_observations=5)
        assert len(candidates) == 0


class TestPromoteCandidates:
    def test_promotes_qualified_candidates(self, db):
        """Candidates with enough observations get inserted into opening_closing_pairs."""
        from src.score.closure import mine_candidate_pairs, promote_candidates, seed_pairs

        seed_pairs(db)
        _create_open_close_sequence(
            db, "projects/-/sa/promo",
            ActionType.IAM_SET_POLICY, ActionType.OTHER,
            count=6,
        )
        mine_candidate_pairs(db, lookback_days=30)
        promoted = promote_candidates(db, min_observations=5)
        assert promoted >= 1

        # Check it's in opening_closing_pairs with tier=2
        row = db.execute(
            "SELECT tier FROM opening_closing_pairs WHERE opening_action_type = 'IAM_SET_POLICY' AND tier = 2"
        ).fetchone()
        assert row is not None

    def test_does_not_promote_below_threshold(self, db):
        """Candidates below min_observations stay as candidates."""
        from src.score.closure import mine_candidate_pairs, promote_candidates, seed_pairs

        seed_pairs(db)
        _create_open_close_sequence(
            db, "projects/-/sa/low",
            ActionType.IAM_SET_POLICY, ActionType.OTHER,
            count=3,
        )
        mine_candidate_pairs(db, lookback_days=30)
        promoted = promote_candidates(db, min_observations=5)
        assert promoted == 0


class TestDiscoveryOnlyCloses:
    def test_discovered_pair_closes_watch(self, db):
        """A promoted discovered pair can close an existing watch."""
        from src.score.closure import (
            create_watch,
            mine_candidate_pairs,
            promote_candidates,
            seed_pairs,
            try_close_watch,
        )

        seed_pairs(db)

        # Create pattern: IAM_SET_POLICY → OTHER (6 instances to auto-promote)
        _create_open_close_sequence(
            db, "projects/-/sa/disc",
            ActionType.IAM_SET_POLICY, ActionType.OTHER,
            count=6,
        )
        mine_candidate_pairs(db, lookback_days=30)
        promote_candidates(db, min_observations=5)

        # Now open a NEW watch for IAM_SET_POLICY
        evt_open = _insert_event(
            db, event_id="e-new-open", ts=W1 + timedelta(days=10),
            window_start=W1 + timedelta(days=10), actor_id=ACTOR,
            action_type=ActionType.IAM_SET_POLICY,
            target_id="projects/-/sa/new-target",
            target_type=TargetType.SERVICE_ACCOUNT,
            target_zone=TargetZone.IDENTITY,
        )
        create_watch(db, evt_open)

        # The discovered closing type (OTHER) should close it
        evt_close = _insert_event(
            db, event_id="e-new-close", ts=W1 + timedelta(days=10, hours=1),
            window_start=W1 + timedelta(days=10), actor_id=ACTOR,
            action_type=ActionType.OTHER,
            target_id="projects/-/sa/new-target",
            target_type=TargetType.SERVICE_ACCOUNT,
            target_zone=TargetZone.IDENTITY,
        )
        closed = try_close_watch(db, evt_close)
        assert closed is True

    def test_discovery_never_creates_new_opening_type(self, db):
        """Discovery only adds closing types to pairs table, never new opening types."""
        from config.settings import SETTINGS
        from src.score.closure import mine_candidate_pairs, promote_candidates, seed_pairs

        config = SETTINGS.closure
        seed_pairs(db, config)
        opening_types_before = set(config.opening_types)

        _create_open_close_sequence(
            db, "projects/-/sa/safe",
            ActionType.IAM_SET_POLICY, ActionType.OTHER,
            count=6,
        )
        mine_candidate_pairs(db, lookback_days=30, config=config)
        promote_candidates(db, min_observations=5)
        # Config opening_types should not have been mutated
        assert config.opening_types == opening_types_before
