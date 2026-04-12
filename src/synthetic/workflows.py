"""WorkflowTemplates — composable action sequences (benign and attack patterns).

GCP API Mapping Table
=====================
This table documents how each synthetic action maps to real GCP APIs.
Use this for follow-up sessions implementing real `gcloud` calls.

| Generator Action          | GCP Service              | GCP Method                    | Real API Call                                      |
|---------------------------|--------------------------|-------------------------------|----------------------------------------------------|
| IAM_SET_POLICY            | cloudresourcemanager/iam | SetIamPolicy                  | gcloud projects add-iam-policy-binding             |
| IAM_CREATE_SA             | iam                      | CreateServiceAccount          | gcloud iam service-accounts create                 |
| IAM_CREATE_KEY            | iam                      | CreateServiceAccountKey       | gcloud iam service-accounts keys create            |
| IAM_DELETE_KEY            | iam                      | DeleteServiceAccountKey       | gcloud iam service-accounts keys delete            |
| IAM_IMPERSONATE           | iamcredentials           | GenerateAccessToken           | gcloud auth print-access-token --impersonate-...  |
| SECRET_ACCESS             | secretmanager            | AccessSecretVersion           | gcloud secrets versions access                     |
| SECRET_ADMIN              | secretmanager            | CreateSecret / AddSecretVersion | gcloud secrets create / gcloud secrets versions add |
| KMS_DECRYPT               | cloudkms                 | Decrypt                       | gcloud kms decrypt                                 |
| KMS_ENCRYPT               | cloudkms                 | Encrypt                       | gcloud kms encrypt                                 |
| GCS_READ                  | storage                  | storage.objects.get           | gsutil cp gs://...                                 |
| GCS_WRITE                 | storage                  | storage.objects.create        | gsutil cp ... gs://...                             |
| GCS_LIST                  | storage                  | storage.objects.list          | gsutil ls gs://...                                 |
| BQ_JOB_SUBMIT             | bigquery                 | jobservice.insert             | bq query                                           |
| COMPUTE_CREATE            | compute                  | instances.insert              | gcloud compute instances create                    |
| SCHEDULER_ADMIN           | cloudscheduler           | CreateJob                     | gcloud scheduler jobs create                       |
"""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class WorkflowStep:
    """Single step in a workflow sequence."""

    service_name: str
    method_name: str
    resource_pattern: str  # e.g. "projects/{project}/..."
    target_zone: str  # IDENTITY, CONTROL, DATA, COMPUTE, SECRET
    offset_sec: float  # Time offset from workflow start
    log_name_suffix: str  # activity, data_access, system_event


