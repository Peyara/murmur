"""Tests for provenance residual risk computation."""

import json
from datetime import datetime, timedelta

from config.settings import MurmurSettings
from src.ingest.dedup import insert_event
from src.provenance.patterns import register_pattern
from src.provenance.residual import compute_residual_risk
from src.schema import ProvenanceLevel
from tests.conftest import make_event

W1 = datetime(2026, 3, 25, 10, 0, 0)  # Wednesday
KNOWN = {"service-123@gcp-sa-cloudscheduler.iam.gserviceaccount.com"}
SETTINGS = MurmurSettings()


def _setup_scored_actor(db, actor_id="sa@proj", fusion_raw=0.5,
                        provenance_level="WEAK", trigger_ref="sched:job:123",
                        zone_sequence=None):
    """Insert event, actor_window, and risk_score for testing."""
    if zone_sequence is None:
        zone_sequence = ["SECRET", "DATA"]

    prov_enum = ProvenanceLevel(provenance_level)
    insert_event(db, make_event(
        event_id="e1", ts=W1 + timedelta(minutes=1),
        window_start=W1, actor_id=actor_id,
        provenance_level=prov_enum,
        trigger_ref=trigger_ref,
    ))
    db.execute(
        "INSERT INTO actor_windows (window_start, actor_id, event_count, "
        "action_types, zone_sequence, target_ids, burst_per_min, breadth_entropy, "
        "provenance_level) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [W1, actor_id, 3, '["GCS_READ"]', json.dumps(zone_sequence),
         '["t1"]', 1.0, 0.0, provenance_level],
    )
    db.execute(
        "INSERT INTO risk_scores (window_start, actor_id, fusion_raw, residual_risk) "
        "VALUES (?, ?, ?, ?)",
        [W1, actor_id, fusion_raw, fusion_raw],
    )


class TestNoDiscount:
    def test_none_provenance(self, db):
        """NONE provenance -> residual = fusion_raw (multiplier = 0.0)."""
        _setup_scored_actor(db, provenance_level="NONE", trigger_ref=None)
        result = compute_residual_risk(db, W1, "sa@proj", 0.5, KNOWN, SETTINGS)
        assert result == 0.5  # no discount

    def test_no_pattern_match(self, db):
        """No registered patterns -> score=0 -> residual = fusion_raw."""
        _setup_scored_actor(db)
        result = compute_residual_risk(db, W1, "sa@proj", 0.5, KNOWN, SETTINGS)
        assert result == 0.5  # no pattern to match


class TestWeakProvenance:
    def test_weak_with_pattern_match(self, db):
        """WEAK provenance + pattern match -> residual < fusion_raw."""
        _setup_scored_actor(db, zone_sequence=["SECRET", "DATA", "DATA"])
        register_pattern(
            db, name="worker", description="",
            initiator_type="SCHEDULED",
            expected_actors=["sa@proj"],
            expected_zones=["SECRET", "DATA", "DATA"],
            expected_window=None, rate_min=1, rate_max=10, expected_duration=15,
        )
        result = compute_residual_risk(db, W1, "sa@proj", 0.5, KNOWN, SETTINGS)
        assert result < 0.5

    def test_weak_chain_resolved_stronger_discount(self, db):
        """WEAK + chain resolved gets boosted multiplier (0.8 vs 0.6)."""
        _setup_scored_actor(db, zone_sequence=["SECRET", "DATA", "DATA"])
        register_pattern(
            db, name="worker", description="",
            initiator_type="SCHEDULED",
            expected_actors=["sa@proj"],
            expected_zones=["SECRET", "DATA", "DATA"],
            expected_window=None, rate_min=1, rate_max=10, expected_duration=15,
        )
        # With chain resolved (scheduler trigger + known initiator)
        result_resolved = compute_residual_risk(db, W1, "sa@proj", 0.5, KNOWN, SETTINGS)

        # Without chain resolved (empty known_initiators)
        # Reset residual_risk
        db.execute("UPDATE risk_scores SET residual_risk = 0.5 WHERE window_start = ? AND actor_id = ?",
                   [W1, "sa@proj"])
        result_unresolved = compute_residual_risk(db, W1, "sa@proj", 0.5, set(), SETTINGS)

        assert result_resolved < result_unresolved

    def test_weak_chain_not_resolved(self, db):
        """WEAK + chain NOT resolved -> standard multiplier 0.6."""
        _setup_scored_actor(db, zone_sequence=["SECRET", "DATA", "DATA"])
        register_pattern(
            db, name="worker", description="",
            initiator_type="SCHEDULED",
            expected_actors=["sa@proj"],
            expected_zones=["SECRET", "DATA", "DATA"],
            expected_window=None, rate_min=1, rate_max=10, expected_duration=15,
        )
        result = compute_residual_risk(db, W1, "sa@proj", 0.5, set(), SETTINGS)
        # discount = match_score * 0.6 (WEAK, not resolved)
        # residual = 0.5 * (1 - 0.3 * match_score * 0.6)
        assert result < 0.5
        assert result > 0.5 * 0.7  # can't be discounted more than 30%


