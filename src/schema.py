"""CanonicalEvent dataclass and enums for Murmur's event model.

Every GCP audit log entry is parsed into a CanonicalEvent. The schema is
provider-agnostic — Azure and AWS parsers can be added later without changing
downstream layers.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ActionType(StrEnum):
    IAM_SET_POLICY = "IAM_SET_POLICY"
    IAM_CREATE_SA = "IAM_CREATE_SA"
    IAM_CREATE_KEY = "IAM_CREATE_KEY"
    IAM_DELETE_KEY = "IAM_DELETE_KEY"
    IAM_IMPERSONATE = "IAM_IMPERSONATE"
    SECRET_ACCESS = "SECRET_ACCESS"  # nosec B105 — enum value, not a password
    SECRET_ADMIN = "SECRET_ADMIN"  # nosec B105 — CreateSecret, AddSecretVersion
    KMS_DECRYPT = "KMS_DECRYPT"
    KMS_ENCRYPT = "KMS_ENCRYPT"
    GCS_READ = "GCS_READ"
    GCS_WRITE = "GCS_WRITE"
    GCS_LIST = "GCS_LIST"
    BQ_JOB_SUBMIT = "BQ_JOB_SUBMIT"
    COMPUTE_CREATE = "COMPUTE_CREATE"
    COMPUTE_METADATA_CHANGE = "COMPUTE_METADATA_CHANGE"
    SCHEDULER_ADMIN = "SCHEDULER_ADMIN"
    AGENT_TOOL_CALL = "AGENT_TOOL_CALL"
    OTHER = "OTHER"


class TargetZone(StrEnum):
    CONTROL = "CONTROL"
    IDENTITY = "IDENTITY"
    SECRET = "SECRET"  # nosec B105
    DATA = "DATA"
    COMPUTE = "COMPUTE"
    EXFIL_RISK = "EXFIL_RISK"


class TargetType(StrEnum):
    PROJECT = "PROJECT"
    IAM_POLICY = "IAM_POLICY"
    SERVICE_ACCOUNT = "SERVICE_ACCOUNT"
    SA_KEY = "SA_KEY"
    SECRET = "SECRET"  # nosec B105
    KMS_KEY = "KMS_KEY"
    GCS_BUCKET = "GCS_BUCKET"
    BIGQUERY = "BIGQUERY"
    COMPUTE = "COMPUTE"
    EXFIL_RISK_DEST = "EXFIL_RISK_DEST"
    OTHER = "OTHER"


class ActorType(StrEnum):
    HUMAN = "HUMAN"
    SERVICE_ACCOUNT = "SERVICE_ACCOUNT"
    UNKNOWN = "UNKNOWN"


class ActorSubtype(StrEnum):
    AGENT = "AGENT"
    HUMAN = "HUMAN"
    SERVICE = "SERVICE"
    PIPELINE = "PIPELINE"


class ProvenanceLevel(StrEnum):
    NONE = "NONE"
    WEAK = "WEAK"
    STRONG = "STRONG"


class ProvenanceSource(StrEnum):
    CLOUD_SCHEDULER = "CLOUD_SCHEDULER"
    CLOUD_BUILD = "CLOUD_BUILD"
    ORCHESTRATOR_SIGNATURE = "ORCHESTRATOR_SIGNATURE"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"
    UNKNOWN = "UNKNOWN"


class EventResult(StrEnum):
    SUCCESS = "SUCCESS"
    FAIL = "FAIL"


@dataclass
class CanonicalEvent:
    # --- Identity ---
    event_id: str
    ts: datetime
    window_start: datetime
    actor_id: str
    actor_type: ActorType

    # --- Action ---
    action_type: ActionType
    target_id: str
    target_type: TargetType
    target_zone: TargetZone

    # --- Result ---
    result: EventResult = EventResult.SUCCESS

    # --- Actor metadata (optional) ---
    actor_subtype: ActorSubtype | None = None
    orchestrator_id: str | None = None

    # --- Provenance ---
    trigger_ref: str | None = None
    provenance_level: ProvenanceLevel = ProvenanceLevel.NONE
    provenance_source: ProvenanceSource = ProvenanceSource.UNKNOWN

    # --- Action detail ---
    action_subtype: str | None = None  # normalized methodName
    tool_name: str | None = None
    tool_parameters_hash: str | None = None
    model_id: str | None = None

    # --- Correlation ---
    correlation_confidence: float = 0.0  # 0.0-1.0 composite confidence for derived trigger_ref

    # --- Delegation ---
    delegation_chain: str = "[]"  # JSON array of delegation SA emails from serviceAccountDelegationInfo

    # --- Context ---
    project_id: str | None = None
    env: str = "sandbox"
    is_deploy: bool = False
    is_incident: bool = False
    is_infrastructure: bool = False  # True for infra meta-logs (e.g. logging SA)
    risk_tags: str = "[]"  # JSON array of string tags
    raw_ref: str | None = None
    coverage_flag: bool = True