class WorkflowTemplates:
    """Library of workflow patterns (benign and attack)."""

    # ========== BENIGN WORKFLOWS ==========

    @staticmethod
    def deploy_workflow() -> list[WorkflowStep]:
        """Typical deployment sequence: build → deploy → verify."""
        return [
            WorkflowStep(
                service_name="storage.googleapis.com",
                method_name="storage.objects.get",
                resource_pattern="projects/_/buckets/source-code-bucket/objects/app.tar.gz",
                target_zone="DATA",
                offset_sec=0,
                log_name_suffix="data_access",
            ),
            WorkflowStep(
                service_name="storage.googleapis.com",
                method_name="storage.objects.create",
                resource_pattern="projects/_/buckets/build-artifacts-bucket/objects/app-v1.0.jar",
                target_zone="DATA",
                offset_sec=30,
                log_name_suffix="data_access",
            ),
            WorkflowStep(
                service_name="compute.googleapis.com",
                method_name="instances.insert",
                resource_pattern="projects/synth-project/zones/us-central1-a/instances/app-server",
                target_zone="COMPUTE",
                offset_sec=60,
                log_name_suffix="activity",
            ),
            WorkflowStep(
                service_name="storage.googleapis.com",
                method_name="storage.objects.get",
                resource_pattern="projects/_/buckets/config-bucket/objects/health-check.json",
                target_zone="DATA",
                offset_sec=90,
                log_name_suffix="data_access",
            ),
        ]

    @staticmethod
    def secret_rotation_workflow() -> list[WorkflowStep]:
        """Secret rotation: read old → create new → delete old."""
        return [
            WorkflowStep(
                service_name="secretmanager.googleapis.com",
                method_name="google.cloud.secretmanager.v1.SecretManagerService.AccessSecretVersion",
                resource_pattern="projects/synth-project/secrets/db-password/versions/latest",
                target_zone="SECRET",
                offset_sec=0,
                log_name_suffix="data_access",
            ),
            WorkflowStep(
                service_name="secretmanager.googleapis.com",
                method_name="AddSecretVersion",
                resource_pattern="projects/synth-project/secrets/db-password/versions/new",
                target_zone="SECRET",
                offset_sec=20,
                log_name_suffix="activity",
            ),
            WorkflowStep(
                service_name="secretmanager.googleapis.com",
                method_name="google.cloud.secretmanager.v1.SecretManagerService.AccessSecretVersion",
                resource_pattern="projects/synth-project/secrets/db-password/versions/latest",
                target_zone="SECRET",
                offset_sec=40,
                log_name_suffix="data_access",
            ),
        ]

    @staticmethod
    def data_pipeline_workflow() -> list[WorkflowStep]:
        """ETL pipeline: read → transform → write."""
        return [
            WorkflowStep(
                service_name="storage.googleapis.com",
                method_name="storage.objects.list",
                resource_pattern="projects/_/buckets/raw-data-bucket",
                target_zone="DATA",
                offset_sec=0,
                log_name_suffix="data_access",
            ),
            WorkflowStep(
                service_name="storage.googleapis.com",
                method_name="storage.objects.get",
                resource_pattern="projects/_/buckets/raw-data-bucket/objects/input.csv",
                target_zone="DATA",
                offset_sec=10,
                log_name_suffix="data_access",
            ),
            WorkflowStep(
                service_name="bigquery.googleapis.com",
                method_name="jobservice.insert",
                resource_pattern="projects/synth-project/jobs/query-job-001",
                target_zone="DATA",
                offset_sec=30,
                log_name_suffix="activity",
            ),
            WorkflowStep(
                service_name="storage.googleapis.com",
                method_name="storage.objects.create",
                resource_pattern="projects/_/buckets/processed-data-bucket/objects/output.csv",
                target_zone="DATA",
                offset_sec=60,
                log_name_suffix="data_access",
            ),
        ]

    @staticmethod
    def maintenance_workflow() -> list[WorkflowStep]:
        """Scheduled maintenance: check status → update config → verify."""
        return [
            WorkflowStep(
                service_name="compute.googleapis.com",
                method_name="setMetadata",
                resource_pattern="projects/synth-project/zones/us-central1-a/instances/server-1",
                target_zone="COMPUTE",
                offset_sec=0,
                log_name_suffix="activity",
            ),
            WorkflowStep(
                service_name="storage.googleapis.com",
                method_name="storage.objects.create",
                resource_pattern="projects/_/buckets/logs-bucket/objects/maintenance-2026-01-15.log",
                target_zone="DATA",
                offset_sec=30,
                log_name_suffix="data_access",
            ),
        ]

    # ========== ATTACK WORKFLOWS ==========

    @staticmethod
    def key_exfil_workflow() -> list[WorkflowStep]:
        """S01: Key exfil — create key + access secret."""
        return [
            WorkflowStep(
                service_name="iam.googleapis.com",
                method_name="CreateServiceAccountKey",
                resource_pattern="projects/synth-project/serviceAccounts/target-sa@synth-project.iam.gserviceaccount.com/keys/key-new",
                target_zone="IDENTITY",
                offset_sec=0,
                log_name_suffix="activity",
            ),
            WorkflowStep(
                service_name="secretmanager.googleapis.com",
                method_name="google.cloud.secretmanager.v1.SecretManagerService.AccessSecretVersion",
                resource_pattern="projects/synth-project/secrets/api-key/versions/latest",
                target_zone="SECRET",
                offset_sec=15,
                log_name_suffix="data_access",
            ),
        ]

    @staticmethod
    def slow_ratchet_workflow() -> list[WorkflowStep]:
        """S04: Slow ratchet — escalating privilege access."""
        return [
            WorkflowStep(
                service_name="iam.googleapis.com",
                method_name="SetIAMPolicy",
                resource_pattern="projects/synth-project/iamPolicies/default",
                target_zone="CONTROL",
                offset_sec=0,
                log_name_suffix="activity",
            ),
            WorkflowStep(
                service_name="iam.googleapis.com",
                method_name="CreateServiceAccount",
                resource_pattern="projects/synth-project/serviceAccounts/escalation-sa",
                target_zone="IDENTITY",
                offset_sec=30,
                log_name_suffix="activity",
            ),
            WorkflowStep(
                service_name="iam.googleapis.com",
                method_name="CreateServiceAccountKey",
                resource_pattern="projects/synth-project/serviceAccounts/escalation-sa@synth-project.iam.gserviceaccount.com/keys/key-1",
                target_zone="IDENTITY",
                offset_sec=60,
                log_name_suffix="activity",
            ),
        ]

    @staticmethod
    def lateral_movement_workflow() -> list[WorkflowStep]:
        """S07: Cross-actor lateral movement — SA impersonation chain."""
        return [
            WorkflowStep(
                service_name="iam.googleapis.com",
                method_name="serviceAccounts.actAs",
                resource_pattern="projects/synth-project/serviceAccounts/intermediate-sa@synth-project.iam.gserviceaccount.com",
                target_zone="IDENTITY",
                offset_sec=0,
                log_name_suffix="activity",
            ),
            WorkflowStep(
                service_name="iamcredentials.googleapis.com",
                method_name="GenerateAccessToken",
                resource_pattern="projects/synth-project/serviceAccounts/target-sa@synth-project.iam.gserviceaccount.com/generateAccessToken",
                target_zone="IDENTITY",
                offset_sec=15,
                log_name_suffix="activity",
            ),
            WorkflowStep(
                service_name="secretmanager.googleapis.com",
                method_name="google.cloud.secretmanager.v1.SecretManagerService.AccessSecretVersion",
                resource_pattern="projects/synth-project/secrets/sensitive-data/versions/latest",
                target_zone="SECRET",
                offset_sec=40,
                log_name_suffix="data_access",
            ),
        ]

    @staticmethod
    def pattern_mimicry_workflow() -> list[WorkflowStep]:
        """S13: Pattern mimicry with no provenance — looks benign but is attack."""
        return [
            WorkflowStep(
                service_name="storage.googleapis.com",
                method_name="storage.objects.get",
                resource_pattern="projects/_/buckets/public-data-bucket/objects/sensitive.csv",
                target_zone="EXFIL_RISK",
                offset_sec=0,
                log_name_suffix="data_access",
            ),
            WorkflowStep(
                service_name="storage.googleapis.com",
                method_name="storage.objects.get",
                resource_pattern="projects/_/buckets/external-sharing-bucket/objects/exports.json",
                target_zone="EXFIL_RISK",
                offset_sec=20,
                log_name_suffix="data_access",
            ),
            WorkflowStep(
                service_name="bigquery.googleapis.com",
                method_name="jobservice.insert",
                resource_pattern="projects/synth-project/jobs/export-job",
                target_zone="DATA",
                offset_sec=45,
                log_name_suffix="activity",
            ),
        ]

    @staticmethod
    def get_benign_workflows() -> list[list[WorkflowStep]]:
        """Get all benign workflow templates."""
        return [
            WorkflowTemplates.deploy_workflow(),
            WorkflowTemplates.secret_rotation_workflow(),
            WorkflowTemplates.data_pipeline_workflow(),
            WorkflowTemplates.maintenance_workflow(),
        ]

    @staticmethod
    def get_attack_workflows() -> list[list[WorkflowStep]]:
        """Get all attack workflow templates."""
        return [
            WorkflowTemplates.key_exfil_workflow(),
            WorkflowTemplates.slow_ratchet_workflow(),
            WorkflowTemplates.lateral_movement_workflow(),
            WorkflowTemplates.pattern_mimicry_workflow(),
        ]
