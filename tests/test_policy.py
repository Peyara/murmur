"""Tests for the policy layer — risk energy and shadow bandit."""

from datetime import datetime, timedelta

from src.schema import ActionType, TargetType, TargetZone
from src.ingest.dedup import insert_event
from tests.conftest import make_event

W1 = datetime(2026, 3, 25, 10, 0, 0)
ACTOR = "test-sa@project.iam.gserviceaccount.com"


class TestRiskEnergy:
    def test_high_risk_alert_high(self, db):
        from src.policy.energy import risk_energy

        state = risk_energy(
            fusion_raw=0.9, residual_risk=0.85,
            closure_ratio=0.2, orphaned_privilege=15.0,
        )
        assert state.alert_level == "ALERT_HIGH"
        assert state.risk_energy > 8.0

    def test_medium_risk_alert_med(self, db):
        from src.policy.energy import risk_energy

        state = risk_energy(
            fusion_raw=0.5, residual_risk=0.45,
            closure_ratio=0.5, orphaned_privilege=5.0,
        )
        assert state.alert_level == "ALERT_MED"
        assert 5.0 < state.risk_energy <= 8.0

    def test_low_risk_watch(self, db):
        from src.policy.energy import risk_energy

        state = risk_energy(
            fusion_raw=0.35, residual_risk=0.30,
            closure_ratio=0.5, orphaned_privilege=5.0,
        )
        assert state.alert_level == "WATCH"
        assert 3.0 < state.risk_energy <= 5.0

    def test_normal_risk(self, db):
        from src.policy.energy import risk_energy

        state = risk_energy(
            fusion_raw=0.03, residual_risk=0.02,
            closure_ratio=1.0, orphaned_privilege=0.0,
        )
        assert state.alert_level == "NORMAL"
        assert state.risk_energy <= 3.0

    def test_clean_closure_reduces_energy(self, db):
        """High closure_ratio (clean) should produce lower risk_energy than low."""
        from src.policy.energy import risk_energy

        dirty = risk_energy(fusion_raw=0.4, residual_risk=0.35, closure_ratio=0.1, orphaned_privilege=10.0)
        clean = risk_energy(fusion_raw=0.4, residual_risk=0.35, closure_ratio=1.0, orphaned_privilege=0.0)
        assert clean.risk_energy < dirty.risk_energy


class TestShadowBandit:
    def test_suggest_isolate_for_high(self, db):
        from src.policy.bandit import suggest_action
        from src.policy.state import PolicyState

        state = PolicyState(
            alert_level="ALERT_HIGH", risk_energy=9.0,
            fusion_raw=0.9, residual_risk=0.85,
            closure_ratio=0.2, orphaned_privilege=10.0,
        )
        action = suggest_action(state)
        assert action == "ISOLATE_ACTOR"

    def test_suggest_review_for_medium(self, db):
        from src.policy.bandit import suggest_action
        from src.policy.state import PolicyState

        state = PolicyState(
            alert_level="ALERT_MED", risk_energy=6.0,
            fusion_raw=0.5, residual_risk=0.45,
            closure_ratio=0.5, orphaned_privilege=5.0,
        )
        action = suggest_action(state)
        assert action == "REQUEST_REVIEW"

    def test_suggest_monitor_for_watch(self, db):
        from src.policy.bandit import suggest_action
        from src.policy.state import PolicyState

        state = PolicyState(
            alert_level="WATCH", risk_energy=4.0,
            fusion_raw=0.2, residual_risk=0.18,
            closure_ratio=0.8, orphaned_privilege=2.0,
        )
        action = suggest_action(state)
        assert action == "INCREASE_MONITORING"

    def test_no_suggestion_for_normal(self, db):
        from src.policy.bandit import suggest_action
        from src.policy.state import PolicyState

        state = PolicyState(
            alert_level="NORMAL", risk_energy=1.0,
            fusion_raw=0.03, residual_risk=0.02,
            closure_ratio=1.0, orphaned_privilege=0.0,
        )
        action = suggest_action(state)
        assert action is None

    def test_log_suggestion(self, db):
        from src.policy.bandit import log_suggestion
        from src.policy.state import PolicyState

        state = PolicyState(
            alert_level="ALERT_HIGH", risk_energy=9.0,
            fusion_raw=0.9, residual_risk=0.85,
            closure_ratio=0.2, orphaned_privilege=10.0,
        )
        log_suggestion(db, W1, ACTOR, state, "ISOLATE_ACTOR")

        row = db.execute(
            "SELECT alert_level, suggested_action FROM policy_suggestions WHERE actor_id = ?",
            [ACTOR],
        ).fetchone()
        assert row is not None
        assert row[0] == "ALERT_HIGH"
        assert row[1] == "ISOLATE_ACTOR"
