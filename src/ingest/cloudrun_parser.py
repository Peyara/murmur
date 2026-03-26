"""Cloud Run request log parser.

Parses Cloud Run request logs (httpRequest with run.googleapis.com logName)
into lightweight CloudRunRequest structs for temporal-identity correlation.
These are NOT CanonicalEvents — they're correlation metadata.
"""

from dataclasses import dataclass
from datetime import datetime

from src.ingest.parser import parse_timestamp


@dataclass
class CloudRunRequest:
    """Lightweight struct for a Cloud Run request log entry."""

    service_name: str
    request_url: str
    status_code: int
    timestamp: datetime
    insert_id: str
    project_id: str
    user_agent: str | None = None
    remote_ip: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    latency_seconds: float | None = None
    is_scheduler_invoked: bool = False


_CLOUDRUN_LOG_MARKER = "run.googleapis.com%2Frequests"


def can_parse_cloudrun(raw: dict) -> bool:
    """Check if this log entry is a Cloud Run request log."""
    log_name = raw.get("logName", "")
    return _CLOUDRUN_LOG_MARKER in log_name


def parse_cloudrun_log(raw: dict) -> CloudRunRequest:
    """Parse a Cloud Run request log entry.

    Raises KeyError if timestamp is missing.
    """
    http_req = raw.get("httpRequest", {})
    resource_labels = raw.get("resource", {}).get("labels", {})

    # Timestamp (required)
    ts = parse_timestamp(raw["timestamp"])

    # Latency parsing: "0.003066100s" -> float seconds
    latency_seconds = None
    latency_str = http_req.get("latency")
    if latency_str:
        latency_seconds = float(latency_str.rstrip("s"))

    user_agent = http_req.get("userAgent")

    return CloudRunRequest(
        service_name=resource_labels.get("service_name", ""),
        request_url=http_req.get("requestUrl", ""),
        status_code=http_req.get("status", 0),
        timestamp=ts,
        insert_id=raw.get("insertId", ""),
        project_id=resource_labels.get("project_id", ""),
        user_agent=user_agent,
        remote_ip=http_req.get("remoteIp"),
        trace_id=raw.get("trace"),
        span_id=raw.get("spanId"),
        latency_seconds=latency_seconds,
        is_scheduler_invoked=user_agent == "Google-Cloud-Scheduler" if user_agent else False,
    )
