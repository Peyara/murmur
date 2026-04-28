"""Tests for the Sprint 2 robustness harness."""

from src.validation.attack_generator import EVASIONS, SPEEDS
from src.validation.robustness import (
    SIGNAL_NAMES,
    aggregate,
    edge_cases,
    param_grid,
    run_trajectory,
)


class TestParamGrid:
    def test_grid_size_respected(self):
        grid = param_grid(grid_size=20, seed=0)
        assert len(grid) == 20

    def test_grid_covers_every_speed_evasion_cell(self):
        # Stratification guarantee: every (speed, evasion) cell has ≥1 sample.
        grid = param_grid(grid_size=20, seed=0)
        cells_seen = {(p.speed, p.evasion) for p, _ in grid}
        for speed in SPEEDS:
            for evasion in EVASIONS:
                assert (speed, evasion) in cells_seen, f"missing cell ({speed},{evasion})"

    def test_grid_is_deterministic(self):
        g1 = param_grid(grid_size=20, seed=42)
        g2 = param_grid(grid_size=20, seed=42)
        assert [p for p, _ in g1] == [p for p, _ in g2]
        assert [s for _, s in g1] == [s for _, s in g2]

    def test_full_grid_size_50_has_unique_seeds(self):
        grid = param_grid(grid_size=50, seed=0)
        seeds = [s for _, s in grid]
        assert len(seeds) == len(set(seeds))


class TestEdgeCases:
    def test_edge_cases_count(self):
        edges = edge_cases()
        assert len(edges) == 5

    def test_edge_case_labels_match_spec(self):
        edges = edge_cases()
        labels = [label for _, _, label in edges]
        assert labels == [
            "edge:slow_ratchet",
            "edge:multi_actor_convergence",
            "edge:exfil_avoiding",
            "edge:perfect_mimicry",
            "edge:minimal_direct",
        ]


class TestRunTrajectory:
    def test_smoke_run_produces_result(self):
        edges = edge_cases()
        params, seed, label = edges[1]  # multi_actor_convergence — should detect
        result = run_trajectory(params, seed, label)
        assert result.label == label
        assert result.n_events >= 2
        assert result.n_windows >= 1
        assert 0.0 <= result.fusion_raw_max <= 1.0
        assert 0.0 <= result.residual_risk_max <= 1.0
        assert result.alert_tier in ("NORMAL", "WATCH", "MEDIUM", "HIGH")
        assert set(result.signal_max.keys()) == set(SIGNAL_NAMES)
        assert set(result.signal_fired.keys()) == set(SIGNAL_NAMES)

    def test_split_actions_produces_multiple_windows(self):
        edges = edge_cases()
        params, seed, label = edges[0]  # slow_ratchet uses split_actions
        result = run_trajectory(params, seed, label)
        assert result.n_windows >= 2


class TestAggregate:
    def test_empty_results_returns_empty_report(self):
        report = aggregate([], [])
        assert report.detection_rate_overall == 0.0
        assert report.results == []

    def test_per_axis_breakdowns_present(self):
        # Run a small grid to populate the report.
        grid = param_grid(grid_size=12, seed=0)  # 12 = exactly 1 per (speed,evasion) cell
        results = [run_trajectory(p, s, f"grid:{i}") for i, (p, s) in enumerate(grid)]
        report = aggregate(results, [])
        assert set(report.detection_rate_by_speed.keys()).issubset(set(SPEEDS))
        assert set(report.detection_rate_by_evasion.keys()).issubset(set(EVASIONS))
        assert 0.0 <= report.detection_rate_overall <= 1.0

    def test_to_markdown_contains_all_sections(self):
        grid = param_grid(grid_size=12, seed=0)
        results = [run_trajectory(p, s, f"grid:{i}") for i, (p, s) in enumerate(grid)]
        report = aggregate(results, [])
        md = report.to_markdown()
        # Must contain the report sections
        assert "# Sprint 2 — Attack-Strategy Robustness Report" in md
        assert "## Gate Summary" in md
        assert "## Detection Rate by Parameter" in md
        assert "### By speed" in md
        assert "### By spread" in md
        assert "### By zone_path" in md
        assert "### By evasion" in md
        assert "### By closure" in md
        assert "### By objective" in md
        assert "## Signal Fire Rate" in md
        assert "## Prediction Divergence" in md
        # Verdict line should be present and one of the four allowed values
        assert any(v in md for v in ("PASS", "BORDERLINE", "FAIL", "CLASS-WIPE"))
