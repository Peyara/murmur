"""Tests for the parameterized attack trajectory generator (Sprint 2 Phase 1)."""

from pathlib import Path

import duckdb
import pytest

from src.ingest.dedup import insert_event
from src.schema import (
    ActionType,
    ActorType,
    ProvenanceLevel,
    TargetZone,
)
from src.validation.attack_generator import (
    SPEED_INTERVALS,
    AttackParams,
    AttackTrajectory,
    generate_attack,
)

SCHEMA_PATH = Path(__file__).parent.parent / "sql" / "schema.sql"


def _params(**overrides) -> AttackParams:
    base = dict(
        speed="fast",
        spread="single_actor",
        zone_path="direct",
        evasion="none",
        closure="none",
        objective="secret_access",
    )
    base.update(overrides)
    return AttackParams(**base)


class TestGenerateAttackBasics:
    def test_returns_attack_trajectory(self):
        traj = generate_attack(_params(), seed=0)
        assert isinstance(traj, AttackTrajectory)
        assert len(traj.events) >= 2
        assert traj.params == _params()
        assert traj.seed == 0

    def test_canonical_events_well_typed(self):
        traj = generate_attack(_params(), seed=0)
        for e in traj.events:
            assert isinstance(e.action_type, ActionType)
            assert isinstance(e.target_zone, TargetZone)
            assert isinstance(e.actor_type, ActorType)
            assert e.event_id.startswith("synthetic_")
            assert e.project_id == "synth-project"
            assert e.actor_id.endswith("@synth-project.iam.gserviceaccount.com")

    def test_window_start_aligned_to_15min(self):
        traj = generate_attack(_params(), seed=0)
        for e in traj.events:
            assert e.window_start.minute % 15 == 0
            assert e.window_start.second == 0
            assert e.window_start.microsecond == 0


class TestZonePath:
    def test_direct_secret_access_path(self):
        traj = generate_attack(_params(zone_path="direct", objective="secret_access"), seed=0)
        assert traj.expected_zone_path == [TargetZone.IDENTITY, TargetZone.SECRET]

    def test_indirect_path_includes_data(self):
        traj = generate_attack(_params(zone_path="indirect", objective="secret_access"), seed=0)
        assert traj.expected_zone_path == [TargetZone.IDENTITY, TargetZone.DATA, TargetZone.SECRET]

    def test_full_chain_includes_control_and_exfil(self):
        traj = generate_attack(_params(zone_path="full_chain", objective="key_exfil"), seed=0)
        assert TargetZone.CONTROL in traj.expected_zone_path
        assert TargetZone.EXFIL_RISK in traj.expected_zone_path

    def test_first_n_events_match_zone_path(self):
        # With evasion=none, opens-then-closes ordering, the first N events
        # (where N = path length) follow the declared zone path.
        traj = generate_attack(_params(zone_path="indirect", objective="data_exfil"), seed=0)
        n = len(traj.expected_zone_path)
        assert [e.target_zone for e in traj.events[:n]] == traj.expected_zone_path


