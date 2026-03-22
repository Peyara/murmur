"""Tests for GCP audit log parser. TDD — tests written before implementation."""

import json
import pytest
from datetime import datetime

from src.schema import ActionType, ActorType, ProvenanceLevel, TargetZone
from src.ingest.parser import parse_audit_log


def _make_raw_log(
    service_name: str,
    method_name: str,
    principal_email: str = "test-sa@project.iam.gserviceaccount.com",
    resource_name: str = "projects/murmur-sandbox/some-resource",
    timestamp: str = "2026-03-22T10:05:30.123Z",
    insert_id: str = "insert-001",
    status: dict | None = None,
    metadata: dict | None = None,
) -> dict:
    """Helper to build a minimal GCP audit log entry."""
    log = {
        "protoPayload": {
            "@type": "type.googleapis.com/google.cloud.audit.v1.AuditLog",
            "serviceName": service_name,
            "methodName": method_name,
            "authenticationInfo": {"principalEmail": principal_email},
            "resourceName": resource_name,
            "status": status or {},
        },
        "resource": {
            "type": "some_resource",
            "labels": {"project_id": "murmur-sandbox"},
        },
        "timestamp": timestamp,
        "insertId": insert_id,
        "logName": "projects/murmur-sandbox/logs/cloudaudit.googleapis.com%2Factivity",
    }
    if metadata:
        log["metadata"] = metadata
    return log


# ── Action type mapping tests (one per GCP method) ──────────────────────


class TestActionTypeMapping:
    def test_iam_set_policy(self):
        raw = _make_raw_log("iam.googleapis.com", "SetIamPolicy")
        event = parse_audit_log(raw)
        assert event.action_type == ActionType.IAM_SET_POLICY
        assert event.target_zone == TargetZone.CONTROL

    def test_iam_create_sa(self):
        raw = _make_raw_log(
            "iam.googleapis.com",
            "google.iam.admin.v1.CreateServiceAccount",
            resource_name="projects/murmur-sandbox/serviceAccounts/new-sa@proj.iam.gserviceaccount.com",
        )
        event = parse_audit_log(raw)
        assert event.action_type == ActionType.IAM_CREATE_SA
        assert event.target_zone == TargetZone.IDENTITY

    def test_iam_create_key(self):
        raw = _make_raw_log(
            "iam.googleapis.com",
            "google.iam.admin.v1.CreateServiceAccountKey",
            resource_name="projects/murmur-sandbox/serviceAccounts/sa@proj.iam.gserviceaccount.com/keys/key-123",
        )
        event = parse_audit_log(raw)
        assert event.action_type == ActionType.IAM_CREATE_KEY
        assert event.target_zone == TargetZone.IDENTITY

    def test_iam_delete_key(self):
        raw = _make_raw_log(
            "iam.googleapis.com",
            "google.iam.admin.v1.DeleteServiceAccountKey",
            resource_name="projects/murmur-sandbox/serviceAccounts/sa@proj.iam.gserviceaccount.com/keys/key-123",
        )
        event = parse_audit_log(raw)
        assert event.action_type == ActionType.IAM_DELETE_KEY
        assert event.target_zone == TargetZone.IDENTITY

    def test_iam_impersonate_access_token(self):
        raw = _make_raw_log(
            "iamcredentials.googleapis.com",
            "GenerateAccessToken",
            resource_name="projects/-/serviceAccounts/target-sa@proj.iam.gserviceaccount.com",
        )
        event = parse_audit_log(raw)
        assert event.action_type == ActionType.IAM_IMPERSONATE
        assert event.target_zone == TargetZone.IDENTITY

    def test_iam_impersonate_id_token(self):
        raw = _make_raw_log(
            "iamcredentials.googleapis.com",
            "GenerateIdToken",
            resource_name="projects/-/serviceAccounts/target-sa@proj.iam.gserviceaccount.com",
        )
        event = parse_audit_log(raw)
        assert event.action_type == ActionType.IAM_IMPERSONATE
        assert event.target_zone == TargetZone.IDENTITY

    def test_secret_access(self):
        raw = _make_raw_log(
            "secretmanager.googleapis.com",
            "google.cloud.secretmanager.v1.SecretManagerService.AccessSecretVersion",
            resource_name="projects/murmur-sandbox/secrets/secret_high/versions/latest",
        )
        event = parse_audit_log(raw)
        assert event.action_type == ActionType.SECRET_ACCESS
        assert event.target_zone == TargetZone.SECRET

    def test_kms_decrypt(self):
        raw = _make_raw_log(
            "cloudkms.googleapis.com",
            "Decrypt",
            resource_name="projects/murmur-sandbox/locations/us-central1/keyRings/ring/cryptoKeys/key",
        )
        event = parse_audit_log(raw)
        assert event.action_type == ActionType.KMS_DECRYPT
        assert event.target_zone == TargetZone.SECRET

    def test_gcs_read(self):
        raw = _make_raw_log(
            "storage.googleapis.com",
            "storage.objects.get",
            resource_name="projects/_/buckets/my-bucket/objects/file.csv",
        )
        event = parse_audit_log(raw)
        assert event.action_type == ActionType.GCS_READ
        assert event.target_zone == TargetZone.DATA

    def test_gcs_write(self):
        raw = _make_raw_log(
            "storage.googleapis.com",
            "storage.objects.create",
            resource_name="projects/_/buckets/my-bucket/objects/output.json",
        )
        event = parse_audit_log(raw)
        assert event.action_type == ActionType.GCS_WRITE
        assert event.target_zone == TargetZone.DATA

    def test_bq_job_submit(self):
        raw = _make_raw_log(
            "bigquery.googleapis.com",
            "jobservice.insert",
            resource_name="projects/murmur-sandbox/jobs/bq-job-001",
        )
        event = parse_audit_log(raw)
        assert event.action_type == ActionType.BQ_JOB_SUBMIT
        assert event.target_zone == TargetZone.DATA

    def test_compute_metadata_change(self):
        raw = _make_raw_log(
            "compute.googleapis.com",
            "v1.compute.instances.setMetadata",
            resource_name="projects/murmur-sandbox/zones/us-central1-a/instances/vm-1",
        )
        event = parse_audit_log(raw)
        assert event.action_type == ActionType.COMPUTE_METADATA_CHANGE
        assert event.target_zone == TargetZone.COMPUTE

    def test_resource_manager_set_iam_policy(self):
        raw = _make_raw_log(
            "cloudresourcemanager.googleapis.com",
            "SetIamPolicy",
            resource_name="projects/murmur-sandbox",
        )
        event = parse_audit_log(raw)
        assert event.action_type == ActionType.IAM_SET_POLICY
        assert event.target_zone == TargetZone.CONTROL

    def test_unknown_service_maps_to_other(self):
        raw = _make_raw_log(
            "unknownservice.googleapis.com",
            "SomeUnknownMethod",
        )
        event = parse_audit_log(raw)
        assert event.action_type == ActionType.OTHER
        assert event.target_zone == TargetZone.DATA  # default zone


