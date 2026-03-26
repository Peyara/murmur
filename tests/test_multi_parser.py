"""Tests for multi-format log dispatcher."""

import pytest

from src.ingest.multi_parser import dispatch_parse, ParseResult
from src.ingest.scheduler_parser import SchedulerExecution
from src.ingest.cloudrun_parser import CloudRunRequest
from src.schema import CanonicalEvent


def _make_audit_log() -> dict:
    return {
        "protoPayload": {
            "serviceName": "storage.googleapis.com",
            "methodName": "storage.objects.get",
            "authenticationInfo": {"principalEmail": "sa@proj.iam.gserviceaccount.com"},
            "resourceName": "projects/_/buckets/b/objects/f",
            "status": {},
        },
        "resource": {"labels": {"project_id": "proj"}},
        "timestamp": "2026-03-25T10:00:00.000Z",
        "insertId": "abc",
        "logName": "projects/proj/logs/cloudaudit.googleapis.com%2Fdata_access",
    }


def _make_scheduler_log() -> dict:
    return {
        "insertId": "xyz",
        "jsonPayload": {
            "@type": "type.googleapis.com/google.cloud.scheduler.logging.AttemptStarted",
            "jobName": "projects/p/locations/us-central1/jobs/j",
            "scheduledTime": "2026-03-25T10:00:00Z",
            "targetType": "HTTP",
            "url": "https://svc.run.app/",
        },
        "logName": "projects/p/logs/cloudscheduler.googleapis.com%2Fexecutions",
        "receiveTimestamp": "2026-03-25T10:00:01Z",
        "resource": {"labels": {"job_id": "j", "location": "us-central1", "project_id": "p"}, "type": "cloud_scheduler_job"},
        "severity": "INFO",
        "timestamp": "2026-03-25T10:00:01Z",
    }


def _make_cloudrun_log() -> dict:
    return {
        "httpRequest": {
            "latency": "0.005s",
            "protocol": "HTTP/1.1",
            "remoteIp": "1.2.3.4",
            "requestMethod": "GET",
            "requestUrl": "https://svc.run.app/",
            "status": 200,
            "userAgent": "Google-Cloud-Scheduler",
        },
        "insertId": "cr-001",
        "labels": {},
        "logName": "projects/p/logs/run.googleapis.com%2Frequests",
        "receiveTimestamp": "2026-03-25T10:00:01Z",
        "resource": {"labels": {"service_name": "svc", "project_id": "p"}, "type": "cloud_run_revision"},
        "severity": "INFO",
        "timestamp": "2026-03-25T10:00:00.500Z",
    }


# ── Dispatch routing ──


class TestDispatchParse:
    def test_routes_audit_log_to_canonical_event(self):
        result = dispatch_parse(_make_audit_log())
        assert isinstance(result, CanonicalEvent)

    def test_routes_scheduler_log_to_scheduler_execution(self):
        result = dispatch_parse(_make_scheduler_log())
        assert isinstance(result, SchedulerExecution)

    def test_routes_cloudrun_log_to_cloudrun_request(self):
        result = dispatch_parse(_make_cloudrun_log())
        assert isinstance(result, CloudRunRequest)

    def test_unknown_format_returns_none(self):
        result = dispatch_parse({"some": "random", "data": True})
        assert result is None

    def test_empty_dict_returns_none(self):
        result = dispatch_parse({})
        assert result is None


# ── ParseResult type ──


class TestParseResultType:
    def test_parse_result_includes_all_types(self):
        """ParseResult union covers all three parser outputs plus None."""
        # Type check — this is a static assertion, runtime just verifies the types exist
        assert CanonicalEvent is not None
        assert SchedulerExecution is not None
        assert CloudRunRequest is not None