class TestStrongProvenance:
    def test_strong_with_pattern(self, db):
        """STRONG provenance -> full multiplier 1.0."""
        _setup_scored_actor(db, provenance_level="STRONG",
                            zone_sequence=["SECRET", "DATA", "DATA"])
        register_pattern(
            db, name="worker", description="",
            initiator_type="SCHEDULED",
            expected_actors=["sa@proj"],
            expected_zones=["SECRET", "DATA", "DATA"],
            expected_window=None, rate_min=1, rate_max=10, expected_duration=15,
        )
        result = compute_residual_risk(db, W1, "sa@proj", 0.5, KNOWN, SETTINGS)
        assert result < 0.5


class TestHandCalculated:
    def test_exact_formula(self, db):
        """Verify formula: residual = fusion * (1 - penalty_weight * match * multiplier)."""
        _setup_scored_actor(db, zone_sequence=["SECRET", "DATA", "DATA"])
        register_pattern(
            db, name="worker", description="",
            initiator_type="SCHEDULED",
            expected_actors=["sa@proj"],
            expected_zones=["SECRET", "DATA", "DATA"],
            expected_window=None, rate_min=1, rate_max=10, expected_duration=15,
        )
        result = compute_residual_risk(db, W1, "sa@proj", 0.5, KNOWN, SETTINGS)

        # Pattern match should be high: actor=1.0, zone=1.0, time=1.0, rate=1.0 → score=1.0
        # Provenance WEAK + chain resolved → multiplier 0.8
        # discount = 1.0 * 0.8 = 0.8
        # residual = 0.5 * (1 - 0.3 * 0.8) = 0.5 * 0.76 = 0.38
        assert abs(result - 0.38) < 0.01


class TestDBUpdates:
    def test_updates_risk_scores(self, db):
        """compute_residual_risk updates risk_scores.residual_risk."""
        _setup_scored_actor(db, zone_sequence=["SECRET", "DATA", "DATA"])
        register_pattern(
            db, name="worker", description="",
            initiator_type="SCHEDULED",
            expected_actors=["sa@proj"],
            expected_zones=["SECRET", "DATA", "DATA"],
            expected_window=None, rate_min=1, rate_max=10, expected_duration=15,
        )
        compute_residual_risk(db, W1, "sa@proj", 0.5, KNOWN, SETTINGS)

        row = db.execute(
            "SELECT residual_risk FROM risk_scores WHERE window_start = ? AND actor_id = ?",
            [W1, "sa@proj"],
        ).fetchone()
        assert row[0] < 0.5

    def test_updates_actor_windows(self, db):
        """compute_residual_risk updates pattern_match_score in actor_windows."""
        _setup_scored_actor(db, zone_sequence=["SECRET", "DATA", "DATA"])
        register_pattern(
            db, name="worker", description="",
            initiator_type="SCHEDULED",
            expected_actors=["sa@proj"],
            expected_zones=["SECRET", "DATA", "DATA"],
            expected_window=None, rate_min=1, rate_max=10, expected_duration=15,
        )
        compute_residual_risk(db, W1, "sa@proj", 0.5, KNOWN, SETTINGS)

        row = db.execute(
            "SELECT pattern_match_score, matched_pattern_id, trigger_chain_resolved "
            "FROM actor_windows WHERE window_start = ? AND actor_id = ?",
            [W1, "sa@proj"],
        ).fetchone()
        assert row[0] > 0.8  # high match
        assert row[1] is not None  # pattern_id
        assert row[2] is True  # chain resolved
