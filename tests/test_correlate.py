"""Tests for temporal-identity correlator."""

from datetime import datetime, timedelta

from src.ingest.cloudrun_parser import CloudRunRequest
from src.ingest.correlate import (
    ServiceWorkerMap,
    correlate_events,
    validate_service_worker_map,
)
from src.ingest.scheduler_parser import SchedulerExecution
from tests.conftest import make_event

# ── Helpers ──

WORKER_SA = "normal-worker-sa@proj.iam.gserviceaccount.com"
SERVICE_URL = "https://normal-worker-123.us-central1.run.app/"
JOB_NAME = "projects/p/locations/us-central1/jobs/trigger-normal-worker"
JOB_ID = "trigger-normal-worker"
BASE_TIME = datetime(2026, 3, 25, 19, 0, 0)

SERVICE_WORKER_MAP: ServiceWorkerMap = {
    "normal-worker": WORKER_SA,
}


def _sched(
    scheduled_time: datetime = BASE_TIME,
    timestamp: datetime | None = None,
    job_id: str = JOB_ID,
) -> SchedulerExecution:
    return SchedulerExecution(
        job_name=JOB_NAME,
        job_id=job_id,
        target_url=SERVICE_URL,
        attempt_type="AttemptStarted",
        timestamp=timestamp or scheduled_time + timedelta(seconds=2),
        insert_id="sched-001",
        project_id="proj",
        scheduled_time=scheduled_time,
    )


def _cloudrun(
    timestamp: datetime = BASE_TIME + timedelta(seconds=3),
    service_name: str = "normal-worker",
    user_agent: str = "Google-Cloud-Scheduler",
    request_url: str = SERVICE_URL,
) -> CloudRunRequest:
    return CloudRunRequest(
        service_name=service_name,
        request_url=request_url,
        status_code=200,
        timestamp=timestamp,
        insert_id="cr-001",
        project_id="proj",
        user_agent=user_agent,
        is_scheduler_invoked=(user_agent == "Google-Cloud-Scheduler"),
    )


def _audit_event(
    actor_id: str = WORKER_SA,
    ts: datetime = BASE_TIME + timedelta(seconds=5),
    event_id: str = "evt-001",
):
    return make_event(
        event_id=event_id,
        actor_id=actor_id,
        ts=ts,
        window_start=ts.replace(minute=0, second=0, microsecond=0),
    )


# ── Happy path: matched triplet ──


class TestMatchedTriplet:
    def test_assigns_trigger_ref(self):
        results = correlate_events(
            scheduler_entries=[_sched()],
            cloudrun_entries=[_cloudrun()],
            audit_events=[_audit_event()],
            service_worker_map=SERVICE_WORKER_MAP,
        )
        assert len(results) == 1
        assert results[0].trigger_ref is not None
        assert results[0].trigger_ref.startswith("sched:")

    def test_trigger_ref_contains_job_id(self):
        results = correlate_events(
            scheduler_entries=[_sched()],
            cloudrun_entries=[_cloudrun()],
            audit_events=[_audit_event()],
            service_worker_map=SERVICE_WORKER_MAP,
        )
        assert JOB_ID in results[0].trigger_ref

    def test_confidence_above_zero(self):
        results = correlate_events(
            scheduler_entries=[_sched()],
            cloudrun_entries=[_cloudrun()],
            audit_events=[_audit_event()],
            service_worker_map=SERVICE_WORKER_MAP,
        )
        assert results[0].correlation_confidence > 0.0

    def test_high_confidence_for_perfect_match(self):
        """Perfect match: identity + URL + single candidate + tight timing."""
        results = correlate_events(
            scheduler_entries=[_sched()],
            cloudrun_entries=[_cloudrun()],
            audit_events=[_audit_event()],
            service_worker_map=SERVICE_WORKER_MAP,
        )
        assert results[0].correlation_confidence > 0.8

    def test_annotates_original_event(self):
        """The returned CorrelationResult references the original event."""
        event = _audit_event()
        results = correlate_events(
            scheduler_entries=[_sched()],
            cloudrun_entries=[_cloudrun()],
            audit_events=[event],
            service_worker_map=SERVICE_WORKER_MAP,
        )
        assert results[0].event.event_id == event.event_id


# ── No match scenarios ──


