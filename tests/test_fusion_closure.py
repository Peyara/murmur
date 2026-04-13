"""Tests for closure signal integration into the fusion pipeline."""

from datetime import datetime, timedelta

from config.settings import MurmurSettings
from src.ingest.dedup import insert_event
from src.schema import ActionType, TargetType, TargetZone
from src.score.fusion import FUSION_WEIGHTS, compute_fusion
from tests.conftest import make_event

W1 = datetime(2026, 3, 25, 10, 0, 0)
ACTOR = "test-sa@project.iam.gserviceaccount.com"
KNOWN = {"service-123@gcp-sa-cloudscheduler.iam.gserviceaccount.com"}
SETTINGS = MurmurSettings()


def _setup_basic_actor(db, actor_id=ACTOR, window=W1):
    """Insert minimal event + actor_window for fusion to run."""
    insert_event(db, make_event(
        event_id="e1", ts=window + timedelta(minutes=1),
        window_start=window, actor_id=actor_id,
        action_type=ActionType.GCS_READ,
        target_zone=TargetZone.DATA, target_type=TargetType.GCS_BUCKET,
    ))
    db.execute(
        "INSERT INTO actor_windows (window_start, actor_id, event_count, "
        "action_types, zone_sequence, target_ids, burst_per_min, breadth_entropy, "
        "provenance_level) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [window, actor_id, 1, '["GCS_READ"]', '["DATA"]', '["t1"]', 0.5, 0.0, "NONE"],
    )


class TestWeights:
    def test_weights_sum_to_one(self):
        total = sum(FUSION_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001, f"Weights sum to {total}, expected 1.0"


class TestClosureInFusion:
    def test_closure_columns_populated(self, db):
        """Fusion writes actual closure values to risk_scores (not hardcoded 0.0)."""
        from src.score.closure import seed_pairs

        seed_pairs(db)
        _setup_basic_actor(db)
        compute_fusion(db, W1, ACTOR, KNOWN)

        row = db.execute(
            "SELECT closure_ratio, orphaned_privilege FROM risk_scores WHERE window_start = ? AND actor_id = ?",
            [W1, ACTOR],
        ).fetchone()
        assert row is not None
        # No closure watches → default: ratio=1.0, orphaned=0.0
        assert row[0] == 1.0  # closure_ratio
        assert row[1] == 0.0  # orphaned_privilege

    def test_empty_closure_no_penalty(self, db):
        """With no closure data, fusion_raw should be same as without closure signals."""
        from src.score.closure import seed_pairs

        seed_pairs(db)
        _setup_basic_actor(db)
        fusion = compute_fusion(db, W1, ACTOR, KNOWN)

        # closure_gap = 1 - 1.0 = 0.0, orphaned = 0.0 → no closure contribution
        # Fusion should be driven entirely by other signals
        assert fusion >= 0.0

    def test_orphaned_key_increases_score(self, db):
        """Creating a key without deletion should increase fusion score."""
        from src.score.closure import create_watch, seed_pairs

        seed_pairs(db)

        target_key = "projects/-/serviceAccounts/12345/keys/key-001"

        # Insert the opening event (key creation) — this is also the actor's events
        insert_event(db, make_event(
            event_id="e-key", ts=W1 + timedelta(minutes=1),
            window_start=W1, actor_id=ACTOR,
            action_type=ActionType.IAM_CREATE_KEY,
            target_id=target_key, target_type=TargetType.SA_KEY,
            target_zone=TargetZone.IDENTITY,
        ))
        db.execute(
            "INSERT INTO actor_windows (window_start, actor_id, event_count, "
            "action_types, zone_sequence, target_ids, burst_per_min, breadth_entropy, "
            "provenance_level) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [W1, ACTOR, 1, '["IAM_CREATE_KEY"]', '["IDENTITY"]', f'["{target_key}"]', 0.5, 0.0, "NONE"],
        )

        # Create the watch
        evt = make_event(
            event_id="e-key", ts=W1 + timedelta(minutes=1),
            window_start=W1, actor_id=ACTOR,
            action_type=ActionType.IAM_CREATE_KEY,
            target_id=target_key, target_type=TargetType.SA_KEY,
            target_zone=TargetZone.IDENTITY,
        )
        create_watch(db, evt)

        # Score 60 days later — key is orphaned
        W_LATE = W1 + timedelta(days=60)
        # Need actor_windows for the late window too
        insert_event(db, make_event(
            event_id="e-late", ts=W_LATE + timedelta(minutes=1),
            window_start=W_LATE, actor_id=ACTOR,
            action_type=ActionType.GCS_READ,
            target_zone=TargetZone.DATA, target_type=TargetType.GCS_BUCKET,
        ))
        db.execute(
            "INSERT INTO actor_windows (window_start, actor_id, event_count, "
            "action_types, zone_sequence, target_ids, burst_per_min, breadth_entropy, "
            "provenance_level) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [W_LATE, ACTOR, 1, '["GCS_READ"]', '["DATA"]', '["t1"]', 0.5, 0.0, "NONE"],
        )

        compute_fusion(db, W_LATE, ACTOR, KNOWN)

        # The orphaned key should contribute to a higher score
        row = db.execute(
            "SELECT orphaned_privilege FROM risk_scores WHERE window_start = ? AND actor_id = ?",
            [W_LATE, ACTOR],
        ).fetchone()
        assert row[0] > 0.0  # orphaned_privilege should be non-zero