# ── Field extraction tests ──────────────────────────────────────────────


class TestFieldExtraction:
    def test_actor_id_from_principal_email(self):
        raw = _make_raw_log(
            "storage.googleapis.com",
            "storage.objects.get",
            principal_email="user@example.com",
        )
        event = parse_audit_log(raw)
        assert event.actor_id == "user@example.com"

    def test_actor_type_service_account(self):
        raw = _make_raw_log(
            "storage.googleapis.com",
            "storage.objects.get",
            principal_email="my-sa@project.iam.gserviceaccount.com",
        )
        event = parse_audit_log(raw)
        assert event.actor_type == ActorType.SERVICE_ACCOUNT

    def test_actor_type_human(self):
        raw = _make_raw_log(
            "storage.googleapis.com",
            "storage.objects.get",
            principal_email="user@example.com",
        )
        event = parse_audit_log(raw)
        assert event.actor_type == ActorType.HUMAN

    def test_target_id_from_resource_name(self):
        raw = _make_raw_log(
            "secretmanager.googleapis.com",
            "AccessSecretVersion",
            resource_name="projects/murmur-sandbox/secrets/secret_high/versions/latest",
        )
        event = parse_audit_log(raw)
        assert event.target_id == "projects/murmur-sandbox/secrets/secret_high/versions/latest"

    def test_timestamp_parsing(self):
        raw = _make_raw_log(
            "storage.googleapis.com",
            "storage.objects.get",
            timestamp="2026-03-22T10:05:30.123Z",
        )
        event = parse_audit_log(raw)
        assert event.ts == datetime(2026, 3, 22, 10, 5, 30, 123000)

    def test_window_start_floored_to_15_min(self):
        raw = _make_raw_log(
            "storage.googleapis.com",
            "storage.objects.get",
            timestamp="2026-03-22T10:23:45.000Z",
        )
        event = parse_audit_log(raw)
        assert event.window_start == datetime(2026, 3, 22, 10, 15, 0)

    def test_window_start_exact_boundary(self):
        raw = _make_raw_log(
            "storage.googleapis.com",
            "storage.objects.get",
            timestamp="2026-03-22T10:30:00.000Z",
        )
        event = parse_audit_log(raw)
        assert event.window_start == datetime(2026, 3, 22, 10, 30, 0)

    def test_action_subtype_is_method_name(self):
        raw = _make_raw_log(
            "iam.googleapis.com",
            "google.iam.admin.v1.CreateServiceAccountKey",
        )
        event = parse_audit_log(raw)
        assert event.action_subtype == "google.iam.admin.v1.CreateServiceAccountKey"

    def test_project_id_from_resource_labels(self):
        raw = _make_raw_log("storage.googleapis.com", "storage.objects.get")
        event = parse_audit_log(raw)
        assert event.project_id == "murmur-sandbox"

    def test_raw_ref_from_logname_and_insert_id(self):
        raw = _make_raw_log(
            "storage.googleapis.com",
            "storage.objects.get",
            insert_id="abc-123",
        )
        event = parse_audit_log(raw)
        assert "abc-123" in event.raw_ref

    def test_trigger_ref_from_metadata(self):
        raw = _make_raw_log(
            "storage.googleapis.com",
            "storage.objects.get",
            metadata={"trigger_ref": "sched-exec-001"},
        )
        event = parse_audit_log(raw)
        assert event.trigger_ref == "sched-exec-001"

    def test_no_trigger_ref_when_absent(self):
        raw = _make_raw_log("storage.googleapis.com", "storage.objects.get")
        event = parse_audit_log(raw)
        assert event.trigger_ref is None

    def test_provenance_level_none_without_trigger(self):
        raw = _make_raw_log("iam.googleapis.com", "SetIamPolicy")
        event = parse_audit_log(raw)
        assert event.provenance_level == ProvenanceLevel.NONE


