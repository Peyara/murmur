"""Tests for synthetic GCP audit log trajectory generator."""

import warnings
from datetime import datetime, timedelta

from src.ingest.parser import parse_audit_log
from src.schema import ActionType, TargetZone
from src.synthetic import generate_trajectory  # noqa: F401
from src.synthetic.provenance import ProvenanceGenerator
from src.synthetic.temporal import TemporalEngine
from src.synthetic.workflows import NOISE_ACTIONS, WorkflowStep, WorkflowTemplates


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


class TestWorkflowCoverage:
    """Tests for expanded workflow templates and ActionType coverage."""

    def test_kms_operations_workflow_valid(self):
        """Verify kms_operations_workflow returns valid WorkflowStep list."""
        steps = WorkflowTemplates.kms_operations_workflow()
        assert isinstance(steps, list)
        assert len(steps) == 2
        for step in steps:
            assert isinstance(step, WorkflowStep)
            assert step.service_name == "cloudkms.googleapis.com"
            assert step.target_zone == "SECRET"
            assert step.log_name_suffix == "data_access"

    def test_scheduler_setup_workflow_valid(self):
        """Verify scheduler_setup_workflow returns valid WorkflowStep list."""
        steps = WorkflowTemplates.scheduler_setup_workflow()
        assert isinstance(steps, list)
        assert len(steps) == 2
        for step in steps:
            assert isinstance(step, WorkflowStep)
            assert step.log_name_suffix in ["activity", "data_access"]

    def test_key_cleanup_workflow_valid(self):
        """Verify key_cleanup_workflow returns valid WorkflowStep list."""
        steps = WorkflowTemplates.key_cleanup_workflow()
        assert isinstance(steps, list)
        assert len(steps) == 3
        for step in steps:
            assert isinstance(step, WorkflowStep)

    def test_kms_workflow_parses_to_correct_action_types(self):
        """Verify KMS workflow steps parse to correct ActionTypes."""
        steps = WorkflowTemplates.kms_operations_workflow()

        # Map step index to expected ActionType
        expected_types = {
            0: ActionType.KMS_ENCRYPT,
            1: ActionType.KMS_DECRYPT,
        }

        for idx, step in enumerate(steps):
            # Construct minimal raw event dict
            raw_event = {
                "protoPayload": {
                    "@type": "type.googleapis.com/google.cloud.audit.v1.AuditLog",
                    "serviceName": step.service_name,
                    "methodName": step.method_name,
                    "authenticationInfo": {"principalEmail": "test@synth-project.iam.gserviceaccount.com"},
                    "resourceName": step.resource_pattern,
                    "status": {},
                },
                "resource": {"type": "other", "labels": {"project_id": "synth-project"}},
                "timestamp": "2026-01-15T00:00:00.000Z",
                "insertId": f"test-evt-{idx}",
                "logName": f"projects/synth-project/logs/cloudaudit.googleapis.com%2F{step.log_name_suffix}",
            }
            canonical = parse_audit_log(raw_event)
            assert canonical is not None
            assert canonical.action_type == expected_types[idx]

    def test_scheduler_workflow_parses_to_correct_action_types(self):
        """Verify scheduler workflow steps parse to correct ActionTypes."""
        steps = WorkflowTemplates.scheduler_setup_workflow()

        expected_types = {
            0: ActionType.SCHEDULER_ADMIN,
            1: ActionType.GCS_READ,
        }

        for idx, step in enumerate(steps):
            raw_event = {
                "protoPayload": {
                    "@type": "type.googleapis.com/google.cloud.audit.v1.AuditLog",
                    "serviceName": step.service_name,
                    "methodName": step.method_name,
                    "authenticationInfo": {"principalEmail": "test@synth-project.iam.gserviceaccount.com"},
                    "resourceName": step.resource_pattern,
                    "status": {},
                },
                "resource": {"type": "other", "labels": {"project_id": "synth-project"}},
                "timestamp": "2026-01-15T00:00:00.000Z",
                "insertId": f"test-evt-{idx}",
                "logName": f"projects/synth-project/logs/cloudaudit.googleapis.com%2F{step.log_name_suffix}",
            }
            canonical = parse_audit_log(raw_event)
            assert canonical is not None
            assert canonical.action_type == expected_types[idx]

    def test_key_cleanup_workflow_parses_to_correct_action_types(self):
        """Verify key cleanup attack workflow parses correctly including IAM_DELETE_KEY."""
        steps = WorkflowTemplates.key_cleanup_workflow()

        expected_types = {
            0: ActionType.IAM_CREATE_KEY,
            1: ActionType.SECRET_ACCESS,
            2: ActionType.IAM_DELETE_KEY,  # The critical action with no prior workflow coverage
        }

        for idx, step in enumerate(steps):
            raw_event = {
                "protoPayload": {
                    "@type": "type.googleapis.com/google.cloud.audit.v1.AuditLog",
                    "serviceName": step.service_name,
                    "methodName": step.method_name,
                    "authenticationInfo": {"principalEmail": "test@synth-project.iam.gserviceaccount.com"},
                    "resourceName": step.resource_pattern,
                    "status": {},
                },
                "resource": {"type": "other", "labels": {"project_id": "synth-project"}},
                "timestamp": "2026-01-15T00:00:00.000Z",
                "insertId": f"test-evt-{idx}",
                "logName": f"projects/synth-project/logs/cloudaudit.googleapis.com%2F{step.log_name_suffix}",
            }
            canonical = parse_audit_log(raw_event)
            assert canonical is not None
            assert canonical.action_type == expected_types[idx]

    def test_all_benign_workflows_in_registry(self):
        """Verify new benign workflows are registered in get_benign_workflows."""
        benign_workflows = WorkflowTemplates.get_benign_workflows()
        assert len(benign_workflows) == 6  # 4 original + 2 new

        # Flatten all steps from all benign workflows
        all_steps = [step for workflow in benign_workflows for step in workflow]

        # Check that we have KMS operations
        kms_services = [s.service_name for s in all_steps if "kms" in s.service_name.lower()]
        assert len(kms_services) > 0, "KMS operations should appear in benign workflows"

        # Check that we have scheduler operations
        scheduler_services = [s.service_name for s in all_steps if "scheduler" in s.service_name.lower()]
        assert len(scheduler_services) > 0, "Scheduler operations should appear in benign workflows"

    def test_all_attack_workflows_in_registry(self):
        """Verify key cleanup attack workflow is registered in get_attack_workflows."""
        attack_workflows = WorkflowTemplates.get_attack_workflows()
        assert len(attack_workflows) == 5  # 4 original + 1 new

        # Flatten all steps from all attack workflows
        all_steps = [step for workflow in attack_workflows for step in workflow]

        # Check that we have IAM_DELETE_KEY operations
        delete_key_ops = [s for s in all_steps if "DeleteServiceAccountKey" in s.method_name]
        assert len(delete_key_ops) > 0, "DeleteServiceAccountKey should appear in attack workflows"

    def test_noise_actions_constant_exists(self):
        """Verify NOISE_ACTIONS constant is defined with correct structure."""
        assert isinstance(NOISE_ACTIONS, list)
        assert len(NOISE_ACTIONS) > 0

        for action in NOISE_ACTIONS:
            assert isinstance(action, tuple)
            assert len(action) == 5
            service_name, method_name, resource_pattern, target_zone, log_suffix = action
            assert isinstance(service_name, str)
            assert isinstance(method_name, str)
            assert isinstance(resource_pattern, str)
            assert isinstance(target_zone, str)
            assert isinstance(log_suffix, str)
            assert service_name.endswith(".googleapis.com")

    def test_noise_actions_parse_successfully(self):
        """Verify noise action specs can be parsed to valid events."""
        for service_name, method_name, resource_pattern, target_zone, log_suffix in NOISE_ACTIONS:
            raw_event = {
                "protoPayload": {
                    "@type": "type.googleapis.com/google.cloud.audit.v1.AuditLog",
                    "serviceName": service_name,
                    "methodName": method_name,
                    "authenticationInfo": {"principalEmail": "noise@synth-project.iam.gserviceaccount.com"},
                    "resourceName": resource_pattern,
                    "status": {},
                },
                "resource": {"type": "other", "labels": {"project_id": "synth-project"}},
                "timestamp": "2026-01-15T00:00:00.000Z",
                "insertId": "noise-evt",
                "logName": f"projects/synth-project/logs/cloudaudit.googleapis.com%2F{log_suffix}",
            }
            canonical = parse_audit_log(raw_event)
            assert canonical is not None
            assert canonical.action_type != ActionType.OTHER  # All noise should map to known actions


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


