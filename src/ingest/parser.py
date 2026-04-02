"""GCP Cloud Audit Log parser -> CanonicalEvent.

Maps raw GCP audit log JSON entries to the canonical event schema.
13 ACTION_MAP entries (using substring matching) cover 14 GCP method
patterns across 13 action types and 6 trust zones.
"""

import json
import logging
from datetime import datetime

from config.settings import SETTINGS
from src.ingest.dedup import compute_event_id
from src.schema import (
    ActionType,
    ActorType,
    CanonicalEvent,
    EventResult,
    ProvenanceLevel,
    ProvenanceSource,
    TargetType,
    TargetZone,
)

logger = logging.getLogger(__name__)

# (serviceName, methodName substring) -> (ActionType, TargetZone)
# Order matters: more specific patterns checked first via substring match.
ACTION_MAP: list[tuple[str, str, ActionType, TargetZone]] = [
    # IAM — more specific patterns first
    ("iam.googleapis.com", "CreateServiceAccountKey", ActionType.IAM_CREATE_KEY, TargetZone.IDENTITY),
    ("iam.googleapis.com", "DeleteServiceAccountKey", ActionType.IAM_DELETE_KEY, TargetZone.IDENTITY),
    ("iam.googleapis.com", "CreateServiceAccount", ActionType.IAM_CREATE_SA, TargetZone.IDENTITY),
    ("iam.googleapis.com", "serviceAccounts.actAs", ActionType.IAM_IMPERSONATE, TargetZone.IDENTITY),
    ("iam.googleapis.com", "SetIamPolicy", ActionType.IAM_SET_POLICY, TargetZone.CONTROL),
    ("iamcredentials.googleapis.com", "GenerateAccessToken", ActionType.IAM_IMPERSONATE, TargetZone.IDENTITY),
    ("iamcredentials.googleapis.com", "GenerateIdToken", ActionType.IAM_IMPERSONATE, TargetZone.IDENTITY),
    # Secret Manager — admin before access (more specific first)
    ("secretmanager.googleapis.com", "AddSecretVersion", ActionType.SECRET_ADMIN, TargetZone.SECRET),
    ("secretmanager.googleapis.com", "CreateSecret", ActionType.SECRET_ADMIN, TargetZone.SECRET),
    ("secretmanager.googleapis.com", "AccessSecretVersion", ActionType.SECRET_ACCESS, TargetZone.SECRET),
    # KMS
    ("cloudkms.googleapis.com", "Decrypt", ActionType.KMS_DECRYPT, TargetZone.SECRET),
    ("cloudkms.googleapis.com", "Encrypt", ActionType.KMS_ENCRYPT, TargetZone.SECRET),
    # Storage — list before get (more specific first)
    ("storage.googleapis.com", "storage.objects.list", ActionType.GCS_LIST, TargetZone.DATA),
    ("storage.googleapis.com", "storage.objects.get", ActionType.GCS_READ, TargetZone.DATA),
    ("storage.googleapis.com", "storage.objects.create", ActionType.GCS_WRITE, TargetZone.DATA),
    # BigQuery
    ("bigquery.googleapis.com", "jobservice.insert", ActionType.BQ_JOB_SUBMIT, TargetZone.DATA),
    # Compute — create before metadata (more specific first)
    ("compute.googleapis.com", "instances.insert", ActionType.COMPUTE_CREATE, TargetZone.COMPUTE),
    ("compute.googleapis.com", "setMetadata", ActionType.COMPUTE_METADATA_CHANGE, TargetZone.COMPUTE),
    ("compute.googleapis.com", "setLabels", ActionType.COMPUTE_METADATA_CHANGE, TargetZone.COMPUTE),
    # Cloud Run — SetIamPolicy before CreateService
    ("run.googleapis.com", "SetIamPolicy", ActionType.IAM_SET_POLICY, TargetZone.CONTROL),
    ("run.googleapis.com", "CreateService", ActionType.COMPUTE_CREATE, TargetZone.COMPUTE),
    # Cloud Scheduler
    ("cloudscheduler.googleapis.com", "CreateJob", ActionType.SCHEDULER_ADMIN, TargetZone.CONTROL),
    # Resource Manager
    ("cloudresourcemanager.googleapis.com", "SetIamPolicy", ActionType.IAM_SET_POLICY, TargetZone.CONTROL),
]

# target_type inference from resource path segments
_TARGET_TYPE_PATTERNS: list[tuple[str, TargetType]] = [
    ("serviceAccounts", TargetType.SERVICE_ACCOUNT),
    ("keys/", TargetType.SA_KEY),
    ("secrets/", TargetType.SECRET),
    ("cryptoKeys/", TargetType.KMS_KEY),
    ("buckets/", TargetType.GCS_BUCKET),
    ("bigquery", TargetType.BIGQUERY),
    ("instances/", TargetType.COMPUTE),
    ("IamPolicy", TargetType.IAM_POLICY),
]


def _resolve_action(service_name: str, method_name: str) -> tuple[ActionType, TargetZone]:
    """Match GCP service+method to ActionType and default TargetZone."""
    for svc, method_sub, action, zone in ACTION_MAP:
        if service_name == svc and method_sub in method_name:
            return action, zone
    logger.debug("Unmapped GCP method: %s/%s -> OTHER/DATA", service_name, method_name)
    return ActionType.OTHER, TargetZone.DATA


# GCP infrastructure service account suffixes — these generate meta-logs
_INFRASTRUCTURE_SA_SUFFIXES = (
    "@gcp-sa-logging.iam.gserviceaccount.com",
)


