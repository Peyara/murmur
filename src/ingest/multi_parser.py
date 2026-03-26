"""Multi-format log dispatcher.

Routes raw log entries to the appropriate format-specific parser based on
structural detection. Returns typed results — downstream code uses isinstance
to branch on the result type.

Common interface per parser: can_parse(raw) -> bool, parse(raw) -> T.
"""

from src.ingest.cloudrun_parser import CloudRunRequest, can_parse_cloudrun, parse_cloudrun_log
from src.ingest.parser import parse_audit_log
from src.ingest.scheduler_parser import SchedulerExecution, can_parse_scheduler, parse_scheduler_log
from src.schema import CanonicalEvent

# Union of all possible parse results (None = unrecognized format)
ParseResult = CanonicalEvent | SchedulerExecution | CloudRunRequest | None


def can_parse_audit(raw: dict) -> bool:
    """Check if this log entry is a Cloud Audit Log (protoPayload)."""
    return "protoPayload" in raw and "timestamp" in raw


def dispatch_parse(raw: dict) -> ParseResult:
    """Detect log format and route to the appropriate parser.

    Returns None for unrecognized formats.
    Check order: scheduler → cloudrun → audit (most specific first).
    """
    if can_parse_scheduler(raw):
        return parse_scheduler_log(raw)
    if can_parse_cloudrun(raw):
        return parse_cloudrun_log(raw)
    if can_parse_audit(raw):
        return parse_audit_log(raw)
    return None
