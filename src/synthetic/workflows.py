"""GCP workflow template definitions for synthetic trajectory generation.

This module provides realistic workflow templates that combine multiple
audit log actions into coherent, detectible patterns. Each template generates
WorkflowStep objects that map to GCP audit log entries, serialized by the
composer with realistic actor identities and timing.

API Mapping Reference:
- storage.googleapis.com: GCS operations (list, get, create)
- compute.googleapis.com: VM and metadata (instances.insert, setMetadata)
- bigquery.googleapis.com: BigQuery job submission (jobservice.insert)
- secretmanager.googleapis.com: Secret ops (AccessSecretVersion,
  AddSecretVersion, CreateSecret)
- cloudkms.googleapis.com: KMS operations (Encrypt, Decrypt)
- cloudscheduler.googleapis.com: Cloud Scheduler (CreateJob, UpdateJob,
  DeleteJob)
- iam.googleapis.com: IAM operations (SetIAMPolicy, CreateServiceAccount,
  CreateServiceAccountKey, DeleteServiceAccountKey, serviceAccounts.actAs)
- iamcredentials.googleapis.com: IAM credentials (GenerateAccessToken,
  GenerateIdToken)
"""

from dataclasses import dataclass


@dataclass
class WorkflowStep:
    service_name: str
    method_name: str
    resource_pattern: str
    target_zone: str
    offset_sec: float
    log_name_suffix: str


# Expanded noise action specs: (service_name, method_name, resource_pattern, target_zone, log_name_suffix)
# Used by the composer to inject realistic background activity.
NOISE_ACTIONS = [
    (
        "storage.googleapis.com",
        "storage.objects.get",
        "projects/_/buckets/data-bucket/objects/file.csv",
        "DATA",
        "data_access",
    ),
    ("storage.googleapis.com", "storage.objects.list", "projects/_/buckets/data-bucket", "DATA", "data_access"),
    (
        "storage.googleapis.com",
        "storage.objects.create",
        "projects/_/buckets/logs-bucket/objects/app.log",
        "DATA",
        "data_access",
    ),
    ("bigquery.googleapis.com", "jobservice.insert", "projects/synth-project/jobs/query-noise", "DATA", "activity"),
    (
        "compute.googleapis.com",
        "setMetadata",
        "projects/synth-project/zones/us-central1-a/instances/server-1",
        "COMPUTE",
        "activity",
    ),
    (
        "secretmanager.googleapis.com",
        "google.cloud.secretmanager.v1.SecretManagerService.AccessSecretVersion",
        "projects/synth-project/secrets/app-config/versions/latest",
        "SECRET",
        "data_access",
    ),
    (
        "cloudkms.googleapis.com",
        "Decrypt",
        "projects/synth-project/locations/us-central1/keyRings/app-keyring/cryptoKeys/data-key",
        "SECRET",
        "data_access",
    ),
    ("iam.googleapis.com", "SetIAMPolicy", "projects/synth-project/iamPolicies/default", "CONTROL", "activity"),
]