def _resolve_actor_type(principal_email: str) -> ActorType:
    if principal_email.endswith(".gserviceaccount.com"):
        return ActorType.SERVICE_ACCOUNT
    if principal_email == "unknown":
        return ActorType.UNKNOWN
    return ActorType.HUMAN


def _is_infrastructure_actor(actor_id: str) -> bool:
    """Check if actor is a GCP infrastructure service account."""
    return any(actor_id.endswith(suffix) for suffix in _INFRASTRUCTURE_SA_SUFFIXES)


def _resolve_target_type(resource_name: str) -> TargetType:
    for pattern, target_type in _TARGET_TYPE_PATTERNS:
        if pattern in resource_name:
            return target_type
    return TargetType.OTHER


def _is_exfil_risk(resource_name: str, action_type: ActionType) -> bool:
    """Check if a DATA-zone resource should be reclassified as EXFIL_RISK."""
    if action_type not in (ActionType.GCS_READ, ActionType.GCS_WRITE, ActionType.GCS_LIST, ActionType.BQ_JOB_SUBMIT):
        return False
    for pattern in SETTINGS.exfil_risk_patterns:
        if pattern in resource_name:
            return True
    # Also check bucket name for external/public prefixes
    if "buckets/" in resource_name:
        bucket_part = resource_name.split("buckets/")[1].split("/")[0]
        if bucket_part.startswith("external-") or bucket_part.startswith("public-"):
            return True
    return False


def parse_timestamp(ts_str: str) -> datetime:
    """Parse GCP timestamp (ISO 8601 with Z suffix)."""
    ts_str = ts_str.rstrip("Z")
    # Handle variable fractional seconds
    if "." in ts_str:
        date_part, frac = ts_str.split(".")
        # Pad or truncate to 6 digits (microseconds)
        frac = frac[:6].ljust(6, "0")
        ts_str = f"{date_part}.{frac}"
    return datetime.fromisoformat(ts_str)


def _floor_to_window(ts: datetime, window_minutes: int | None = None) -> datetime:
    """Floor timestamp to window boundary."""
    if window_minutes is None:
        window_minutes = SETTINGS.window_size_minutes
    minute = (ts.minute // window_minutes) * window_minutes
    return ts.replace(minute=minute, second=0, microsecond=0)


def parse_audit_log(raw: dict) -> CanonicalEvent:
    """Parse a single GCP Cloud Audit Log JSON entry into a CanonicalEvent.

    Raises KeyError/ValueError if timestamp is missing.
    Handles missing authenticationInfo and resourceName gracefully.
    """
    payload = raw.get("protoPayload", {})
    service_name = payload.get("serviceName", "")
    method_name = payload.get("methodName", "")
    resource_name = payload.get("resourceName", "unknown")

    # Actor
    auth_info = payload.get("authenticationInfo", {})
    actor_id = auth_info.get("principalEmail", "unknown")
    actor_type = _resolve_actor_type(actor_id)

    # Delegation chain — extract SA emails from serviceAccountDelegationInfo
    delegation_entries = auth_info.get("serviceAccountDelegationInfo", [])
    delegation_emails = []
    for entry in delegation_entries:
        fpp = entry.get("firstPartyPrincipal", {})
        email = fpp.get("principalEmail")
        if email:
            delegation_emails.append(email)

    # Action + zone
    action_type, target_zone = _resolve_action(service_name, method_name)

    # EXFIL_RISK override
    if target_zone == TargetZone.DATA and _is_exfil_risk(resource_name, action_type):
        target_zone = TargetZone.EXFIL_RISK

    # Target
    target_type = _resolve_target_type(resource_name)
    if target_zone == TargetZone.EXFIL_RISK:
        target_type = TargetType.EXFIL_RISK_DEST

    # Timestamp (required)
    ts_str = raw["timestamp"]
    ts = parse_timestamp(ts_str)
    window_start = _floor_to_window(ts)

    # Insert ID
    insert_id = raw.get("insertId", "")
    log_name = raw.get("logName", "")

    # Event ID
    event_id = compute_event_id(ts_str, actor_id, method_name, resource_name, insert_id)

    # Project ID
    resource_labels = raw.get("resource", {}).get("labels", {})
    project_id = resource_labels.get("project_id")

    # Provenance (basic — enrichment in provenance_ingest.py classifies source)
    metadata = raw.get("metadata", {})
    trigger_ref = metadata.get("trigger_ref")
    provenance_level = ProvenanceLevel.NONE
    provenance_source = ProvenanceSource.UNKNOWN
    if trigger_ref:
        provenance_level = ProvenanceLevel.WEAK

    # Result
    status = payload.get("status", {})
    result = EventResult.FAIL if status.get("code", 0) != 0 else EventResult.SUCCESS

    return CanonicalEvent(
        event_id=event_id,
        ts=ts,
        window_start=window_start,
        actor_id=actor_id,
        actor_type=actor_type,
        action_type=action_type,
        action_subtype=method_name or None,
        target_id=resource_name,
        target_type=target_type,
        target_zone=target_zone,
        result=result,
        project_id=project_id,
        trigger_ref=trigger_ref,
        provenance_level=provenance_level,
        provenance_source=provenance_source,
        is_infrastructure=_is_infrastructure_actor(actor_id),
        delegation_chain=json.dumps(delegation_emails),
        raw_ref=f"{log_name}:{insert_id}" if log_name else insert_id,
    )