class TestNoMatch:
    def test_no_scheduler_entries(self):
        results = correlate_events(
            scheduler_entries=[],
            cloudrun_entries=[_cloudrun()],
            audit_events=[_audit_event()],
            service_worker_map=SERVICE_WORKER_MAP,
        )
        assert len(results) == 1
        assert results[0].trigger_ref is None
        assert results[0].correlation_confidence == 0.0

    def test_no_cloudrun_entries(self):
        results = correlate_events(
            scheduler_entries=[_sched()],
            cloudrun_entries=[],
            audit_events=[_audit_event()],
            service_worker_map=SERVICE_WORKER_MAP,
        )
        assert len(results) == 1
        assert results[0].trigger_ref is None

    def test_actor_not_in_service_map(self):
        results = correlate_events(
            scheduler_entries=[_sched()],
            cloudrun_entries=[_cloudrun()],
            audit_events=[_audit_event(actor_id="unknown-sa@proj.iam.gserviceaccount.com")],
            service_worker_map=SERVICE_WORKER_MAP,
        )
        assert len(results) == 1
        assert results[0].trigger_ref is None

    def test_cloudrun_not_scheduler_invoked(self):
        results = correlate_events(
            scheduler_entries=[_sched()],
            cloudrun_entries=[_cloudrun(user_agent="curl/7.68.0")],
            audit_events=[_audit_event()],
            service_worker_map=SERVICE_WORKER_MAP,
        )
        assert len(results) == 1
        assert results[0].trigger_ref is None

    def test_audit_event_too_far_after_cloudrun(self):
        """Audit event 5 minutes after Cloud Run — outside correlation window."""
        results = correlate_events(
            scheduler_entries=[_sched()],
            cloudrun_entries=[_cloudrun()],
            audit_events=[_audit_event(ts=BASE_TIME + timedelta(minutes=5))],
            service_worker_map=SERVICE_WORKER_MAP,
        )
        assert len(results) == 1
        assert results[0].trigger_ref is None

    def test_audit_event_before_scheduler(self):
        """Audit event before scheduler fired — can't be caused by it."""
        results = correlate_events(
            scheduler_entries=[_sched()],
            cloudrun_entries=[_cloudrun()],
            audit_events=[_audit_event(ts=BASE_TIME - timedelta(seconds=10))],
            service_worker_map=SERVICE_WORKER_MAP,
        )
        assert len(results) == 1
        assert results[0].trigger_ref is None


# ── Ambiguous matches ──


class TestAmbiguousMatches:
    def test_multiple_scheduler_entries_picks_closest(self):
        """Two scheduler executions — correlator picks the one closest in time."""
        sched1 = _sched(scheduled_time=BASE_TIME - timedelta(minutes=5))
        sched2 = _sched(scheduled_time=BASE_TIME)
        results = correlate_events(
            scheduler_entries=[sched1, sched2],
            cloudrun_entries=[_cloudrun()],
            audit_events=[_audit_event()],
            service_worker_map=SERVICE_WORKER_MAP,
        )
        assert len(results) == 1
        assert results[0].trigger_ref is not None
        # Should pick sched2 (closer in time)
        scheduled_epoch = str(int(BASE_TIME.timestamp()))
        assert scheduled_epoch in results[0].trigger_ref

    def test_ambiguity_lowers_confidence(self):
        """Multiple Cloud Run requests in window → lower confidence due to ambiguity."""
        cr1 = _cloudrun(timestamp=BASE_TIME + timedelta(seconds=3))
        cr2 = _cloudrun(timestamp=BASE_TIME + timedelta(seconds=4))
        results = correlate_events(
            scheduler_entries=[_sched()],
            cloudrun_entries=[cr1, cr2],
            audit_events=[_audit_event()],
            service_worker_map=SERVICE_WORKER_MAP,
        )
        assert len(results) == 1
        # Still matches, but confidence should be lower than single-candidate case
        single_result = correlate_events(
            scheduler_entries=[_sched()],
            cloudrun_entries=[_cloudrun()],
            audit_events=[_audit_event()],
            service_worker_map=SERVICE_WORKER_MAP,
        )
        assert results[0].correlation_confidence < single_result[0].correlation_confidence


# ── Multiple events ──


class TestMultipleEvents:
    def test_correlates_multiple_audit_events_from_same_execution(self):
        """Worker SA does 3 things after one scheduler trigger — all get same trigger_ref."""
        events = [
            _audit_event(event_id="evt-1", ts=BASE_TIME + timedelta(seconds=5)),
            _audit_event(event_id="evt-2", ts=BASE_TIME + timedelta(seconds=7)),
            _audit_event(event_id="evt-3", ts=BASE_TIME + timedelta(seconds=10)),
        ]
        results = correlate_events(
            scheduler_entries=[_sched()],
            cloudrun_entries=[_cloudrun()],
            audit_events=events,
            service_worker_map=SERVICE_WORKER_MAP,
        )
        assert len(results) == 3
        refs = {r.trigger_ref for r in results}
        assert len(refs) == 1  # all same trigger_ref
        assert None not in refs

    def test_different_actors_only_correlate_matching_sa(self):
        """Events from a different SA don't get correlated."""
        events = [
            _audit_event(event_id="evt-worker", actor_id=WORKER_SA),
            _audit_event(event_id="evt-other", actor_id="other-sa@proj.iam.gserviceaccount.com"),
        ]
        results = correlate_events(
            scheduler_entries=[_sched()],
            cloudrun_entries=[_cloudrun()],
            audit_events=events,
            service_worker_map=SERVICE_WORKER_MAP,
        )
        worker_result = [r for r in results if r.event.event_id == "evt-worker"][0]
        other_result = [r for r in results if r.event.event_id == "evt-other"][0]
        assert worker_result.trigger_ref is not None
        assert other_result.trigger_ref is None


