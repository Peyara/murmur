"""Tests for synthetic GCP audit log trajectory generator."""

import warnings
from datetime import datetime, timedelta

from src.ingest.parser import parse_audit_log
from src.schema import TargetZone
from src.synthetic import generate_trajectory  # noqa: F401
from src.synthetic.provenance import ProvenanceGenerator
from src.synthetic.temporal import TemporalEngine


class TestSyntheticGeneration:
    def test_generate_trajectory_returns_list(self):
        result = generate_trajectory(actors=5, windows=10, attack_ratio=0.2, seed=42)
        assert isinstance(result, list)

    def test_generate_trajectory_creates_events(self):
        result = generate_trajectory(actors=5, windows=10, attack_ratio=0.2, seed=42)
        assert len(result) > 0

    def test_generated_events_parse_successfully(self):
        result = generate_trajectory(actors=5, windows=10, attack_ratio=0.2, seed=42)
        for event in result:
            canonical = parse_audit_log(event)
            assert canonical is not None

    def test_seed_reproducibility(self):
        result_1 = generate_trajectory(actors=5, windows=10, attack_ratio=0.2, seed=42)
        result_2 = generate_trajectory(actors=5, windows=10, attack_ratio=0.2, seed=42)
        assert result_1 == result_2

    def test_all_6_target_zones_coverage(self):
        result = generate_trajectory(actors=20, windows=20, attack_ratio=0.2, seed=123)
        zones = set()
        for event in result:
            canonical = parse_audit_log(event)
            zones.add(canonical.target_zone)
        expected_zones = {
            TargetZone.CONTROL,
            TargetZone.IDENTITY,
            TargetZone.SECRET,
            TargetZone.DATA,
            TargetZone.COMPUTE,
            TargetZone.EXFIL_RISK,
        }
        assert zones == expected_zones

    def test_performance_1000_events(self):
        import time

        start = time.time()
        result = generate_trajectory(actors=20, windows=50, attack_ratio=0.15, seed=42)
        elapsed = time.time() - start
        assert elapsed < 5.0
        assert len(result) >= 500


class TestSyntheticCLI:
    def test_cli_generate_subcommand_help(self):
        from src.cli import cli

        assert any(cmd.name == "generate" for cmd in cli.commands.values())

    def test_cli_generate_basic_invocation(self, tmp_path):
        from click.testing import CliRunner

        from src.cli import cli

        output_file = tmp_path / "test_output.jsonl"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "generate",
                "--actors",
                "5",
                "--windows",
                "10",
                "--attack-ratio",
                "0.1",
                "--seed",
                "42",
                "--output",
                str(output_file),
            ],
        )
        assert result.exit_code == 0
        assert output_file.exists()


