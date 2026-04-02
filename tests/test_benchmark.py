"""Benchmark scenario tests — Sprint 1B signal validation gate.

Validates that:
1. Attack scenarios fire expected invariants and score above threshold
2. Benign scenarios (with history) score low with correct provenance discount
3. Attack residual_risk >= 2x benign average (the core validation criterion)
"""

from pathlib import Path

import pytest

from src.benchmark.runner import BenchmarkResult, run_scenario

SCENARIOS_DIR = Path(__file__).parent.parent / "data" / "benchmark"
HISTORY_PATH = str(SCENARIOS_DIR / "history_benign.jsonl")

BENIGN_PATTERNS = [
    {
        "name": "normal-worker-scheduled",
        "expected_actors": ["normal-worker-sa@murmur-sandbox.iam.gserviceaccount.com"],
        "expected_zones": ["DATA", "DATA", "SECRET", "DATA"],
        "rate_min": 3,
        "rate_max": 10,
    },
    {
        "name": "maintainer-scheduled",
        "expected_actors": ["maintenance-sa@murmur-sandbox.iam.gserviceaccount.com"],
        "expected_zones": ["SECRET", "SECRET", "SECRET"],
        "rate_min": 2,
        "rate_max": 8,
    },
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def s01() -> BenchmarkResult:
    return run_scenario(str(SCENARIOS_DIR / "s01_key_secret.jsonl"))


@pytest.fixture(scope="module")
def s04() -> BenchmarkResult:
    return run_scenario(str(SCENARIOS_DIR / "s04_slow_ratchet.jsonl"))


@pytest.fixture(scope="module")
def s07() -> BenchmarkResult:
    return run_scenario(str(SCENARIOS_DIR / "s07_cross_actor.jsonl"))


@pytest.fixture(scope="module")
def b01() -> BenchmarkResult:
    return run_scenario(
        str(SCENARIOS_DIR / "b01_deploy.jsonl"),
        history_path=HISTORY_PATH,
        patterns=BENIGN_PATTERNS,
    )


@pytest.fixture(scope="module")
def b02() -> BenchmarkResult:
    return run_scenario(
        str(SCENARIOS_DIR / "b02_secret_rotation.jsonl"),
        history_path=HISTORY_PATH,
        patterns=BENIGN_PATTERNS,
    )


@pytest.fixture(scope="module")
def s13() -> BenchmarkResult:
    return run_scenario(
        str(SCENARIOS_DIR / "s13_pattern_no_provenance.jsonl"),
        history_path=HISTORY_PATH,
        patterns=BENIGN_PATTERNS,
    )


# ---------------------------------------------------------------------------
# Attack scenarios: invariant assertions
# ---------------------------------------------------------------------------


class TestS01KeySecret:
    def test_ingests_all_events(self, s01: BenchmarkResult):
        assert s01.ingest_stats["inserted"] == 2

    def test_fires_key_creation(self, s01: BenchmarkResult):
        assert "INV_002" in s01.all_fired_invariants

    def test_fires_secret_access_new_actor(self, s01: BenchmarkResult):
        assert "INV_006" in s01.all_fired_invariants

    def test_does_not_fire_impersonation(self, s01: BenchmarkResult):
        assert "INV_004" not in s01.all_fired_invariants

    def test_scores_above_watch(self, s01: BenchmarkResult):
        assert s01.max_residual >= 0.30


class TestS04SlowRatchet:
    def test_ingests_all_events(self, s04: BenchmarkResult):
        assert s04.ingest_stats["inserted"] == 7

    def test_fires_iam_policy(self, s04: BenchmarkResult):
        assert "INV_001" in s04.all_fired_invariants

    def test_fires_key_creation(self, s04: BenchmarkResult):
        assert "INV_002" in s04.all_fired_invariants

    def test_fires_impersonation(self, s04: BenchmarkResult):
        assert "INV_004" in s04.all_fired_invariants

    def test_fires_kms_decrypt(self, s04: BenchmarkResult):
        assert "INV_008" in s04.all_fired_invariants

    def test_fires_exfil_edge(self, s04: BenchmarkResult):
        assert "INV_010" in s04.all_fired_invariants

    def test_highest_attack_score(self, s04: BenchmarkResult, s01: BenchmarkResult, s07: BenchmarkResult):
        assert s04.max_residual >= s01.max_residual
        assert s04.max_residual >= s07.max_residual

    def test_spans_multiple_windows(self, s04: BenchmarkResult):
        windows = {r.window_start for r in s04.actor_results}
        assert len(windows) >= 2


class TestS07CrossActor:
    def test_ingests_all_events(self, s07: BenchmarkResult):
        assert s07.ingest_stats["inserted"] == 5

    def test_fires_iam_policy(self, s07: BenchmarkResult):
        assert "INV_001" in s07.all_fired_invariants

    def test_fires_impersonation(self, s07: BenchmarkResult):
        assert "INV_004" in s07.all_fired_invariants

    def test_multiple_actors_scored(self, s07: BenchmarkResult):
        actors = {r.actor_id for r in s07.actor_results}
        assert len(actors) >= 2


# ---------------------------------------------------------------------------
# Benign scenarios: invariant + provenance assertions
# ---------------------------------------------------------------------------


class TestB01Deploy:
    def test_ingests_all_events(self, b01: BenchmarkResult):
        assert b01.ingest_stats["inserted"] == 4

    def test_no_invariants_fire(self, b01: BenchmarkResult):
        assert len(b01.all_fired_invariants) == 0

    def test_pattern_match(self, b01: BenchmarkResult):
        for r in b01.actor_results:
            assert r.pattern_match_score > 0.5

    def test_provenance_discount_applied(self, b01: BenchmarkResult):
        for r in b01.actor_results:
            assert r.residual_risk < r.fusion_raw

    def test_scores_normal(self, b01: BenchmarkResult):
        assert b01.max_alert_tier == "NORMAL"


class TestB02SecretRotation:
    def test_ingests_all_events(self, b02: BenchmarkResult):
        assert b02.ingest_stats["inserted"] == 3

    def test_no_key_or_impersonation_invariants(self, b02: BenchmarkResult):
        assert "INV_002" not in b02.all_fired_invariants
        assert "INV_004" not in b02.all_fired_invariants

    def test_pattern_match(self, b02: BenchmarkResult):
        for r in b02.actor_results:
            assert r.pattern_match_score > 0.5

    def test_scores_below_attacks(self, b02: BenchmarkResult, s01: BenchmarkResult):
        assert b02.max_residual < s01.max_residual


# ---------------------------------------------------------------------------
# Hybrid scenario
# ---------------------------------------------------------------------------


class TestS13PatternNoProvenance:
    def test_ingests_all_events(self, s13: BenchmarkResult):
        assert s13.ingest_stats["inserted"] == 4

    def test_no_invariants_fire(self, s13: BenchmarkResult):
        assert len(s13.all_fired_invariants) == 0

    def test_no_provenance_discount(self, s13: BenchmarkResult):
        for r in s13.actor_results:
            # No trigger_ref → NONE provenance → discount multiplier = 0
            assert r.residual_risk == pytest.approx(r.fusion_raw, abs=0.001)

    def test_scores_higher_than_b01(self, s13: BenchmarkResult, b01: BenchmarkResult):
        assert s13.max_residual > b01.max_residual

    def test_scores_lower_than_attacks(self, s13: BenchmarkResult, s01: BenchmarkResult):
        assert s13.max_residual < s01.max_residual


# ---------------------------------------------------------------------------
# Core validation criterion: attack >= 2x benign average
# ---------------------------------------------------------------------------


class TestSignalSeparation:
    def test_attack_exceeds_2x_benign(
        self, s01: BenchmarkResult, s04: BenchmarkResult, s07: BenchmarkResult,
        b01: BenchmarkResult, b02: BenchmarkResult,
    ):
        benign_avg = (b01.mean_residual + b02.mean_residual) / 2
        assert benign_avg > 0, "Benign scenarios must produce nonzero residual"

        for name, attack in [("S01", s01), ("S04", s04), ("S07", s07)]:
            ratio = attack.max_residual / benign_avg
            assert ratio >= 2.0, (
                f"{name} max_residual={attack.max_residual:.4f} is only "
                f"{ratio:.1f}x benign avg={benign_avg:.4f} (need >= 2.0x)"
            )

    def test_ordering_b01_lt_s13_lt_attacks(
        self, b01: BenchmarkResult, s13: BenchmarkResult,
        s01: BenchmarkResult, s04: BenchmarkResult,
    ):
        assert b01.max_residual < s13.max_residual < s01.max_residual <= s04.max_residual
