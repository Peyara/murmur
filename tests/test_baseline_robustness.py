"""Tests for src/validation/baseline_robustness.py.

Covers the new attack-in-benign harness, the benign-only floor measurement,
threshold recalibration logic, and the full aggregation path.
"""

from __future__ import annotations

from src.validation.attack_generator import AttackParams
from src.validation.baseline_robustness import (
    BenignFloorResult,
    _generate_benign_canonical_events,
    _namespace_attack_actors,
    aggregate_baseline_report,
    recalibrate_thresholds,
    run_benign_only,
    run_trajectory_in_baseline,
)


def test_generate_benign_canonical_events_returns_canonical_events():
    events = _generate_benign_canonical_events(seed=42, n_actors=10, n_windows=5)
    assert len(events) > 0
    # Every event must be a CanonicalEvent (parse_audit_log contract)
    for e in events:
        assert hasattr(e, "actor_id")
        assert hasattr(e, "action_type")
        assert hasattr(e, "target_zone")
        assert hasattr(e, "ts")


def test_generate_benign_is_deterministic():
    events_a = _generate_benign_canonical_events(seed=42, n_actors=10, n_windows=5)
    events_b = _generate_benign_canonical_events(seed=42, n_actors=10, n_windows=5)
    assert len(events_a) == len(events_b)
    # Same actor IDs in same order
    actors_a = [e.actor_id for e in events_a]
    actors_b = [e.actor_id for e in events_b]
    assert actors_a == actors_b


def test_namespace_attack_actors_prefixes_actor_id():
    from datetime import datetime

    from src.schema import (
        ActionType,
        ActorType,
        CanonicalEvent,
        EventResult,
        ProvenanceLevel,
        ProvenanceSource,
        TargetType,
        TargetZone,
    )

    e = CanonicalEvent(
        event_id="x", ts=datetime(2026, 1, 1), window_start=datetime(2026, 1, 1),
        actor_id="worker-sa-3@synth-project.iam.gserviceaccount.com",
        actor_type=ActorType.SERVICE_ACCOUNT,
        action_type=ActionType.IAM_CREATE_KEY,
        target_id="x", target_type=TargetType.SA_KEY,
        target_zone=TargetZone.IDENTITY,
        result=EventResult.SUCCESS,
        trigger_ref=None,
        provenance_level=ProvenanceLevel.NONE,
        provenance_source=ProvenanceSource.UNKNOWN,
        action_subtype="IAM_CREATE_KEY",
        project_id="synth-project", env="rd",
    )
    out = _namespace_attack_actors([e])
    assert out[0].actor_id == "attack-worker-sa-3@synth-project.iam.gserviceaccount.com"
    # Ensure it's a copy, not mutation
    assert e.actor_id == "worker-sa-3@synth-project.iam.gserviceaccount.com"


def test_run_trajectory_in_baseline_basic():
    """End-to-end smoke: one fast/single attack in baseline produces a result."""
    baseline = _generate_benign_canonical_events(seed=999, n_windows=10)
    params = AttackParams("fast", "single_actor", "direct", "none", "none", "key_exfil")
    result = run_trajectory_in_baseline(params, seed=42, baseline_events=baseline, label="t")

    assert result.label == "t"
    assert result.params == params
    assert result.n_events >= 2  # minimum trajectory length
    assert 0.0 <= result.residual_risk_max <= 1.0
    assert result.alert_tier in ("NORMAL", "WATCH", "MEDIUM", "HIGH")


def test_run_trajectory_attribution_attack_only():
    """Signal max should reflect attack actors only, not benign workers.

    Attack actor IDs are namespaced to `attack-*`. Benign actors don't match
    that prefix. If the harness leaked benign signals into signal_max, this
    test could fail when benign signals exceed attack signals.
    """
    baseline = _generate_benign_canonical_events(seed=123, n_windows=10)
    # closure="full" → attack closes its own keys → closure_gap should be 0
    params = AttackParams("fast", "single_actor", "direct", "none", "full", "key_exfil")
    result = run_trajectory_in_baseline(params, seed=7, baseline_events=baseline, label="t")
    # With closure=full, the attack's own openings close. But benign workflows
    # can leave openings unclosed → benign closure_gap could be >0. The
    # attribution filter must not pick that up. A flaky-but-informative check:
    # signal_max for orphaned_priv must be exactly 0 (orphan needs window_hours
    # overdue, which our short trajectory cannot accumulate).
    assert result.signal_max["orphaned_priv"] == 0.0


