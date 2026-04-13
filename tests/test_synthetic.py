"""Tests for synthetic GCP audit log trajectory generator."""

from src.ingest.parser import parse_audit_log
from src.schema import ActionType, TargetZone
from src.synthetic import generate_trajectory  # noqa: F401
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
