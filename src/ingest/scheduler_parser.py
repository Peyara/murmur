"""Cloud Scheduler execution log parser.

Parses scheduler execution logs (jsonPayload with AttemptStarted/AttemptFinished)
into lightweight SchedulerExecution structs for temporal-identity correlation.
These are NOT CanonicalEvents — they're correlation metadata.
"""

from dataclasses import dataclass
from datetime import datetime

from src.ingest.parser import parse_timestamp


@dataclass
class SchedulerExecution:
    """Lightweight struct for a scheduler execution log entry."""

    job_name: str  # full resource path
    job_id: str  # short name (last segment of job_name)
    target_url: str | None
    attempt_type: str  # "AttemptStarted" or "AttemptFinished"
    timestamp: datetime
    insert_id: str
    project_id: str
    scheduled_time: datetime | None = None  # only on AttemptStarted
    http_status: int | None = None  # only on AttemptFinished
    status: str | None = None  # error status string, only on failed AttemptFinished


_SCHEDULER_TYPE_PREFIX = "type.googleapis.com/google.cloud.scheduler.logging."


def can_parse_scheduler(raw: dict) -> bool:
    """Check if this log entry is a Cloud Scheduler execution log."""
    payload = raw.get("jsonPayload", {})
    at_type = payload.get("@type", "")
    return at_type.startswith(_SCHEDULER_TYPE_PREFIX)


def parse_scheduler_log(raw: dict) -> SchedulerExecution:
    """Parse a Cloud Scheduler execution log entry.

    Raises KeyError if timestamp is missing.
    """
    payload = raw["jsonPayload"]
    at_type = payload["@type"]
    attempt_type = at_type.removeprefix(_SCHEDULER_TYPE_PREFIX)

    job_name = payload.get("jobName", "")
    job_id = raw.get("resource", {}).get("labels", {}).get("job_id", job_name.rsplit("/", 1)[-1])

    # Timestamp (required)
    ts = parse_timestamp(raw["timestamp"])

    # Scheduled time (only on AttemptStarted)
    scheduled_time = None
    if "scheduledTime" in payload:
        scheduled_time = parse_timestamp(payload["scheduledTime"])

    # HTTP status (only on AttemptFinished with httpRequest)
    http_status = None
    http_req = raw.get("httpRequest")
    if http_req:
        http_status = http_req.get("status")

    project_id = raw.get("resource", {}).get("labels", {}).get("project_id", "")

    return SchedulerExecution(
        job_name=job_name,
        job_id=job_id,
        target_url=payload.get("url"),
        attempt_type=attempt_type,
        timestamp=ts,
        insert_id=raw.get("insertId", ""),
        project_id=project_id,
        scheduled_time=scheduled_time,
        http_status=http_status,
        status=payload.get("status"),
    )