class TestTimestamps:
    def test_timestamps_strictly_ordered(self):
        for speed in ("slow", "medium", "fast"):
            traj = generate_attack(_params(speed=speed), seed=0)
            ts_list = [e.ts for e in traj.events]
            assert ts_list == sorted(ts_list), f"unsorted for speed={speed}"

    @pytest.mark.parametrize("speed", ["slow", "medium", "fast"])
    def test_speed_intervals_within_band(self, speed):
        # full_chain key_exfil ensures multiple events to compute median gap from.
        traj = generate_attack(
            _params(speed=speed, evasion="none", zone_path="full_chain", objective="key_exfil"),
            seed=1,
        )
        gaps = [
            (traj.events[i + 1].ts - traj.events[i].ts).total_seconds()
            for i in range(len(traj.events) - 1)
        ]
        median_gap = sorted(gaps)[len(gaps) // 2]
        expected = SPEED_INTERVALS[speed]
        # Constant intervals (no jitter); median gap should equal expected.
        assert abs(median_gap - expected) < 1.0, (
            f"speed={speed}: median gap {median_gap}s, expected {expected}s"
        )


class TestDeterminism:
    def test_same_params_seed_produces_same_trajectory(self):
        t1 = generate_attack(_params(), seed=42)
        t2 = generate_attack(_params(), seed=42)
        assert len(t1.events) == len(t2.events)
        for e1, e2 in zip(t1.events, t2.events, strict=True):
            assert e1.event_id == e2.event_id
            assert e1.actor_id == e2.actor_id
            assert e1.action_type == e2.action_type
            assert e1.target_zone == e2.target_zone
            assert e1.ts == e2.ts
            assert e1.trigger_ref == e2.trigger_ref

    def test_different_seed_diverges(self):
        t1 = generate_attack(_params(zone_path="full_chain", objective="key_exfil"), seed=1)
        t2 = generate_attack(_params(zone_path="full_chain", objective="key_exfil"), seed=2)
        # At minimum, the first event_id collides (deterministic format), but
        # at least one actor_id or trigger_ref should differ.
        differs = any(
            e1.actor_id != e2.actor_id or e1.trigger_ref != e2.trigger_ref
            for e1, e2 in zip(t1.events, t2.events, strict=True)
        )
        assert differs


class TestEvasion:
    def test_pattern_mimicry_uses_benign_trigger_ref(self):
        traj = generate_attack(_params(evasion="pattern_mimicry"), seed=0)
        for e in traj.events:
            assert e.trigger_ref is not None
            assert "synth-project" in e.trigger_ref
            assert "/jobs/" in e.trigger_ref
            assert "forged" not in e.trigger_ref
            assert e.provenance_level == ProvenanceLevel.WEAK

    def test_split_actions_spans_multiple_windows(self):
        traj = generate_attack(
            _params(evasion="split_actions", zone_path="full_chain", objective="key_exfil"),
            seed=0,
        )
        windows = {e.window_start for e in traj.events}
        assert len(windows) >= 2

    def test_timing_jitter_perturbs_intervals(self):
        baseline = generate_attack(_params(speed="medium", evasion="none"), seed=5)
        jittered = generate_attack(_params(speed="medium", evasion="timing_jitter"), seed=5)
        # Jitter should produce non-uniform gaps; baseline should be uniform.
        baseline_gaps = [
            (baseline.events[i + 1].ts - baseline.events[i].ts).total_seconds()
            for i in range(len(baseline.events) - 1)
        ]
        jittered_gaps = [
            (jittered.events[i + 1].ts - jittered.events[i].ts).total_seconds()
            for i in range(len(jittered.events) - 1)
        ]
        if len(baseline_gaps) > 1:
            assert max(baseline_gaps) - min(baseline_gaps) < 2.0
        # With jitter, gaps should vary noticeably for a non-trivial-length traj.
        if len(jittered_gaps) > 2:
            assert max(jittered_gaps) - min(jittered_gaps) > 1.0


class TestClosure:
    def test_closure_full_balances_iam_creates(self):
        traj = generate_attack(
            _params(zone_path="direct", objective="key_exfil", closure="full"),
            seed=0,
        )
        creates = sum(1 for e in traj.events if e.action_type == ActionType.IAM_CREATE_KEY)
        deletes = sum(1 for e in traj.events if e.action_type == ActionType.IAM_DELETE_KEY)
        if creates > 0:
            assert deletes == creates

    def test_closure_none_has_no_delete_keys(self):
        traj = generate_attack(
            _params(zone_path="full_chain", objective="key_exfil", closure="none"),
            seed=0,
        )
        deletes = sum(1 for e in traj.events if e.action_type == ActionType.IAM_DELETE_KEY)
        assert deletes == 0


class TestSpread:
    def test_single_actor_uses_one_actor(self):
        traj = generate_attack(_params(spread="single_actor"), seed=0)
        actors = {e.actor_id for e in traj.events}
        assert len(actors) == 1

    def test_multi_actor_uses_2_to_4_distinct_actors(self):
        traj = generate_attack(
            _params(zone_path="full_chain", objective="key_exfil", spread="multi_actor"),
            seed=7,
        )
        actors = {e.actor_id for e in traj.events}
        assert 2 <= len(actors) <= 4


class TestExpectedSignals:
    def test_novelty_always_predicted(self):
        traj = generate_attack(_params(), seed=0)
        assert "novelty_score" in traj.expected_signals

    def test_bridge_predicted_for_multi_zone_no_split(self):
        traj = generate_attack(_params(zone_path="indirect"), seed=0)
        assert "bridge_new" in traj.expected_signals

    def test_bridge_not_predicted_for_split_actions(self):
        traj = generate_attack(_params(zone_path="indirect", evasion="split_actions"), seed=0)
        assert "bridge_new" not in traj.expected_signals

    def test_closure_predicted_when_closure_none(self):
        traj = generate_attack(
            _params(zone_path="full_chain", objective="key_exfil", closure="none"),
            seed=0,
        )
        assert "closure_gap" in traj.expected_signals
        assert "orphaned_priv" in traj.expected_signals


class TestDuckDBInjection:
    def test_trajectory_inserts_into_memory_db(self):
        db = duckdb.connect(":memory:")
        try:
            db.execute(SCHEMA_PATH.read_text())
            traj = generate_attack(
                _params(zone_path="full_chain", objective="key_exfil"),
                seed=3,
            )
            for e in traj.events:
                inserted = insert_event(db, e)
                assert inserted is True
            count = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            assert count == len(traj.events)
        finally:
            db.close()
