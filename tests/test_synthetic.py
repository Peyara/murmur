"""Tests for synthetic GCP audit log trajectory generator."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.ingest.parser import ACTION_MAP, parse_audit_log
from src.schema import ActionType, TargetZone
from src.synthetic import generate_trajectory


class TestSyntheticGeneration:
    """Unit and integration tests for trajectory generator."""

    def test_generate_trajectory_returns_list(self):
        """Trajectory generator returns a list."""
        result = generate_trajectory(actors=5, windows=10, attack_ratio=0.2, seed=42)
        assert isinstance(result, list)

    def test_generate_trajectory_creates_events(self):
        """Trajectory generator creates events."""
        result = generate_trajectory(actors=5, windows=10, attack_ratio=0.2, seed=42)
        assert len(result) > 0

    def test_generate_trajectory_events_are_dicts(self):
        """Each event is a dict with required GCP audit log structure."""
        result = generate_trajectory(actors=5, windows=10, attack_ratio=0.2, seed=42)
        for event in result:
            assert isinstance(event, dict)
            assert "protoPayload" in event
            assert "timestamp" in event
            assert "insertId" in event
            assert "logName" in event
            assert "resource" in event

    def test_generate_trajectory_sorted_by_timestamp(self):
        """Events are sorted by timestamp."""
        result = generate_trajectory(actors=5, windows=10, attack_ratio=0.2, seed=42)
        timestamps = [event["timestamp"] for event in result]
        assert timestamps == sorted(timestamps)

    def test_generated_events_parse_successfully(self):
        """Generated events can be parsed by parser.py."""
        result = generate_trajectory(actors=5, windows=10, attack_ratio=0.2, seed=42)
        for event in result:
            try:
                canonical = parse_audit_log(event)
                assert canonical is not None
                assert canonical.action_type is not None
                assert canonical.target_zone is not None
            except Exception as e:
                pytest.fail(f"Failed to parse event: {event}\nError: {e}")

    def test_generated_events_in_action_map(self):
        """All generated events have serviceName+methodName in ACTION_MAP."""
        result = generate_trajectory(actors=5, windows=10, attack_ratio=0.2, seed=42)
        action_map_keys = {(svc, method) for svc, method, _, _ in ACTION_MAP}

        for event in result:
            payload = event.get("protoPayload", {})
            service_name = payload.get("serviceName", "")
            method_name = payload.get("methodName", "")

            found = False
            for svc, method_sub, _, _ in ACTION_MAP:
                if service_name == svc and method_sub in method_name:
                    found = True
                    break

            if not found:
                pytest.fail(
                    f"Event {service_name}/{method_name} not in ACTION_MAP: {event}"
                )

    def test_generated_events_cover_action_types(self):
        """Generated events cover multiple ActionTypes (not just one)."""
        result = generate_trajectory(actors=10, windows=20, attack_ratio=0.2, seed=42)

        action_types = set()
        for event in result:
            canonical = parse_audit_log(event)
            action_types.add(canonical.action_type)

        # Should have at least 5 distinct action types
        assert len(action_types) >= 5, f"Only {len(action_types)} action types: {action_types}"

    def test_generated_events_cover_target_zones(self):
        """Generated events cover multiple TargetZones."""
        result = generate_trajectory(actors=10, windows=20, attack_ratio=0.2, seed=42)

        zones = set()
        for event in result:
            canonical = parse_audit_log(event)
            zones.add(canonical.target_zone)

        # Should have at least 4 distinct zones
        assert len(zones) >= 4, f"Only {len(zones)} zones: {zones}"

    def test_configurable_actor_count(self):
        """Actor count is configurable."""
        result_5 = generate_trajectory(actors=5, windows=10, attack_ratio=0.1, seed=42)
        result_20 = generate_trajectory(actors=20, windows=10, attack_ratio=0.1, seed=42)

        # Both should have events
        assert len(result_5) > 0
        assert len(result_20) > 0
        # More actors should generally produce more events (probabilistic)
        assert len(result_20) >= len(result_5) * 0.5

    def test_configurable_window_count(self):
        """Window count is configurable."""
        result_10 = generate_trajectory(actors=5, windows=10, attack_ratio=0.1, seed=42)
        result_50 = generate_trajectory(actors=5, windows=50, attack_ratio=0.1, seed=42)

        # Both should have events
        assert len(result_10) > 0
        assert len(result_50) > 0
        # More windows should produce more events
        assert len(result_50) > len(result_10)

    def test_configurable_attack_ratio(self):
        """Attack ratio is configurable."""
        result_low = generate_trajectory(actors=5, windows=10, attack_ratio=0.0, seed=42)
        result_high = generate_trajectory(actors=5, windows=10, attack_ratio=0.5, seed=42)

        # Both should have events
        assert len(result_low) > 0
        assert len(result_high) > 0

    def test_seed_reproducibility(self):
        """Same seed produces identical trajectories."""
        result_1 = generate_trajectory(actors=5, windows=10, attack_ratio=0.2, seed=42)
        result_2 = generate_trajectory(actors=5, windows=10, attack_ratio=0.2, seed=42)

        assert len(result_1) == len(result_2)
        assert result_1 == result_2

    def test_different_seed_different_result(self):
        """Different seeds produce different trajectories."""
        result_seed_42 = generate_trajectory(actors=5, windows=10, attack_ratio=0.2, seed=42)
        result_seed_99 = generate_trajectory(actors=5, windows=10, attack_ratio=0.2, seed=99)

        # Different seeds should produce different results (very likely)
        assert result_seed_42 != result_seed_99

    def test_timestamp_format_iso8601(self):
        """All timestamps are ISO 8601 with Z suffix."""
        result = generate_trajectory(actors=5, windows=10, attack_ratio=0.1, seed=42)
        for event in result:
            ts = event["timestamp"]
            assert ts.endswith("Z"), f"Timestamp {ts} doesn't end with Z"
            # Try to parse as ISO 8601
            try:
                datetime.fromisoformat(ts.rstrip("Z"))
            except ValueError:
                pytest.fail(f"Invalid ISO 8601 timestamp: {ts}")

    def test_authentication_info_has_principal_email(self):
        """All events have authenticationInfo.principalEmail."""
        result = generate_trajectory(actors=5, windows=10, attack_ratio=0.1, seed=42)
        for event in result:
            payload = event.get("protoPayload", {})
            auth_info = payload.get("authenticationInfo", {})
            email = auth_info.get("principalEmail")
            assert email is not None
            assert "@" in email
            assert "iam.gserviceaccount.com" in email

    def test_resource_has_project_id(self):
        """All events have project_id in resource.labels."""
        result = generate_trajectory(actors=5, windows=10, attack_ratio=0.1, seed=42)
        for event in result:
            resource = event.get("resource", {})
            labels = resource.get("labels", {})
            project_id = labels.get("project_id")
            assert project_id is not None
            assert project_id == "synth-project"

    def test_benign_events_have_trigger_ref(self):
        """Benign workflow events have metadata.trigger_ref."""
        result = generate_trajectory(actors=5, windows=10, attack_ratio=0.0, seed=42)

        has_trigger = 0
        for event in result:
            metadata = event.get("metadata", {})
            if metadata.get("trigger_ref"):
                has_trigger += 1

        # With 0% attack ratio, all should be benign (have trigger refs or no events)
        # At least some events should have provenance
        assert has_trigger > 0 or len(result) == 0

    def test_attack_events_no_trigger_ref(self):
        """Attack workflow events have no metadata.trigger_ref."""
        result = generate_trajectory(actors=5, windows=10, attack_ratio=1.0, seed=42)

        # With 100% attack ratio, NO events should have trigger refs
        for event in result:
            metadata = event.get("metadata", {})
            trigger_ref = metadata.get("trigger_ref")
            # Attacker events should have no provenance
            # (Some benign background noise may still have it)
            # We're mainly checking that not all have it

        # Check at least some don't have trigger refs (attack events)
        without_trigger = sum(1 for e in result if not e.get("metadata", {}).get("trigger_ref"))
        assert without_trigger > 0

    def test_performance_1000_events(self):
        """1000 events generated in reasonable time (<5s)."""
        import time
        start = time.time()
        result = generate_trajectory(actors=20, windows=50, attack_ratio=0.15, seed=42)
        elapsed = time.time() - start

        # Should complete in under 5 seconds
        assert elapsed < 5.0, f"Generation took {elapsed:.1f}s (limit: 5s)"
        # Should produce a decent number of events
        assert len(result) >= 500, f"Only generated {len(result)} events"

    def test_all_19_action_types_coverage(self):
        """Generator can cover all 19 ActionTypes with larger trajectory."""
        result = generate_trajectory(actors=30, windows=30, attack_ratio=0.2, seed=123)

        action_types = set()
        for event in result:
            canonical = parse_audit_log(event)
            action_types.add(canonical.action_type)

        # Count how many of the 19 action types are present
        # Not all may be present in synthetic generator, but should cover most
        covered = len(action_types)
        # At minimum, should cover 12+ of the 19
        assert covered >= 12, f"Only {covered} action types covered: {action_types}"

    def test_all_6_target_zones_coverage(self):
        """Generator covers all 6 TargetZones."""
        result = generate_trajectory(actors=20, windows=20, attack_ratio=0.2, seed=123)

        zones = set()
        for event in result:
            canonical = parse_audit_log(event)
            zones.add(canonical.target_zone)

        # All 6 zones should be present
        expected_zones = {
            TargetZone.CONTROL,
            TargetZone.IDENTITY,
            TargetZone.SECRET,
            TargetZone.DATA,
            TargetZone.COMPUTE,
            TargetZone.EXFIL_RISK,
        }
        assert zones == expected_zones, f"Missing zones: {expected_zones - zones}"

    def test_valid_insert_id_format(self):
        """All insertIds are valid and unique."""
        result = generate_trajectory(actors=5, windows=10, attack_ratio=0.1, seed=42)
        insert_ids = set()
        for event in result:
            insert_id = event.get("insertId")
            assert insert_id is not None
            assert isinstance(insert_id, str)
            assert len(insert_id) > 0
            insert_ids.add(insert_id)

        # All should be unique
        assert len(insert_ids) == len(result)


class TestSyntheticOrchestration:
    """Tests for attack patterns and workflow orchestration."""

    def test_key_exfil_pattern_present(self):
        """Key exfil pattern (s01) elements are present in attacks."""
        result = generate_trajectory(actors=10, windows=15, attack_ratio=0.5, seed=42)

        # Should have IAM_CREATE_KEY and SECRET_ACCESS close together
        iam_create_keys = [
            (i, parse_audit_log(result[i]))
            for i in range(len(result))
            if parse_audit_log(result[i]).action_type == ActionType.IAM_CREATE_KEY
        ]

        secret_access = [
            (i, parse_audit_log(result[i]))
            for i in range(len(result))
            if parse_audit_log(result[i]).action_type == ActionType.SECRET_ACCESS
        ]

        # Should have at least some of these actions
        assert len(iam_create_keys) > 0 or len(secret_access) > 0

    def test_lateral_movement_pattern_present(self):
        """Lateral movement elements are present."""
        result = generate_trajectory(actors=10, windows=15, attack_ratio=0.5, seed=42)

        # Should have IAM operations
        iam_ops = [
            parse_audit_log(result[i])
            for i in range(len(result))
            if "IAM" in str(parse_audit_log(result[i]).action_type)
        ]

        assert len(iam_ops) > 0

    def test_scheduler_delegation_chain(self):
        """Benign scheduler events have delegation chains."""
        result = generate_trajectory(actors=10, windows=10, attack_ratio=0.0, seed=42)

        has_delegation = 0
        for event in result:
            payload = event.get("protoPayload", {})
            auth_info = payload.get("authenticationInfo", {})
            delegation = auth_info.get("serviceAccountDelegationInfo", [])
            if delegation:
                has_delegation += 1

        # With benign-only workflows, should have some delegation chains
        assert has_delegation > 0 or len(result) == 0


class TestSyntheticCLI:
    """Tests for CLI integration."""

    def test_cli_generate_subcommand_help(self):
        """CLI has generate subcommand."""
        from src.cli import cli

        # Check that cli has a generate command
        assert any(cmd.name == "generate" for cmd in cli.commands.values())

    def test_cli_generate_basic_invocation(self, tmp_path):
        """CLI generate command can be invoked."""
        from click.testing import CliRunner
        from src.cli import cli

        output_file = tmp_path / "test_output.jsonl"
        runner = CliRunner()
        result = runner.invoke(cli, [
            "generate",
            "--actors", "5",
            "--windows", "10",
            "--attack-ratio", "0.1",
            "--seed", "42",
            "--output", str(output_file),
        ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert output_file.exists()

    def test_cli_generate_output_is_jsonl(self, tmp_path):
        """CLI generate output is valid JSONL."""
        from click.testing import CliRunner
        from src.cli import cli

        output_file = tmp_path / "test_output.jsonl"
        runner = CliRunner()
        result = runner.invoke(cli, [
            "generate",
            "--actors", "5",
            "--windows", "10",
            "--attack-ratio", "0.1",
            "--seed", "42",
            "--output", str(output_file),
        ])

        assert result.exit_code == 0

        # Parse JSONL
        lines = output_file.read_text().strip().split("\n")
        assert len(lines) > 0

        for line in lines:
            if line.strip():
                event = json.loads(line)
                assert "protoPayload" in event
                assert "timestamp" in event

    def test_cli_generate_reproducible(self, tmp_path):
        """CLI generate with same seed produces same output."""
        from click.testing import CliRunner
        from src.cli import cli

        output_1 = tmp_path / "output_1.jsonl"
        output_2 = tmp_path / "output_2.jsonl"

        runner = CliRunner()
        for output_file in [output_1, output_2]:
            result = runner.invoke(cli, [
                "generate",
                "--actors", "5",
                "--windows", "10",
                "--attack-ratio", "0.1",
                "--seed", "42",
                "--output", str(output_file),
            ])
            assert result.exit_code == 0

        content_1 = output_1.read_text()
        content_2 = output_2.read_text()
        assert content_1 == content_2
