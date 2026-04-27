"""Tests for large-scale validation harness."""

import math

import pytest

from src.validation.large_scale import (
    RunMetrics,
    SweepConfig,
    ValidationReport,
    run_single_trajectory,
    aggregate_report,
)


class TestSweepConfig:
    def test_default_generates_900_configs(self):
        cfg = SweepConfig()
        params = cfg.param_grid()
        assert len(params) == 900  # 100 seeds x 3 actors x 3 attack_ratios

    def test_custom_config(self):
        cfg = SweepConfig(seeds=range(1, 6), actor_counts=[10], attack_ratios=[0.1])
        params = cfg.param_grid()
        assert len(params) == 5
        for p in params:
            assert p["actors"] == 10
            assert p["attack_ratio"] == 0.1
            assert p["windows"] == 20

    def test_param_grid_has_required_keys(self):
        cfg = SweepConfig(seeds=range(1, 3), actor_counts=[10], attack_ratios=[0.2])
        for p in cfg.param_grid():
            assert "seed" in p
            assert "actors" in p
            assert "windows" in p
            assert "attack_ratio" in p


class TestRunSingleTrajectory:
    """Integration test: run one small trajectory through the full pipeline."""

    def test_returns_run_metrics(self):
        result = run_single_trajectory(seed=42, actors=10, windows=5, attack_ratio=0.2)
        assert isinstance(result, RunMetrics)

    def test_metrics_have_expected_fields(self):
        m = run_single_trajectory(seed=42, actors=10, windows=5, attack_ratio=0.2)
        # Gap should be a real number (can be negative in small samples)
        assert isinstance(m.gap_ratio, float)
        assert not math.isnan(m.gap_ratio)
        # FP/FN rates in [0, 1]
        assert 0.0 <= m.fp_rate <= 1.0
        assert 0.0 <= m.fn_rate <= 1.0
        # Event count should be positive
        assert m.event_count > 0
        # Actor counts
        assert m.attacker_count >= 1
        assert m.worker_count >= 1

    def test_signal_activations_present(self):
        m = run_single_trajectory(seed=42, actors=10, windows=5, attack_ratio=0.2)
        expected_signals = {
            "inv_score", "novelty_score", "bridge_new",
            "closure_gap", "orphaned_priv", "trigger_resolved",
        }
        assert set(m.signal_activations.keys()) == expected_signals
        # Each activation is a fraction in [0, 1]
        for k, v in m.signal_activations.items():
            assert 0.0 <= v <= 1.0, f"{k} activation {v} out of range"

    def test_different_seeds_different_results(self):
        m1 = run_single_trajectory(seed=1, actors=10, windows=5, attack_ratio=0.2)
        m2 = run_single_trajectory(seed=99, actors=10, windows=5, attack_ratio=0.2)
        # Different seeds should produce different event counts or gaps
        # (extremely unlikely to be identical)
        assert m1.event_count != m2.event_count or m1.gap_ratio != m2.gap_ratio

    def test_zero_attack_ratio(self):
        """With no attacks, FN rate is undefined (no attackers to miss)."""
        m = run_single_trajectory(seed=42, actors=10, windows=5, attack_ratio=0.0)
        # Attackers are still generated (role assignment is per-actor, not per-window)
        # but no attack windows means attackers behave benignly
        assert isinstance(m.gap_ratio, float)


