"""Tests for closure signal ablation study."""

import math

from src.score.ablation import (
    AblationResult,
    ScoredRow,
    assign_tier,
    compute_fusion_with_weights,
    compute_role_stats,
    extract_role,
    format_tier_matrix,
    generate_report,
    reweight,
    run_ablation,
)
from src.score.fusion import FUSION_WEIGHTS


def _make_row(**overrides) -> ScoredRow:
    """Create a ScoredRow with sensible defaults."""
    defaults = dict(
        window_start="2026-01-01 00:00:00",
        actor_id="test-sa@proj.iam.gserviceaccount.com",
        inv_score=0.0,
        inv_count=0.0,
        sigma_coarse=0.0,
        novelty_score=0.0,
        bridge_new=0.0,
        delta_f=0.0,
        burst_per_min=0.0,
        breadth_entropy=0.0,
        closure_ratio=1.0,
        orphaned_privilege=0.0,
        fusion_raw=0.0,
        residual_risk=0.0,
        explanation="test",
    )
    defaults.update(overrides)
    return ScoredRow(**defaults)


class TestAssignTier:
    def test_high(self):
        assert assign_tier(0.85) == "HIGH"

    def test_medium(self):
        assert assign_tier(0.55) == "MEDIUM"

    def test_watch(self):
        assert assign_tier(0.05) == "WATCH"

    def test_normal(self):
        assert assign_tier(0.001) == "NORMAL"

    def test_boundary_high(self):
        assert assign_tier(0.8) == "HIGH"

    def test_boundary_medium(self):
        assert assign_tier(0.5) == "MEDIUM"


class TestReweight:
    def test_zero_mode_sums_to_one(self):
        result = reweight(FUSION_WEIGHTS, ["closure_gap", "orphaned_priv"], "zero")
        assert result["closure_gap"] == 0.0
        assert result["orphaned_priv"] == 0.0
        assert abs(sum(result.values()) - 1.0) < 1e-10

    def test_redistribute_mode_sums_to_one(self):
        result = reweight(FUSION_WEIGHTS, ["closure_gap", "orphaned_priv"], "redistribute")
        assert result["closure_gap"] == 0.0
        assert result["orphaned_priv"] == 0.0
        assert abs(sum(result.values()) - 1.0) < 1e-10

    def test_zero_and_redistribute_equivalent_for_proportional(self):
        """Both modes produce same weights when starting weights are proportional."""
        zero = reweight(FUSION_WEIGHTS, ["closure_gap", "orphaned_priv"], "zero")
        redist = reweight(FUSION_WEIGHTS, ["closure_gap", "orphaned_priv"], "redistribute")
        for k in zero:
            assert abs(zero[k] - redist[k]) < 1e-10

    def test_non_zeroed_weights_increase(self):
        result = reweight(FUSION_WEIGHTS, ["closure_gap", "orphaned_priv"], "zero")
        for k in FUSION_WEIGHTS:
            if k not in ["closure_gap", "orphaned_priv"] and FUSION_WEIGHTS[k] > 0:
                assert result[k] > FUSION_WEIGHTS[k]


class TestComputeFusion:
    def test_all_zeros(self):
        signals = {k: 0.0 for k in FUSION_WEIGHTS}
        assert compute_fusion_with_weights(signals, FUSION_WEIGHTS) == 0.0

    def test_all_ones(self):
        signals = {k: 1.0 for k in FUSION_WEIGHTS}
        result = compute_fusion_with_weights(signals, FUSION_WEIGHTS)
        assert abs(result - sum(FUSION_WEIGHTS.values())) < 1e-10

    def test_single_signal(self):
        signals = {k: 0.0 for k in FUSION_WEIGHTS}
        signals["novelty_score"] = 0.5
        result = compute_fusion_with_weights(signals, FUSION_WEIGHTS)
        assert abs(result - 0.5 * FUSION_WEIGHTS["novelty_score"]) < 1e-10


class TestNormalizeSignals:
    def test_closure_gap_inversion(self):
        row = _make_row(closure_ratio=0.8)
        signals = row.normalize_signals()
        assert abs(signals["closure_gap"] - 0.2) < 1e-10

    def test_zero_signals_normalize_to_baseline(self):
        row = _make_row()
        signals = row.normalize_signals()
        # sigma_coarse at 0 still has sigmoid baseline > 0
        assert signals["sigma_coarse"] > 0
        # All others should be 0 or near 0
        assert signals["inv_score"] == 0.0
        assert signals["novelty_score"] == 0.0


