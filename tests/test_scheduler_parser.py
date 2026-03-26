"""Tests for Cloud Scheduler execution log parser."""

from datetime import datetime

import pytest

from src.ingest.scheduler_parser import can_parse_scheduler, parse_scheduler_log

# ── Real data samples (from data/raw_inspection/scheduler_executions.json) ──


def _make_attempt_started(
    job_name: str = "projects/proj/locations/us-central1/jobs/trigger-normal-worker",
    scheduled_time: str = "2026-03-25T19:00:53.95875Z",
    url: str = "https://normal-worker-1013530516622.us-central1.run.app/",
    timestamp: str = "2026-03-25T19:01:02.017128147Z",
    insert_id: str = "1qhiz4xf2nt1ny",
    project_id: str = "project-1f4f13c5-912e-45ae-b8a",
) -> dict:
    return {
        "insertId": insert_id,
        "jsonPayload": {
            "@type": "type.googleapis.com/google.cloud.scheduler.logging.AttemptStarted",
            "jobName": job_name,
            "scheduledTime": scheduled_time,
            "targetType": "HTTP",
            "url": url,
        },
        "logName": f"projects/{project_id}/logs/cloudscheduler.googleapis.com%2Fexecutions",
        "receiveTimestamp": "2026-03-25T19:01:02.017128147Z",
        "resource": {
            "labels": {
                "job_id": job_name.rsplit("/", 1)[-1],
                "location": "us-central1",
                "project_id": project_id,
            },
            "type": "cloud_scheduler_job",
        },
        "severity": "INFO",
        "timestamp": timestamp,
    }


def _make_attempt_finished(
    job_name: str = "projects/proj/locations/us-central1/jobs/trigger-normal-worker",
    url: str = "https://normal-worker-1013530516622.us-central1.run.app/",
    timestamp: str = "2026-03-25T19:01:02.109150691Z",
    insert_id: str = "1e014qbf70zu2t",
    status_code: int = 200,
    debug_info: str = "URL_CRAWLED. Original HTTP response code number = 200",
    error_status: str | None = None,
) -> dict:
    payload = {
        "@type": "type.googleapis.com/google.cloud.scheduler.logging.AttemptFinished",
        "debugInfo": debug_info,
        "jobName": job_name,
        "targetType": "HTTP",
        "url": url,
    }
    if error_status:
        payload["status"] = error_status
    raw = {
        "httpRequest": {"status": status_code},
        "insertId": insert_id,
        "jsonPayload": payload,
        "logName": "projects/proj/logs/cloudscheduler.googleapis.com%2Fexecutions",
        "receiveTimestamp": timestamp,
        "resource": {
            "labels": {
                "job_id": job_name.rsplit("/", 1)[-1],
                "location": "us-central1",
                "project_id": "proj",
            },
            "type": "cloud_scheduler_job",
        },
        "severity": "INFO",
        "timestamp": timestamp,
    }
    return raw


# ── Format detection ──


class TestCanParseScheduler:
    def test_detects_attempt_started(self):
        assert can_parse_scheduler(_make_attempt_started()) is True

    def test_detects_attempt_finished(self):
        assert can_parse_scheduler(_make_attempt_finished()) is True

    def test_rejects_audit_log(self):
        raw = {"protoPayload": {"serviceName": "iam.googleapis.com"}, "timestamp": "2026-03-25T10:00:00Z"}
        assert can_parse_scheduler(raw) is False

    def test_rejects_cloudrun_log(self):
        raw = {"httpRequest": {"status": 200}, "logName": "projects/p/logs/run.googleapis.com%2Frequests"}
        assert can_parse_scheduler(raw) is False

    def test_rejects_empty_dict(self):
        assert can_parse_scheduler({}) is False


# ── Parsing AttemptStarted ──


class TestParseAttemptStarted:
    def test_extracts_job_name(self):
        result = parse_scheduler_log(_make_attempt_started())
        assert result.job_name == "projects/proj/locations/us-central1/jobs/trigger-normal-worker"

    def test_extracts_job_id(self):
        result = parse_scheduler_log(_make_attempt_started())
        assert result.job_id == "trigger-normal-worker"

    def test_extracts_scheduled_time(self):
        result = parse_scheduler_log(_make_attempt_started())
        assert result.scheduled_time == datetime(2026, 3, 25, 19, 0, 53, 958750)

    def test_extracts_target_url(self):
        result = parse_scheduler_log(_make_attempt_started())
        assert result.target_url == "https://normal-worker-1013530516622.us-central1.run.app/"

    def test_attempt_type_is_started(self):
        result = parse_scheduler_log(_make_attempt_started())
        assert result.attempt_type == "AttemptStarted"

    def test_extracts_timestamp(self):
        result = parse_scheduler_log(_make_attempt_started())
        assert result.timestamp.year == 2026

    def test_extracts_insert_id(self):
        result = parse_scheduler_log(_make_attempt_started())
        assert result.insert_id == "1qhiz4xf2nt1ny"

    def test_extracts_project_id(self):
        result = parse_scheduler_log(_make_attempt_started())
        assert result.project_id == "project-1f4f13c5-912e-45ae-b8a"

    def test_status_is_none_for_started(self):
        result = parse_scheduler_log(_make_attempt_started())
        assert result.status is None

    def test_http_status_is_none_for_started(self):
        result = parse_scheduler_log(_make_attempt_started())
        assert result.http_status is None


# ── Parsing AttemptFinished ──


class TestParseAttemptFinished:
    def test_attempt_type_is_finished(self):
        result = parse_scheduler_log(_make_attempt_finished())
        assert result.attempt_type == "AttemptFinished"

    def test_http_status_success(self):
        result = parse_scheduler_log(_make_attempt_finished(status_code=200))
        assert result.http_status == 200

    def test_http_status_error(self):
        result = parse_scheduler_log(_make_attempt_finished(
            status_code=500,
            debug_info="URL_REJECTED. Original HTTP response code number = 500",
            error_status="INTERNAL",
        ))
        assert result.http_status == 500
        assert result.status == "INTERNAL"

    def test_no_scheduled_time_for_finished(self):
        result = parse_scheduler_log(_make_attempt_finished())
        assert result.scheduled_time is None


# ── Edge cases ──


class TestSchedulerEdgeCases:
    def test_missing_url(self):
        raw = _make_attempt_started()
        del raw["jsonPayload"]["url"]
        result = parse_scheduler_log(raw)
        assert result.target_url is None

    def test_missing_scheduled_time(self):
        raw = _make_attempt_started()
        del raw["jsonPayload"]["scheduledTime"]
        result = parse_scheduler_log(raw)
        assert result.scheduled_time is None

    def test_missing_timestamp_raises(self):
        raw = _make_attempt_started()
        del raw["timestamp"]
        with pytest.raises(KeyError):
            parse_scheduler_log(raw)