class WorkflowTemplates:
    @staticmethod
    def deploy_workflow():
        return [
            WorkflowStep(
                "storage.googleapis.com",
                "storage.objects.get",
                "projects/_/buckets/source-code-bucket/objects/app.tar.gz",
                "DATA",
                0,
                "data_access",
            ),
            WorkflowStep(
                "storage.googleapis.com",
                "storage.objects.create",
                "projects/_/buckets/build-artifacts-bucket/objects/app-v1.0.jar",
                "DATA",
                30,
                "data_access",
            ),
            WorkflowStep(
                "compute.googleapis.com",
                "instances.insert",
                "projects/synth-project/zones/us-central1-a/instances/app-server",
                "COMPUTE",
                60,
                "activity",
            ),
            WorkflowStep(
                "storage.googleapis.com",
                "storage.objects.get",
                "projects/_/buckets/config-bucket/objects/health-check.json",
                "DATA",
                90,
                "data_access",
            ),
        ]

    @staticmethod
    def secret_rotation_workflow():
        return [
            WorkflowStep(
                "secretmanager.googleapis.com",
                "google.cloud.secretmanager.v1.SecretManagerService.AccessSecretVersion",
                "projects/synth-project/secrets/db-password/versions/latest",
                "SECRET",
                0,
                "data_access",
            ),
            WorkflowStep(
                "secretmanager.googleapis.com",
                "AddSecretVersion",
                "projects/synth-project/secrets/db-password/versions/new",
                "SECRET",
                20,
                "activity",
            ),
            WorkflowStep(
                "secretmanager.googleapis.com",
                "google.cloud.secretmanager.v1.SecretManagerService.AccessSecretVersion",
                "projects/synth-project/secrets/db-password/versions/latest",
                "SECRET",
                40,
                "data_access",
            ),
        ]

    @staticmethod
    def data_pipeline_workflow():
        return [
            WorkflowStep(
                "storage.googleapis.com",
                "storage.objects.list",
                "projects/_/buckets/raw-data-bucket",
                "DATA",
                0,
                "data_access",
            ),
            WorkflowStep(
                "storage.googleapis.com",
                "storage.objects.get",
                "projects/_/buckets/raw-data-bucket/objects/input.csv",
                "DATA",
                10,
                "data_access",
            ),
            WorkflowStep(
                "bigquery.googleapis.com",
                "jobservice.insert",
                "projects/synth-project/jobs/query-job-001",
                "DATA",
                30,
                "activity",
            ),
            WorkflowStep(
                "storage.googleapis.com",
                "storage.objects.create",
                "projects/_/buckets/processed-data-bucket/objects/output.csv",
                "DATA",
                60,
                "data_access",
            ),
        ]

    @staticmethod
    def maintenance_workflow():
        return [
            WorkflowStep(
                "compute.googleapis.com",
                "setMetadata",
                "projects/synth-project/zones/us-central1-a/instances/server-1",
                "COMPUTE",
                0,
                "activity",
            ),
            WorkflowStep(
                "storage.googleapis.com",
                "storage.objects.create",
                "projects/_/buckets/logs-bucket/objects/maintenance-2026-01-15.log",
                "DATA",
                30,
                "data_access",
            ),
        ]

    @staticmethod
    def key_exfil_workflow():
        return [
            WorkflowStep(
                "iam.googleapis.com",
                "CreateServiceAccountKey",
                "projects/synth-project/serviceAccounts/target-sa@synth-project.iam.gserviceaccount.com/keys/key-new",
                "IDENTITY",
                0,
                "activity",
            ),
            WorkflowStep(
                "secretmanager.googleapis.com",
                "google.cloud.secretmanager.v1.SecretManagerService.AccessSecretVersion",
                "projects/synth-project/secrets/api-key/versions/latest",
                "SECRET",
                15,
                "data_access",
            ),
        ]

    @staticmethod
    def slow_ratchet_workflow():
        return [
            WorkflowStep(
                "iam.googleapis.com",
                "SetIAMPolicy",
                "projects/synth-project/iamPolicies/default",
                "CONTROL",
                0,
                "activity",
            ),
            WorkflowStep(
                "iam.googleapis.com",
                "CreateServiceAccount",
                "projects/synth-project/serviceAccounts/escalation-sa",
                "IDENTITY",
                30,
                "activity",
            ),
            WorkflowStep(
                "iam.googleapis.com",
                "CreateServiceAccountKey",
                "projects/synth-project/serviceAccounts/escalation-sa@synth-project.iam.gserviceaccount.com/keys/key-1",
                "IDENTITY",
                60,
                "activity",
            ),
        ]

    @staticmethod
    def lateral_movement_workflow():
        return [
            WorkflowStep(
                "iam.googleapis.com",
                "serviceAccounts.actAs",
                "projects/synth-project/serviceAccounts/intermediate-sa@synth-project.iam.gserviceaccount.com",
                "IDENTITY",
                0,
                "activity",
            ),
            WorkflowStep(
                "iamcredentials.googleapis.com",
                "GenerateAccessToken",
                "projects/synth-project/serviceAccounts/"
                "target-sa@synth-project.iam.gserviceaccount.com/"
                "generateAccessToken",
                "IDENTITY",
                15,
                "activity",
            ),
            WorkflowStep(
                "secretmanager.googleapis.com",
                "google.cloud.secretmanager.v1.SecretManagerService.AccessSecretVersion",
                "projects/synth-project/secrets/sensitive-data/versions/latest",
                "SECRET",
                40,
                "data_access",
            ),
        ]

    @staticmethod
    def pattern_mimicry_workflow():
        return [
            WorkflowStep(
                "storage.googleapis.com",
                "storage.objects.get",
                "projects/_/buckets/public-data-bucket/objects/sensitive.csv",
                "EXFIL_RISK",
                0,
                "data_access",
            ),
            WorkflowStep(
                "storage.googleapis.com",
                "storage.objects.get",
                "projects/_/buckets/external-sharing-bucket/objects/exports.json",
                "EXFIL_RISK",
                20,
                "data_access",
            ),
            WorkflowStep(
                "bigquery.googleapis.com",
                "jobservice.insert",
                "projects/synth-project/jobs/export-job",
                "DATA",
                45,
                "activity",
            ),
        ]

    @staticmethod
    def kms_operations_workflow():
        """Benign KMS encryption/decryption workflow.

        Represents typical application encryption and decryption of data,
        such as encrypting sensitive configuration or decrypting stored secrets.
        This is normal operational activity for applications that require
        encrypted data protection.
        """
        return [
            WorkflowStep(
                "cloudkms.googleapis.com",
                "Encrypt",
                "projects/synth-project/locations/us-central1/keyRings/app-keyring/cryptoKeys/data-key",
                "SECRET",
                0,
                "data_access",
            ),
            WorkflowStep(
                "cloudkms.googleapis.com",
                "Decrypt",
                "projects/synth-project/locations/us-central1/keyRings/app-keyring/cryptoKeys/data-key",
                "SECRET",
                10,
                "data_access",
            ),
        ]

    @staticmethod
    def scheduler_setup_workflow():
        """Benign Cloud Scheduler job creation workflow.

        Represents a typical scheduled job setup, combined with data operations
        that the job would use. Cloud Scheduler is commonly used for automated
        maintenance and data processing tasks.
        """
        return [
            WorkflowStep(
                "cloudscheduler.googleapis.com",
                "CreateJob",
                "projects/synth-project/locations/us-central1/jobs/daily-backup",
                "CONTROL",
                0,
                "activity",
            ),
            WorkflowStep(
                "storage.googleapis.com",
                "storage.objects.get",
                "projects/_/buckets/backup-config-bucket/objects/schedule-config.json",
                "DATA",
                20,
                "data_access",
            ),
        ]

    @staticmethod
    def key_cleanup_workflow():
        """Attack pattern: create key, use it, then delete it to cover tracks.

        This workflow represents a classic privilege escalation + exfiltration
        attack where the attacker:
        1. Creates a new service account key
        2. Uses the key to access secrets (proof of compromise)
        3. Deletes the key to remove evidence of their activity

        The key deletion (IAM_DELETE_KEY) is the critical action that currently
        lacks workflow coverage.
        """
        return [
            WorkflowStep(
                "iam.googleapis.com",
                "CreateServiceAccountKey",
                "projects/synth-project/serviceAccounts/target-sa@synth-project.iam.gserviceaccount.com/keys/key-temp",
                "IDENTITY",
                0,
                "activity",
            ),
            WorkflowStep(
                "secretmanager.googleapis.com",
                "google.cloud.secretmanager.v1.SecretManagerService.AccessSecretVersion",
                "projects/synth-project/secrets/sensitive-creds/versions/latest",
                "SECRET",
                15,
                "data_access",
            ),
            WorkflowStep(
                "iam.googleapis.com",
                "DeleteServiceAccountKey",
                "projects/synth-project/serviceAccounts/target-sa@synth-project.iam.gserviceaccount.com/keys/key-temp",
                "IDENTITY",
                30,
                "activity",
            ),
        ]

    @staticmethod
    def get_benign_workflows():
        return [
            WorkflowTemplates.deploy_workflow(),
            WorkflowTemplates.secret_rotation_workflow(),
            WorkflowTemplates.data_pipeline_workflow(),
            WorkflowTemplates.maintenance_workflow(),
            WorkflowTemplates.kms_operations_workflow(),
            WorkflowTemplates.scheduler_setup_workflow(),
        ]

    @staticmethod
    def get_attack_workflows():
        return [
            WorkflowTemplates.key_exfil_workflow(),
            WorkflowTemplates.slow_ratchet_workflow(),
            WorkflowTemplates.lateral_movement_workflow(),
            WorkflowTemplates.pattern_mimicry_workflow(),
            WorkflowTemplates.key_cleanup_workflow(),
        ]
