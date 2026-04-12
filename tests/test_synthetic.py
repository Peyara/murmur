"""Tests for synthetic GCP audit log trajectory generator."""

from src.ingest.parser import parse_audit_log
from src.schema import TargetZone
from src.synthetic import generate_trajectory  # noqa: F401


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
        result = generate_trajectory(
            actors=20, windows=20, attack_ratio=0.2, seed=123
        )
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