class TestTemporalProfiles:
    """Test evidence-grounded temporal profiles for synthetic event generation."""

    @staticmethod
    def create_window():
        """Create a standard 15-minute test window."""
        window_start = datetime(2026, 1, 15, 0, 0, 0)
        window_end = window_start + timedelta(minutes=15)
        return window_start, window_end

    def test_burst_cluster_within_bounds(self):
        """All timestamps must be within [window_start, window_end]."""
        window_start, window_end = self.create_window()
        engine = TemporalEngine(seed=42)
        timestamps = engine.burst_cluster(window_start, window_end, count=10)
        assert all(window_start <= ts <= window_end for ts in timestamps)

    def test_burst_cluster_density(self):
        """Events should be clustered (max spread < 2 * spread_sec)."""
        window_start, window_end = self.create_window()
        engine = TemporalEngine(seed=42)
        spread_sec = 30
        timestamps = engine.burst_cluster(window_start, window_end, count=10, spread_sec=spread_sec)
        # Max spread between first and last should be less than 2 * spread_sec
        if len(timestamps) > 1:
            actual_spread = (timestamps[-1] - timestamps[0]).total_seconds()
            assert actual_spread < 2 * spread_sec

    def test_burst_cluster_count(self):
        """Should return exactly `count` timestamps."""
        window_start, window_end = self.create_window()
        engine = TemporalEngine(seed=42)
        for count in [1, 5, 10]:
            timestamps = engine.burst_cluster(window_start, window_end, count=count)
            assert len(timestamps) == count

    def test_stealth_spread_min_gap(self):
        """Consecutive events must be at least min_gap_sec apart (within jitter)."""
        window_start, window_end = self.create_window()
        engine = TemporalEngine(seed=42)
        min_gap_sec = 120
        # Use a large window to fit multiple events
        large_window_end = window_start + timedelta(seconds=min_gap_sec * 5)
        timestamps = engine.stealth_spread(window_start, large_window_end, count=3, min_gap_sec=min_gap_sec)
        for i in range(len(timestamps) - 1):
            gap = (timestamps[i + 1] - timestamps[i]).total_seconds()
            # Allow for jitter tolerance (±10%)
            assert gap >= min_gap_sec * 0.85

    def test_stealth_spread_within_bounds(self):
        """All timestamps must be within [window_start, window_end]."""
        window_start, window_end = self.create_window()
        large_window_end = window_start + timedelta(seconds=900)  # 15 minutes
        engine = TemporalEngine(seed=42)
        timestamps = engine.stealth_spread(window_start, large_window_end, count=3, min_gap_sec=120)
        assert all(window_start <= ts <= large_window_end for ts in timestamps)

    def test_stealth_spread_reduces_count_when_window_too_small(self):
        """Should not crash; instead reduce count if window too small."""
        window_start, window_end = self.create_window()
        engine = TemporalEngine(seed=42)
        # Window is 15 min = 900 sec; min_gap = 120; can only fit 7-8 events
        # Requesting 20 events should trigger warning and reduce
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            timestamps = engine.stealth_spread(window_start, window_end, count=20, min_gap_sec=120)
            # Should have been warned
            assert len(w) > 0
            assert "stealth_spread" in str(w[0].message)
            # Should return fewer than 20 events
            assert len(timestamps) < 20
            assert len(timestamps) > 0  # But should still return some

    def test_scheduled_periodic_regularity(self):
        """Intervals between events should be approximately interval_sec."""
        window_start = datetime(2026, 1, 15, 0, 0, 0)
        large_window_end = window_start + timedelta(seconds=600)  # 10 min
        engine = TemporalEngine(seed=42)
        interval_sec = 60
        jitter_sec = 2
        timestamps = engine.scheduled_periodic(
            window_start, large_window_end, interval_sec=interval_sec, jitter_sec=jitter_sec
        )
        # Check intervals
        for i in range(len(timestamps) - 1):
            gap = (timestamps[i + 1] - timestamps[i]).total_seconds()
            # Should be approximately interval_sec, within jitter
            assert abs(gap - interval_sec) <= jitter_sec * 2

    def test_scheduled_periodic_within_bounds(self):
        """All timestamps must be within [window_start, window_end]."""
        window_start = datetime(2026, 1, 15, 0, 0, 0)
        window_end = window_start + timedelta(seconds=600)
        engine = TemporalEngine(seed=42)
        timestamps = engine.scheduled_periodic(window_start, window_end, interval_sec=60, jitter_sec=2)
        assert all(window_start <= ts <= window_end for ts in timestamps)

    def test_temporal_seed_reproducibility(self):
        """Same seed should produce identical results for all temporal methods."""
        window_start = datetime(2026, 1, 15, 0, 0, 0)
        large_window = window_start + timedelta(seconds=900)

        engine1 = TemporalEngine(seed=42)
        burst1 = engine1.burst_cluster(window_start, large_window, count=5)
        stealth1 = engine1.stealth_spread(window_start, large_window, count=3, min_gap_sec=120)
        sched1 = engine1.scheduled_periodic(window_start, large_window, interval_sec=60, jitter_sec=2)

        engine2 = TemporalEngine(seed=42)
        burst2 = engine2.burst_cluster(window_start, large_window, count=5)
        stealth2 = engine2.stealth_spread(window_start, large_window, count=3, min_gap_sec=120)
        sched2 = engine2.scheduled_periodic(window_start, large_window, interval_sec=60, jitter_sec=2)

        assert burst1 == burst2
        assert stealth1 == stealth2
        assert sched1 == sched2


class TestProvenancePatterns:
    """Test attack-grade provenance patterns for synthetic event generation."""

    def test_no_trigger_ref_returns_none(self):
        """no_trigger_ref() should return None."""
        gen = ProvenanceGenerator(seed=42)
        result = gen.no_trigger_ref()
        assert result is None

    def test_forged_trigger_ref_format(self):
        """forged_trigger_ref should look like a valid Cloud Scheduler path."""
        gen = ProvenanceGenerator(seed=42)
        result = gen.forged_trigger_ref("attacker@example.com")
        # Should contain "forged"
        assert "forged" in result
        # Should look like a Cloud Scheduler path
        assert "projects/synth-project/locations/us-central1/jobs/" in result

    def test_partial_trigger_ref_is_malformed(self):
        """partial_trigger_ref should be detectably incomplete."""
        gen = ProvenanceGenerator(seed=42)
        result = gen.partial_trigger_ref("attacker@example.com")
        # Should be a string
        assert isinstance(result, str)
        # Should be missing something (ends with /, has //, etc.)
        is_malformed = (
            result.endswith("/") or "//" in result or not result.startswith("projects/") or "deleted" in result
        )
        assert is_malformed

    def test_benign_vs_forged_different(self):
        """benign_trigger_ref and forged_trigger_ref should differ."""
        gen = ProvenanceGenerator(seed=42)
        benign = gen.benign_trigger_ref("service@example.com")
        forged = gen.forged_trigger_ref("attacker@example.com")
        assert benign != forged
        assert "forged" not in benign
        assert "forged" in forged

    def test_provenance_seed_reproducibility(self):
        """Same seed should produce identical results for all provenance methods."""
        gen1 = ProvenanceGenerator(seed=42)
        benign1 = gen1.benign_trigger_ref("actor1@example.com")
        forged1 = gen1.forged_trigger_ref("actor2@example.com")
        partial1 = gen1.partial_trigger_ref("actor3@example.com")

        gen2 = ProvenanceGenerator(seed=42)
        benign2 = gen2.benign_trigger_ref("actor1@example.com")
        forged2 = gen2.forged_trigger_ref("actor2@example.com")
        partial2 = gen2.partial_trigger_ref("actor3@example.com")

        assert benign1 == benign2
        assert forged1 == forged2
        assert partial1 == partial2