# ── Edge case tests ─────────────────────────────────────────────────────


class TestEdgeCases:
    def test_missing_authentication_info(self):
        raw = _make_raw_log("storage.googleapis.com", "storage.objects.get")
        del raw["protoPayload"]["authenticationInfo"]
        event = parse_audit_log(raw)
        assert event.actor_id == "unknown"
        assert event.actor_type == ActorType.UNKNOWN

    def test_missing_resource_name(self):
        raw = _make_raw_log("storage.googleapis.com", "storage.objects.get")
        del raw["protoPayload"]["resourceName"]
        event = parse_audit_log(raw)
        assert event.target_id == "unknown"

    def test_missing_timestamp_raises(self):
        raw = _make_raw_log("storage.googleapis.com", "storage.objects.get")
        del raw["timestamp"]
        with pytest.raises((KeyError, ValueError)):
            parse_audit_log(raw)

    def test_event_id_is_deterministic(self):
        raw = _make_raw_log(
            "storage.googleapis.com",
            "storage.objects.get",
            timestamp="2026-03-22T10:00:00.000Z",
            insert_id="fixed-id",
        )
        e1 = parse_audit_log(raw)
        e2 = parse_audit_log(raw)
        assert e1.event_id == e2.event_id
        assert len(e1.event_id) > 0

    def test_different_inputs_different_event_ids(self):
        raw1 = _make_raw_log(
            "storage.googleapis.com",
            "storage.objects.get",
            insert_id="id-1",
        )
        raw2 = _make_raw_log(
            "storage.googleapis.com",
            "storage.objects.get",
            insert_id="id-2",
        )
        e1 = parse_audit_log(raw1)
        e2 = parse_audit_log(raw2)
        assert e1.event_id != e2.event_id


# ── EXFIL_RISK zone override tests ─────────────────────────────────────


class TestExfilRiskZone:
    def test_external_gcs_bucket_maps_to_exfil_risk(self):
        raw = _make_raw_log(
            "storage.googleapis.com",
            "storage.objects.get",
            resource_name="projects/_/buckets/external-data-export/objects/dump.tar.gz",
        )
        event = parse_audit_log(raw)
        assert event.target_zone == TargetZone.EXFIL_RISK

    def test_public_gcs_bucket_maps_to_exfil_risk(self):
        raw = _make_raw_log(
            "storage.googleapis.com",
            "storage.objects.create",
            resource_name="projects/_/buckets/public-shared/objects/leaked.csv",
        )
        event = parse_audit_log(raw)
        assert event.target_zone == TargetZone.EXFIL_RISK

    def test_normal_gcs_bucket_stays_data(self):
        raw = _make_raw_log(
            "storage.googleapis.com",
            "storage.objects.get",
            resource_name="projects/_/buckets/internal-data/objects/report.csv",
        )
        event = parse_audit_log(raw)
        assert event.target_zone == TargetZone.DATA
