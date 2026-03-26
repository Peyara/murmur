"""Tests for Cloud Run request log parser."""

from datetime import datetime

import pytest

from src.ingest.cloudrun_parser import CloudRunRequest, parse_cloudrun_log, can_parse_cloudrun


def _make_cloudrun_request(
    service_name: str = "normal-worker",
    request_url: str = "https://normal-worker-1013530516622.us-central1.run.app/",
    user_agent: str = "Google-Cloud-Scheduler",
    remote_ip: str = "107.178.194.161",
    status_code: int = 200,
    timestamp: str = "2026-03-25T19:00:54.002305Z",
    insert_id: str = "69c430e600003e08235d9233",
    trace: str = "projects/proj/traces/c0a64c0728fe0b7c290d63772ec2a646",
    span_id: str = "31b9db755942f73d",
    latency: str = "0.003066100s",
    project_id: str = "project-1f4f13c5-912e-45ae-b8a",
) -> dict:
    return {
        "httpRequest": {
            "latency": latency,
            "protocol": "HTTP/1.1",
            "remoteIp": remote_ip,
            "requestMethod": "GET",
            "requestSize": "1308",
            "requestUrl": request_url,
            "responseSize": "5061",
            "serverIp": "34.143.72.2",
            "status": status_code,
            "userAgent": user_agent,
        },
        "insertId": insert_id,
        "labels": {"instanceId": "008c15ff..."},
        "logName": f"projects/{project_id}/logs/run.googleapis.com%2Frequests",
        "receiveTimestamp": "2026-03-25T19:00:54.027183967Z",
        "resource": {
            "labels": {
                "configuration_name": service_name,
                "location": "us-central1",
                "project_id": project_id,
                "revision_name": f"{service_name}-00001-46j",
                "service_name": service_name,
            },
            "type": "cloud_run_revision",
        },
        "severity": "INFO",
        "spanId": span_id,
        "timestamp": timestamp,
        "trace": trace,
        "traceSampled": True,
    }


# ── Format detection ──


class TestCanParseCloudRun:
    def test_detects_cloudrun_request(self):
        assert can_parse_cloudrun(_make_cloudrun_request()) is True

    def test_rejects_audit_log(self):
        raw = {"protoPayload": {"serviceName": "iam.googleapis.com"}, "timestamp": "2026-03-25T10:00:00Z"}
        assert can_parse_cloudrun(raw) is False

    def test_rejects_scheduler_log(self):
        raw = {"jsonPayload": {"@type": "type.googleapis.com/google.cloud.scheduler.logging.AttemptStarted"}}
        assert can_parse_cloudrun(raw) is False

    def test_rejects_empty_dict(self):
        assert can_parse_cloudrun({}) is False


# ── Field extraction ──


class TestParseCloudRunFields:
    def test_extracts_service_name(self):
        result = parse_cloudrun_log(_make_cloudrun_request())
        assert result.service_name == "normal-worker"

    def test_extracts_request_url(self):
        result = parse_cloudrun_log(_make_cloudrun_request())
        assert result.request_url == "https://normal-worker-1013530516622.us-central1.run.app/"

    def test_extracts_user_agent(self):
        result = parse_cloudrun_log(_make_cloudrun_request())
        assert result.user_agent == "Google-Cloud-Scheduler"

    def test_extracts_remote_ip(self):
        result = parse_cloudrun_log(_make_cloudrun_request())
        assert result.remote_ip == "107.178.194.161"

    def test_extracts_status_code(self):
        result = parse_cloudrun_log(_make_cloudrun_request())
        assert result.status_code == 200

    def test_extracts_trace_id(self):
        result = parse_cloudrun_log(_make_cloudrun_request())
        assert result.trace_id == "projects/proj/traces/c0a64c0728fe0b7c290d63772ec2a646"

    def test_extracts_span_id(self):
        result = parse_cloudrun_log(_make_cloudrun_request())
        assert result.span_id == "31b9db755942f73d"

    def test_extracts_timestamp(self):
        result = parse_cloudrun_log(_make_cloudrun_request())
        assert result.timestamp == datetime(2026, 3, 25, 19, 0, 54, 2305)

    def test_extracts_insert_id(self):
        result = parse_cloudrun_log(_make_cloudrun_request())
        assert result.insert_id == "69c430e600003e08235d9233"

    def test_extracts_latency_seconds(self):
        result = parse_cloudrun_log(_make_cloudrun_request())
        assert abs(result.latency_seconds - 0.003066100) < 1e-9

    def test_extracts_project_id(self):
        result = parse_cloudrun_log(_make_cloudrun_request())
        assert result.project_id == "project-1f4f13c5-912e-45ae-b8a"

    def test_is_scheduler_invoked_true(self):
        result = parse_cloudrun_log(_make_cloudrun_request(user_agent="Google-Cloud-Scheduler"))
        assert result.is_scheduler_invoked is True

    def test_is_scheduler_invoked_false(self):
        result = parse_cloudrun_log(_make_cloudrun_request(user_agent="curl/7.68.0"))
        assert result.is_scheduler_invoked is False

    def test_error_status(self):
        result = parse_cloudrun_log(_make_cloudrun_request(status_code=500))
        assert result.status_code == 500


# ── Edge cases ──


class TestCloudRunEdgeCases:
    def test_missing_trace(self):
        raw = _make_cloudrun_request()
        del raw["trace"]
        del raw["spanId"]
        result = parse_cloudrun_log(raw)
        assert result.trace_id is None
        assert result.span_id is None

    def test_missing_latency(self):
        raw = _make_cloudrun_request()
        del raw["httpRequest"]["latency"]
        result = parse_cloudrun_log(raw)
        assert result.latency_seconds is None

    def test_missing_timestamp_raises(self):
        raw = _make_cloudrun_request()
        del raw["timestamp"]
        with pytest.raises(KeyError):
            parse_cloudrun_log(raw)

    def test_missing_user_agent(self):
        raw = _make_cloudrun_request()
        del raw["httpRequest"]["userAgent"]
        result = parse_cloudrun_log(raw)
        assert result.user_agent is None
        assert result.is_scheduler_invoked is False