class TestRunAblation:
    def test_returns_correct_length(self):
        rows = [_make_row(), _make_row(actor_id="other-sa@proj.iam")]
        result = run_ablation(rows, ["closure_gap", "orphaned_priv"], "zero")
        assert len(result.rows) == 2
        assert len(result.deltas) == 2

    def test_no_closure_activity_minimal_delta(self):
        """Rows with closure_ratio=1.0 (no gap) should have small deltas."""
        row = _make_row(
            closure_ratio=1.0, orphaned_privilege=0.0,
            inv_score=2.0, novelty_score=5.0, fusion_raw=0.25,
        )
        result = run_ablation([row], ["closure_gap", "orphaned_priv"], "zero")
        # Delta comes only from weight redistribution on non-closure signals
        assert abs(result.deltas[0]) < 0.15

    def test_high_closure_gap_changes_score(self):
        """Rows with closure_ratio=0.0 (max gap) should see larger deltas."""
        row = _make_row(
            closure_ratio=0.0, orphaned_privilege=10.0,
            fusion_raw=0.15,
        )
        result = run_ablation([row], ["closure_gap", "orphaned_priv"], "zero")
        # Removing closure_gap=1.0 (weight 0.10) should produce noticeable delta
        assert abs(result.deltas[0]) > 0.01


class TestTierMigrations:
    def test_migration_matrix(self):
        result = AblationResult(
            mode="zero",
            weights=FUSION_WEIGHTS,
            rows=[
                (_make_row(), 0.0, "NORMAL", "NORMAL"),
                (_make_row(), 0.1, "NORMAL", "WATCH"),
                (_make_row(), 0.6, "WATCH", "MEDIUM"),
            ],
            deltas=[0.0, 0.1, 0.1],
        )
        mig = result.tier_migrations
        assert mig[("NORMAL", "NORMAL")] == 1
        assert mig[("NORMAL", "WATCH")] == 1
        assert mig[("WATCH", "MEDIUM")] == 1

    def test_format_tier_matrix_renders(self):
        migrations = {("NORMAL", "NORMAL"): 10, ("NORMAL", "WATCH"): 2}
        table = format_tier_matrix(migrations)
        assert "NORMAL" in table
        assert "10" in table
        assert "2" in table


class TestStats:
    def test_stats_computation(self):
        result = AblationResult(
            mode="zero",
            weights=FUSION_WEIGHTS,
            rows=[],
            deltas=[0.1, -0.2, 0.05],
        )
        s = result.stats
        assert abs(s["mean"] - (0.1 + 0.2 + 0.05) / 3) < 1e-10
        assert s["max"] == 0.2


# ── Role-based analysis tests ──────────────────────────────────


class TestExtractRole:
    def test_synthetic_attacker(self):
        assert extract_role("attacker-sa-5@synth-project.iam.gserviceaccount.com") == "attacker"

    def test_synthetic_worker(self):
        assert extract_role("worker-sa-12@synth-project.iam.gserviceaccount.com") == "worker"

    def test_synthetic_admin(self):
        assert extract_role("admin-sa-0@synth-project.iam.gserviceaccount.com") == "admin"

    def test_synthetic_scheduler(self):
        assert extract_role("scheduler-sa-3@synth-project.iam.gserviceaccount.com") == "scheduler"

    def test_non_synthetic_fallback(self):
        assert extract_role("real-user@example.com") == "unknown"

    def test_empty_string(self):
        assert extract_role("") == "unknown"


