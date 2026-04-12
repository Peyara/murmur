from dataclasses import dataclass


@dataclass
class WorkflowStep:
    service_name: str
    method_name: str
    resource_pattern: str
    target_zone: str
    offset_sec: float
    log_name_suffix: str

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
                "google.cloud.secretmanager.v1.SecretManagerService."
                "AccessSecretVersion",
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
                "google.cloud.secretmanager.v1.SecretManagerService."
                "AccessSecretVersion",
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
                "projects/_/buckets/logs-bucket/objects/"
                "maintenance-2026-01-15.log",
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
                "projects/synth-project/serviceAccounts/"
                "target-sa@synth-project.iam.gserviceaccount.com/keys/key-new",
                "IDENTITY",
                0,
                "activity",
            ),
            WorkflowStep(
                "secretmanager.googleapis.com",
                "google.cloud.secretmanager.v1.SecretManagerService."
                "AccessSecretVersion",
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
                "projects/synth-project/serviceAccounts/"
                "escalation-sa@synth-project.iam.gserviceaccount.com/keys/key-1",
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
                "projects/synth-project/serviceAccounts/"
                "intermediate-sa@synth-project.iam.gserviceaccount.com",
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
                "google.cloud.secretmanager.v1.SecretManagerService."
                "AccessSecretVersion",
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
                "projects/_/buckets/external-sharing-bucket/objects/"
                "exports.json",
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
    def get_benign_workflows():
        return [
            WorkflowTemplates.deploy_workflow(),
            WorkflowTemplates.secret_rotation_workflow(),
            WorkflowTemplates.data_pipeline_workflow(),
            WorkflowTemplates.maintenance_workflow(),
        ]

    @staticmethod
    def get_attack_workflows():
        return [
            WorkflowTemplates.key_exfil_workflow(),
            WorkflowTemplates.slow_ratchet_workflow(),
            WorkflowTemplates.lateral_movement_workflow(),
            WorkflowTemplates.pattern_mimicry_workflow(),
        ]