class TestAggregateReport:
    """Test report aggregation from multiple RunMetrics."""

    def _make_metrics(self, gap: float, fp: float, fn: float, **kwargs) -> RunMetrics:
        defaults = dict(
            seed=1, actors=10, windows=5, attack_ratio=0.1,
            event_count=100, attacker_count=2, worker_count=6,
            attacker_mean_residual=0.2, worker_mean_residual=0.1,
            gap_ratio=gap, fp_rate=fp, fn_rate=fn,
            alert_dist={"HIGH": 1, "MEDIUM": 2, "WATCH": 3, "NORMAL": 4},
            signal_activations={
                "inv_score": 0.5, "novelty_score": 0.8, "bridge_new": 0.3,
                "closure_gap": 0.4, "orphaned_priv": 0.1, "trigger_resolved": 0.6,
            },
        )
        defaults.update(kwargs)
        return RunMetrics(**defaults)

    def test_basic_aggregation(self):
        runs = [
            self._make_metrics(gap=60.0, fp=0.05, fn=0.10),
            self._make_metrics(gap=70.0, fp=0.03, fn=0.15),
            self._make_metrics(gap=50.0, fp=0.08, fn=0.05),
        ]
        report = aggregate_report(runs)
        assert isinstance(report, ValidationReport)
        assert report.total_runs == 3
        assert abs(report.mean_gap - 60.0) < 0.01
        assert report.worst_gap == 50.0  # lowest gap = worst discrimination
        assert abs(report.mean_fp - (0.05 + 0.03 + 0.08) / 3) < 0.01
        assert abs(report.mean_fn - (0.10 + 0.15 + 0.05) / 3) < 0.01

    def test_parameter_sensitivity(self):
        """Report should break down gap by parameter value."""
        runs = [
            self._make_metrics(gap=60.0, fp=0.0, fn=0.0, actors=10, attack_ratio=0.1),
            self._make_metrics(gap=50.0, fp=0.0, fn=0.0, actors=20, attack_ratio=0.1),
            self._make_metrics(gap=40.0, fp=0.0, fn=0.0, actors=10, attack_ratio=0.2),
            self._make_metrics(gap=30.0, fp=0.0, fn=0.0, actors=20, attack_ratio=0.2),
        ]
        report = aggregate_report(runs)
        # Should have per-actor-count and per-attack-ratio breakdowns
        assert 10 in report.gap_by_actors
        assert 20 in report.gap_by_actors
        assert 0.1 in report.gap_by_attack_ratio
        assert 0.2 in report.gap_by_attack_ratio
        # 10-actor runs: mean gap (60+40)/2 = 50
        assert abs(report.gap_by_actors[10] - 50.0) < 0.01
        # 0.1-ratio runs: mean gap (60+50)/2 = 55
        assert abs(report.gap_by_attack_ratio[0.1] - 55.0) < 0.01

    def test_signal_reliability(self):
        """Signal reliability = fraction of runs where signal activation > 0."""
        runs = [
            self._make_metrics(
                gap=60.0, fp=0.0, fn=0.0,
                signal_activations={
                    "inv_score": 0.5, "novelty_score": 0.8, "bridge_new": 0.0,
                    "closure_gap": 0.4, "orphaned_priv": 0.0, "trigger_resolved": 0.6,
                },
            ),
            self._make_metrics(
                gap=60.0, fp=0.0, fn=0.0,
                signal_activations={
                    "inv_score": 0.0, "novelty_score": 0.9, "bridge_new": 0.3,
                    "closure_gap": 0.0, "orphaned_priv": 0.1, "trigger_resolved": 0.0,
                },
            ),
        ]
        report = aggregate_report(runs)
        # inv_score active in 1/2 = 0.5
        assert abs(report.signal_reliability["inv_score"] - 0.5) < 0.01
        # novelty_score active in 2/2 = 1.0
        assert abs(report.signal_reliability["novelty_score"] - 1.0) < 0.01

    def test_report_to_markdown(self):
        runs = [self._make_metrics(gap=60.0, fp=0.05, fn=0.10)]
        report = aggregate_report(runs)
        md = report.to_markdown()
        assert "# Large-Scale Validation Report" in md
        assert "60.0" in md
        assert "Signal Reliability" in md


class TestThresholdCalibration:
    """Verify recalibrated thresholds produce usable FP/FN rates.

    Per-window classification has a fundamental FP/FN tradeoff because attackers
    don't attack every window. The real discrimination is at the actor level
    (mean across windows). These tests verify the thresholds are in a sane range,
    not that per-window classification is perfect.
    """

    def test_fp_rate_below_10_percent(self):
        """Worker FP at MEDIUM+ must stay below 10%."""
        fps = []
        for seed in [42, 7, 55, 13, 99]:
            m = run_single_trajectory(seed=seed, actors=20, windows=20, attack_ratio=0.2)
            fps.append(m.fp_rate)
        mean_fp = sum(fps) / len(fps)
        assert mean_fp < 0.10, f"Mean FP {mean_fp:.3f} too high — thresholds too aggressive"

    def test_attacker_mean_residual_above_worker(self):
        """Actor-level discrimination: attacker mean > worker mean in most runs."""
        discriminating = 0
        for seed in [42, 7, 55, 13, 99]:
            m = run_single_trajectory(seed=seed, actors=20, windows=20, attack_ratio=0.2)
            if m.attacker_mean_residual > m.worker_mean_residual:
                discriminating += 1
        assert discriminating >= 4, f"Only {discriminating}/5 runs discriminate at actor level"

    def test_thresholds_not_above_max_residual(self):
        """HIGH threshold must be reachable — at least some events should cross it."""
        any_high = False
        for seed in [42, 7, 55, 13, 99, 22, 77]:
            m = run_single_trajectory(seed=seed, actors=20, windows=20, attack_ratio=0.3)
            if m.alert_dist.get("HIGH", 0) > 0:
                any_high = True
                break
        assert any_high, "HIGH threshold unreachable — no events cross it across 7 seeds"


class TestRunMetricsEdgeCases:
    def test_single_attacker_single_worker(self):
        """Minimum viable trajectory — should not crash."""
        m = run_single_trajectory(seed=42, actors=5, windows=5, attack_ratio=0.2)
        assert m.attacker_count >= 1
        assert m.worker_count >= 1