class TestComputeRoleStats:
    def test_groups_by_role(self):
        baseline = [
            _make_row(actor_id="attacker-sa-0@synth", fusion_raw=0.5),
            _make_row(actor_id="attacker-sa-1@synth", fusion_raw=0.6),
            _make_row(actor_id="worker-sa-0@synth", fusion_raw=0.2),
            _make_row(actor_id="worker-sa-1@synth", fusion_raw=0.3),
            _make_row(actor_id="worker-sa-2@synth", fusion_raw=0.25),
        ]
        zero = run_ablation(baseline, ["closure_gap", "orphaned_priv"], "zero")
        redist = run_ablation(baseline, ["closure_gap", "orphaned_priv"], "redistribute")
        stats = compute_role_stats(baseline, zero, redist)

        assert "attacker" in stats
        assert "worker" in stats
        assert stats["attacker"].count == 2
        assert stats["worker"].count == 3

    def test_per_role_means(self):
        baseline = [
            _make_row(actor_id="attacker-sa-0@synth", fusion_raw=0.4),
            _make_row(actor_id="attacker-sa-1@synth", fusion_raw=0.6),
            _make_row(actor_id="worker-sa-0@synth", fusion_raw=0.2),
            _make_row(actor_id="worker-sa-1@synth", fusion_raw=0.3),
        ]
        zero = run_ablation(baseline, ["closure_gap", "orphaned_priv"], "zero")
        redist = run_ablation(baseline, ["closure_gap", "orphaned_priv"], "redistribute")
        stats = compute_role_stats(baseline, zero, redist)

        assert abs(stats["attacker"].baseline_mean - 0.5) < 1e-10
        assert abs(stats["worker"].baseline_mean - 0.25) < 1e-10

    def test_gap_metric(self):
        baseline = [
            _make_row(actor_id="attacker-sa-0@synth", fusion_raw=0.6),
            _make_row(actor_id="attacker-sa-1@synth", fusion_raw=0.6),
            _make_row(actor_id="worker-sa-0@synth", fusion_raw=0.3),
            _make_row(actor_id="worker-sa-1@synth", fusion_raw=0.3),
        ]
        zero = run_ablation(baseline, ["closure_gap", "orphaned_priv"], "zero")
        redist = run_ablation(baseline, ["closure_gap", "orphaned_priv"], "redistribute")
        stats = compute_role_stats(baseline, zero, redist)

        # attacker_mean / worker_mean = 0.6 / 0.3 = 2.0
        assert abs(stats["attacker"].gap_baseline - 2.0) < 0.01

    def test_gap_nan_without_workers(self):
        baseline = [
            _make_row(actor_id="attacker-sa-0@synth", fusion_raw=0.5),
            _make_row(actor_id="admin-sa-0@synth", fusion_raw=0.3),
        ]
        zero = run_ablation(baseline, ["closure_gap", "orphaned_priv"], "zero")
        redist = run_ablation(baseline, ["closure_gap", "orphaned_priv"], "redistribute")
        stats = compute_role_stats(baseline, zero, redist)

        assert math.isnan(stats["attacker"].gap_baseline)

    def test_closure_activation_pct(self):
        baseline = [
            _make_row(actor_id="attacker-sa-0@synth", closure_ratio=0.5, orphaned_privilege=5.0, fusion_raw=0.3),
            _make_row(actor_id="attacker-sa-1@synth", closure_ratio=1.0, orphaned_privilege=0.0, fusion_raw=0.2),
        ]
        zero = run_ablation(baseline, ["closure_gap", "orphaned_priv"], "zero")
        redist = run_ablation(baseline, ["closure_gap", "orphaned_priv"], "redistribute")
        stats = compute_role_stats(baseline, zero, redist)

        # 1 of 2 has closure_gap > 0.001 (closure_ratio=0.5 → gap=0.5)
        assert abs(stats["attacker"].closure_gap_active_pct - 50.0) < 0.1
        # 1 of 2 has orphaned_priv > 0.001
        assert abs(stats["attacker"].orphaned_priv_active_pct - 50.0) < 0.1

    def test_single_row_per_role_no_crash(self):
        baseline = [
            _make_row(actor_id="attacker-sa-0@synth", fusion_raw=0.5),
            _make_row(actor_id="worker-sa-0@synth", fusion_raw=0.3),
        ]
        zero = run_ablation(baseline, ["closure_gap", "orphaned_priv"], "zero")
        redist = run_ablation(baseline, ["closure_gap", "orphaned_priv"], "redistribute")
        stats = compute_role_stats(baseline, zero, redist)

        # Single row → stdev should be 0.0, not crash
        assert stats["attacker"].baseline_stdev == 0.0
        assert stats["worker"].count == 1


class TestGenerateReportRoles:
    def test_report_includes_role_section(self):
        baseline = [
            _make_row(actor_id="attacker-sa-0@synth", fusion_raw=0.5),
            _make_row(actor_id="worker-sa-0@synth", fusion_raw=0.3),
        ]
        zero = run_ablation(baseline, ["closure_gap", "orphaned_priv"], "zero")
        redist = run_ablation(baseline, ["closure_gap", "orphaned_priv"], "redistribute")
        report = generate_report(baseline, zero, redist, ":memory:", include_role_analysis=True)

        assert "## Role-Based Analysis" in report
        assert "attacker" in report
        assert "worker" in report

    def test_report_backward_compatible(self):
        baseline = [_make_row(fusion_raw=0.1)]
        zero = run_ablation(baseline, ["closure_gap", "orphaned_priv"], "zero")
        redist = run_ablation(baseline, ["closure_gap", "orphaned_priv"], "redistribute")
        report = generate_report(baseline, zero, redist, ":memory:", include_role_analysis=False)

        assert "## Method" in report
        assert "## Role-Based Analysis" not in report