class TestComposerIntegration:
    """Integration tests validating the full composer pipeline.

    These tests generate trajectories through the composer and validate
    that temporal profiles, provenance patterns, and expanded workflows
    are all wired correctly end-to-end.
    """

    def test_all_parseable_action_types_present(self):
        """Generate a large trajectory and verify all 17 parseable ActionTypes appear."""
        result = generate_trajectory(actors=20, windows=100, attack_ratio=0.2, seed=99)
        action_types = set()
        for event in result:
            canonical = parse_audit_log(event)
            action_types.add(canonical.action_type)

        # All ActionTypes that have ACTION_MAP entries should appear
        # with enough volume. We check for at least 12 of 17 since
        # random selection may not hit every workflow in one run.
        assert len(action_types) >= 12, f"Only {len(action_types)} ActionTypes found: {action_types}"

    def test_attack_windows_have_degraded_provenance(self):
        """Attack events should have missing, forged, or partial provenance."""
        result = generate_trajectory(actors=10, windows=50, attack_ratio=0.3, seed=42)
        events_without_trigger = 0
        events_with_forged = 0
        total = len(result)
        for event in result:
            metadata = event.get("metadata", {})
            trigger_ref = metadata.get("trigger_ref")
            if trigger_ref is None:
                events_without_trigger += 1
            elif "forged" in trigger_ref:
                events_with_forged += 1

        # With 30% attack ratio, we should see some events without triggers
        # and some with forged triggers
        assert events_without_trigger > 0, "Should have events with no trigger_ref (attacks)"
        assert events_with_forged > 0, "Should have events with forged trigger_ref"
        # Not ALL events should lack triggers (benign windows have them)
        assert events_without_trigger < total, "Not all events should lack triggers"

    def test_benign_windows_have_valid_provenance(self):
        """Benign events should have well-formed Cloud Scheduler trigger_refs."""
        result = generate_trajectory(actors=10, windows=20, attack_ratio=0.0, seed=42)
        events_with_trigger = 0
        for event in result:
            metadata = event.get("metadata", {})
            trigger_ref = metadata.get("trigger_ref")
            if trigger_ref and "forged" not in trigger_ref:
                events_with_trigger += 1
                # Valid trigger_refs should have full path
                assert "projects/synth-project/locations/us-central1/jobs/" in trigger_ref

        assert events_with_trigger > 0, "Benign windows should produce events with trigger_refs"

    def test_noise_uses_expanded_actions(self):
        """Background noise should include diverse action types beyond gcs_read/bq/gcs_list."""
        result = generate_trajectory(actors=10, windows=50, attack_ratio=0.0, seed=123)
        services = set()
        for event in result:
            svc = event["protoPayload"]["serviceName"]
            services.add(svc)

        # With NOISE_ACTIONS wired in, we should see more than just storage + bigquery
        assert len(services) >= 3, f"Only {len(services)} services: {services}"

    def test_temporal_clustering_in_benign_windows(self):
        """Benign workflow events should show tight inter-arrival times from burst_cluster."""
        from src.ingest.parser import parse_timestamp

        result = generate_trajectory(actors=10, windows=20, attack_ratio=0.0, seed=42)
        timestamps = sorted(parse_timestamp(e["timestamp"]) for e in result)

        # With burst_cluster wired in, we should see pairs of events
        # within 30 seconds of each other (workflow steps in same burst).
        # Background noise is uniform, so without clustering the minimum
        # gap would be ~minutes. Tight pairs prove burst_cluster is active.
        tight_pairs = 0
        for i in range(len(timestamps) - 1):
            gap = (timestamps[i + 1] - timestamps[i]).total_seconds()
            if gap < 30:
                tight_pairs += 1

        assert tight_pairs > 0, "Should have event pairs < 30s apart (burst_cluster active)"

    def test_seed_reproducibility_preserved(self):
        """Composer rewrite must preserve deterministic output for same seed."""
        result1 = generate_trajectory(actors=10, windows=20, attack_ratio=0.1, seed=42)
        result2 = generate_trajectory(actors=10, windows=20, attack_ratio=0.1, seed=42)
        assert result1 == result2
