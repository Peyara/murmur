"""Temporal-identity correlator for deriving trigger_ref.

Joins three log streams (scheduler executions, Cloud Run requests, audit events)
to derive trigger_ref and correlation_confidence for audit log CanonicalEvents.

The causal chain: Scheduler fires → Cloud Run receives request → Worker SA executes API calls.

Correlation confidence is a composite of:
  - identity_match (0.4): audit event actor matches expected worker SA
  - url_match (0.3): scheduler target URL matches Cloud Run request URL
  - ambiguity_penalty (0.2): 1/candidate_count — fewer candidates = higher confidence
  - temporal_ratio (0.1): gap/cadence — tighter relative timing = higher confidence
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta

from src.ingest.cloudrun_parser import CloudRunRequest
from src.ingest.scheduler_parser import SchedulerExecution
from src.schema import CanonicalEvent

# Type alias: maps Cloud Run service_name → expected worker SA email
ServiceWorkerMap = dict[str, str]

# Correlation windows (generous — calibrate against real data in Session C)
_SCHED_TO_CLOUDRUN_WINDOW = timedelta(seconds=60)
_CLOUDRUN_TO_AUDIT_WINDOW = timedelta(seconds=120)

# Confidence component weights (initial estimates — calibrate in Session C)
_W_IDENTITY = 0.4
_W_URL = 0.3
_W_AMBIGUITY = 0.2
_W_TEMPORAL = 0.1


@dataclass
class CorrelationResult:
    """An audit event annotated with correlation outcome."""

    event: CanonicalEvent
    trigger_ref: str | None
    correlation_confidence: float
    matched_scheduler: SchedulerExecution | None = None
    matched_cloudrun: CloudRunRequest | None = None


@dataclass
class _SchedulerCloudRunLink:
    """Internal: a matched scheduler → Cloud Run pair."""

    scheduler: SchedulerExecution
    cloudrun: CloudRunRequest
    url_match: bool


def _estimate_cadence(scheduler_entries: list[SchedulerExecution]) -> float:
    """Estimate job cadence in seconds from consecutive AttemptStarted entries.

    Returns the median interval, or 300.0 (5 min default) if insufficient data.
    """
    started = sorted(
        [s for s in scheduler_entries if s.attempt_type == "AttemptStarted" and s.scheduled_time],
        key=lambda s: s.scheduled_time,
    )
    if len(started) < 2:
        return 300.0

    intervals = []
    for i in range(1, len(started)):
        gap = (started[i].scheduled_time - started[i - 1].scheduled_time).total_seconds()
        if gap > 0:
            intervals.append(gap)

    if not intervals:
        return 300.0

    intervals.sort()
    return intervals[len(intervals) // 2]


def _link_scheduler_to_cloudrun(
    scheduler_entries: list[SchedulerExecution],
    cloudrun_entries: list[CloudRunRequest],
) -> list[_SchedulerCloudRunLink]:
    """Match scheduler AttemptStarted entries to Cloud Run requests.

    Match criteria:
      - Cloud Run user_agent is "Google-Cloud-Scheduler" (is_scheduler_invoked)
      - Cloud Run timestamp is within window after scheduler scheduled_time
      - URL match (scheduler target_url matches Cloud Run request_url)
    """
    started = [s for s in scheduler_entries if s.attempt_type == "AttemptStarted" and s.scheduled_time]
    scheduler_invoked = [cr for cr in cloudrun_entries if cr.is_scheduler_invoked]

    links: list[_SchedulerCloudRunLink] = []
    used_cloudrun: set[str] = set()  # track by insert_id to avoid double-matching

    for sched in sorted(started, key=lambda s: s.scheduled_time):
        best_cr: CloudRunRequest | None = None
        best_gap = _SCHED_TO_CLOUDRUN_WINDOW.total_seconds()
        url_match = False

        for cr in scheduler_invoked:
            if cr.insert_id in used_cloudrun:
                continue
            gap = (cr.timestamp - sched.scheduled_time).total_seconds()
            if gap < 0 or gap > _SCHED_TO_CLOUDRUN_WINDOW.total_seconds():
                continue
            # URL match check
            cr_url_matches = (
                sched.target_url is not None
                and cr.request_url
                and sched.target_url.rstrip("/") == cr.request_url.rstrip("/")
            )
            if gap < best_gap or (gap == best_gap and cr_url_matches):
                best_cr = cr
                best_gap = gap
                url_match = cr_url_matches

        if best_cr:
            used_cloudrun.add(best_cr.insert_id)
            links.append(_SchedulerCloudRunLink(scheduler=sched, cloudrun=best_cr, url_match=url_match))

    return links


def _compute_confidence(
    identity_match: bool,
    url_match: bool,
    candidate_count: int,
    temporal_gap_seconds: float,
    cadence_seconds: float,
) -> float:
    """Compute composite correlation confidence.

    Components:
      - identity_match: actor SA matches expected worker (binary)
      - url_match: scheduler URL matches Cloud Run URL (binary)
      - ambiguity: 1/candidate_count (fewer = better)
      - temporal_ratio: 1 - (gap/cadence), clamped to [0, 1]
    """
    id_score = 1.0 if identity_match else 0.0
    url_score = 1.0 if url_match else 0.0
    ambiguity_score = 1.0 / max(candidate_count, 1)
    temporal_ratio = max(0.0, 1.0 - (temporal_gap_seconds / cadence_seconds)) if cadence_seconds > 0 else 0.5

    confidence = (
        _W_IDENTITY * id_score
        + _W_URL * url_score
        + _W_AMBIGUITY * ambiguity_score
        + _W_TEMPORAL * temporal_ratio
    )
    return round(min(1.0, max(0.0, confidence)), 4)


def correlate_events(
    scheduler_entries: list[SchedulerExecution],
    cloudrun_entries: list[CloudRunRequest],
    audit_events: list[CanonicalEvent],
    service_worker_map: ServiceWorkerMap,
) -> list[CorrelationResult]:
    """Correlate audit events with scheduler executions via Cloud Run requests.

    Returns one CorrelationResult per audit event (in the same order).
    Events that can't be correlated get trigger_ref=None, confidence=0.0.
    """
    if not audit_events:
        return []

    # Build reverse map: worker_sa → service_name
    sa_to_service: dict[str, str] = {sa: svc for svc, sa in service_worker_map.items()}

    # Link scheduler → Cloud Run
    links = _link_scheduler_to_cloudrun(scheduler_entries, cloudrun_entries)

    # Estimate cadence for temporal confidence
    cadence = _estimate_cadence(scheduler_entries)

    # For each link, count how many Cloud Run candidates were in that scheduler's window
    # (used for ambiguity penalty)
    scheduler_invoked = [cr for cr in cloudrun_entries if cr.is_scheduler_invoked]

    results: list[CorrelationResult] = []

    for event in audit_events:
        # Can this actor be linked to a known service?
        service_name = sa_to_service.get(event.actor_id)
        if service_name is None:
            results.append(CorrelationResult(event=event, trigger_ref=None, correlation_confidence=0.0))
            continue

        # Find the best matching link for this event
        best_link: _SchedulerCloudRunLink | None = None
        best_gap = _CLOUDRUN_TO_AUDIT_WINDOW.total_seconds()

        for link in links:
            # Check service match via Cloud Run service_name
            if link.cloudrun.service_name != service_name:
                continue
            # Temporal: audit event must be after Cloud Run request
            gap = (event.ts - link.cloudrun.timestamp).total_seconds()
            if gap < 0 or gap > _CLOUDRUN_TO_AUDIT_WINDOW.total_seconds():
                continue
            if gap < best_gap:
                best_link = link
                best_gap = gap

        if best_link is None:
            results.append(CorrelationResult(event=event, trigger_ref=None, correlation_confidence=0.0))
            continue

        # Count candidates in the scheduler→cloudrun window for ambiguity
        sched_time = best_link.scheduler.scheduled_time
        candidate_count = sum(
            1
            for cr in scheduler_invoked
            if 0 <= (cr.timestamp - sched_time).total_seconds() <= _SCHED_TO_CLOUDRUN_WINDOW.total_seconds()
            and cr.service_name == service_name
        )

        # Compute confidence
        confidence = _compute_confidence(
            identity_match=True,  # already verified via sa_to_service
            url_match=best_link.url_match,
            candidate_count=candidate_count,
            temporal_gap_seconds=best_gap,
            cadence_seconds=cadence,
        )

        # Derive trigger_ref
        scheduled_epoch = int(best_link.scheduler.scheduled_time.timestamp())
        trigger_ref = f"sched:{best_link.scheduler.job_id}:{scheduled_epoch}"

        results.append(CorrelationResult(
            event=event,
            trigger_ref=trigger_ref,
            correlation_confidence=confidence,
            matched_scheduler=best_link.scheduler,
            matched_cloudrun=best_link.cloudrun,
        ))

    return results


# ---------------------------------------------------------------------------
# Hydration validation — verify service_worker_map against observed data
# ---------------------------------------------------------------------------


@dataclass
class HydrationReport:
    """Result of validating service_worker_map against observed patterns."""

    confirmed_mappings: list[tuple[str, str]] = field(default_factory=list)
    mismatched_mappings: list[tuple[str, str, str]] = field(default_factory=list)
    discovered_mappings: list[tuple[str, str, int]] = field(default_factory=list)
    hydration_complete: bool = False
    min_observations: int = 0


def validate_service_worker_map(
    scheduler_entries: list[SchedulerExecution],
    cloudrun_entries: list[CloudRunRequest],
    audit_events: list[CanonicalEvent],
    service_worker_map: ServiceWorkerMap,
) -> HydrationReport:
    """Validate configured service→SA mappings against observed log patterns.

    Uses hop 1 (scheduler→cloudrun, fully deterministic) to identify services
    with scheduler-invoked traffic, then observes which SAs produce audit events
    in the post-request windows. Compares against configured mappings.
    """
    report = HydrationReport()

    # Hop 1: link scheduler → Cloud Run (no config needed)
    links = _link_scheduler_to_cloudrun(scheduler_entries, cloudrun_entries)

    if not links:
        # No scheduler→cloudrun links observed — can't validate
        report.min_observations = 0
        report.hydration_complete = False
        return report

    # Group links by Cloud Run service
    service_windows: dict[str, list[_SchedulerCloudRunLink]] = {}
    for link in links:
        svc = link.cloudrun.service_name
        service_windows.setdefault(svc, []).append(link)

    # For each service, find SAs that produce audit events in post-request windows
    observed_sas: dict[str, Counter] = {}
    for svc, svc_links in service_windows.items():
        sa_counter: Counter = Counter()
        for link in svc_links:
            cr_ts = link.cloudrun.timestamp
            window_end = cr_ts + _CLOUDRUN_TO_AUDIT_WINDOW
            for event in audit_events:
                if event.ts >= cr_ts and event.ts <= window_end:
                    sa_counter[event.actor_id] += 1
        if sa_counter:
            observed_sas[svc] = sa_counter

    # Compare against config
    observation_counts: list[int] = []

    for svc, sa_counter in observed_sas.items():
        most_common_sa, count = sa_counter.most_common(1)[0]
        observation_counts.append(count)

        if svc in service_worker_map:
            configured_sa = service_worker_map[svc]
            if configured_sa == most_common_sa:
                report.confirmed_mappings.append((svc, most_common_sa))
            else:
                report.mismatched_mappings.append((svc, configured_sa, most_common_sa))
        else:
            report.discovered_mappings.append((svc, most_common_sa, count))

    # Check for configured services with no observations
    for svc in service_worker_map:
        if svc not in observed_sas and svc not in {m[0] for m in report.confirmed_mappings}:
            observation_counts.append(0)

    report.min_observations = min(observation_counts) if observation_counts else 0
    report.hydration_complete = (
        len(report.confirmed_mappings) == len(service_worker_map)
        and len(service_worker_map) > 0
        and report.min_observations > 0
        and len(report.mismatched_mappings) == 0
    )

    return report