# ── Retry pattern ──


class TestRetryPattern:
    def test_retry_correlates_to_same_scheduler_execution(self):
        """Cloud Run 500 → retry → both audit events from retry get trigger_ref."""
        cr_fail = _cloudrun(timestamp=BASE_TIME + timedelta(seconds=3))
        cr_fail = CloudRunRequest(
            service_name=cr_fail.service_name,
            request_url=cr_fail.request_url,
            status_code=500,
            timestamp=cr_fail.timestamp,
            insert_id="cr-fail",
            project_id=cr_fail.project_id,
            user_agent="Google-Cloud-Scheduler",
            is_scheduler_invoked=True,
        )
        cr_retry = _cloudrun(timestamp=BASE_TIME + timedelta(seconds=10))
        # Events from the retry invocation
        events = [
            _audit_event(event_id="evt-retry-1", ts=BASE_TIME + timedelta(seconds=12)),
        ]
        results = correlate_events(
            scheduler_entries=[_sched()],
            cloudrun_entries=[cr_fail, cr_retry],
            audit_events=events,
            service_worker_map=SERVICE_WORKER_MAP,
        )
        assert results[0].trigger_ref is not None


# ── Hydration validation ──


class TestValidateServiceWorkerMap:
    def test_confirmed_mapping(self):
        """Configured SA matches observed SA → confirmed."""
        cr1 = _cloudrun()
        cr2 = CloudRunRequest(
            service_name="normal-worker",
            request_url=SERVICE_URL,
            status_code=200,
            timestamp=BASE_TIME + timedelta(minutes=5, seconds=3),
            insert_id="cr-002",
            project_id="proj",
            user_agent="Google-Cloud-Scheduler",
            is_scheduler_invoked=True,
        )
        report = validate_service_worker_map(
            scheduler_entries=[_sched(), _sched(scheduled_time=BASE_TIME + timedelta(minutes=5))],
            cloudrun_entries=[cr1, cr2],
            audit_events=[
                _audit_event(event_id="e1"),
                _audit_event(event_id="e2", ts=BASE_TIME + timedelta(minutes=5, seconds=5)),
            ],
            service_worker_map=SERVICE_WORKER_MAP,
        )
        assert len(report.confirmed_mappings) == 1
        assert report.confirmed_mappings[0] == ("normal-worker", WORKER_SA)
        assert report.hydration_complete is True
        assert report.min_observations >= 2

    def test_mismatched_mapping(self):
        """Configured SA doesn't match observed → mismatch."""
        wrong_map: ServiceWorkerMap = {"normal-worker": "wrong-sa@proj.iam.gserviceaccount.com"}
        report = validate_service_worker_map(
            scheduler_entries=[_sched()],
            cloudrun_entries=[_cloudrun()],
            audit_events=[_audit_event()],
            service_worker_map=wrong_map,
        )
        assert len(report.mismatched_mappings) == 1
        assert report.mismatched_mappings[0][0] == "normal-worker"
        assert report.mismatched_mappings[0][1] == "wrong-sa@proj.iam.gserviceaccount.com"
        assert report.mismatched_mappings[0][2] == WORKER_SA
        assert report.hydration_complete is False

    def test_discovered_mapping(self):
        """Service has scheduler traffic + observed SA but no config → discovered."""
        report = validate_service_worker_map(
            scheduler_entries=[_sched()],
            cloudrun_entries=[_cloudrun()],
            audit_events=[_audit_event()],
            service_worker_map={},  # empty config
        )
        assert len(report.discovered_mappings) == 1
        assert report.discovered_mappings[0][0] == "normal-worker"
        assert report.discovered_mappings[0][1] == WORKER_SA

    def test_no_observations(self):
        """No data at all → not hydrated."""
        report = validate_service_worker_map(
            scheduler_entries=[],
            cloudrun_entries=[],
            audit_events=[],
            service_worker_map=SERVICE_WORKER_MAP,
        )
        assert report.hydration_complete is False
        assert report.min_observations == 0

    def test_multiple_sas_picks_most_frequent(self):
        """Multiple SAs observed → picks the most frequent one."""
        other_sa = "other-sa@proj.iam.gserviceaccount.com"
        events = [
            _audit_event(event_id="e1", ts=BASE_TIME + timedelta(seconds=5)),
            _audit_event(event_id="e2", ts=BASE_TIME + timedelta(seconds=6)),
            _audit_event(event_id="e3", ts=BASE_TIME + timedelta(seconds=7)),
            _audit_event(event_id="e4", actor_id=other_sa, ts=BASE_TIME + timedelta(seconds=8)),
        ]
        report = validate_service_worker_map(
            scheduler_entries=[_sched()],
            cloudrun_entries=[_cloudrun()],
            audit_events=events,
            service_worker_map=SERVICE_WORKER_MAP,
        )
        assert len(report.confirmed_mappings) == 1
        assert report.confirmed_mappings[0][1] == WORKER_SA