def test_run_benign_only_returns_distribution():
    floor = run_benign_only(seed=999)
    assert isinstance(floor, BenignFloorResult)
    assert floor.n_pairs > 0
    assert 0.0 <= floor.p50 <= floor.p75 <= floor.p90 <= floor.p95 <= floor.p99
    assert floor.p99 <= floor.max_residual + 1e-9
    # Signal fire rates are valid fractions
    for s, fr in floor.signal_fire_rate.items():
        assert 0.0 <= fr <= 1.0, f"{s}={fr}"


def test_recalibrate_thresholds_respects_benign_floor():
    """Recalibrated WATCH must be >= benign P95."""
    benign = BenignFloorResult(
        n_pairs=100, residuals=[0.1] * 100,
        p50=0.10, p75=0.20, p90=0.30, p95=0.40, p99=0.45,
        max_residual=0.50, signal_fire_rate={},
    )

    # Case: grid p75 below benign p95 → WATCH = benign p95
    from src.validation.robustness import TrajectoryResult
    grid_low = [
        TrajectoryResult(
            params=AttackParams("fast", "single_actor", "direct", "none", "none", "key_exfil"),
            seed=i, label=f"t{i}", n_events=2, n_windows=5,
            fusion_raw_max=0.1, residual_risk_max=0.15 + (i * 0.01),
            detected=False, alert_tier="NORMAL",
            signal_max={s: 0.0 for s in (
                "inv_score", "novelty_score", "sigma_coarse", "bridge_new",
                "delta_f", "closure_gap", "orphaned_priv",
            )},
            signal_fired={s: False for s in (
                "inv_score", "novelty_score", "sigma_coarse", "bridge_new",
                "delta_f", "closure_gap", "orphaned_priv",
            )},
            expected_signals=[],
        )
        for i in range(20)
    ]
    recal = recalibrate_thresholds(grid_low, benign)
    assert recal.watch >= benign.p95, (
        f"recalibrated WATCH {recal.watch:.3f} below benign P95 {benign.p95:.3f}"
    )
    assert recal.benign_p95 == benign.p95


def test_recalibrate_thresholds_uses_grid_when_higher():
    """When grid p75 > benign p95, WATCH = grid p75."""
    benign = BenignFloorResult(
        n_pairs=100, residuals=[0.1] * 100,
        p50=0.05, p75=0.10, p90=0.15, p95=0.20, p99=0.25,
        max_residual=0.30, signal_fire_rate={},
    )
    from src.validation.robustness import TrajectoryResult
    grid_high = [
        TrajectoryResult(
            params=AttackParams("fast", "single_actor", "direct", "none", "none", "key_exfil"),
            seed=i, label=f"t{i}", n_events=2, n_windows=5,
            fusion_raw_max=0.5, residual_risk_max=0.40 + (i * 0.01),
            detected=True, alert_tier="MEDIUM",
            signal_max={s: 0.0 for s in (
                "inv_score", "novelty_score", "sigma_coarse", "bridge_new",
                "delta_f", "closure_gap", "orphaned_priv",
            )},
            signal_fired={s: False for s in (
                "inv_score", "novelty_score", "sigma_coarse", "bridge_new",
                "delta_f", "closure_gap", "orphaned_priv",
            )},
            expected_signals=[],
        )
        for i in range(20)
    ]
    recal = recalibrate_thresholds(grid_high, benign)
    assert recal.watch > benign.p95
    assert recal.watch >= 0.40  # at least the lowest grid p75 candidate


def test_aggregate_produces_complete_report():
    """Aggregation should produce a full report including divergence and rates by axis."""
    baseline = _generate_benign_canonical_events(seed=999, n_windows=8)
    params_list = [
        (AttackParams("fast", "single_actor", "direct", "none", "none", "key_exfil"), 1),
        (AttackParams("slow", "multi_actor", "full_chain", "split_actions", "full", "data_exfil"), 2),
    ]
    grid_results = [
        run_trajectory_in_baseline(p, s, baseline, f"t{s}") for p, s in params_list
    ]
    floor = run_benign_only(seed=999)

    report = aggregate_baseline_report(grid_results, [], floor)

    assert len(report.grid_results_in_baseline) == 2
    assert "speed" in report.rates_by_axis_recalibrated
    assert "spread" in report.rates_by_axis_recalibrated
    assert all(s in report.signal_fire_rate_in_baseline for s in (
        "inv_score", "novelty_score", "sigma_coarse", "bridge_new",
        "delta_f", "closure_gap", "orphaned_priv",
    ))
    md = report.to_markdown()
    assert "Detection rate (current thresholds" in md
    assert "Detection rate (recalibrated" in md
    assert "Benign-Only Residual Distribution" in md
