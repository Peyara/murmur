"""
Per-instance evaluation harness.

Takes per-(actor, window) scores from any detector and Campaign ground truth.
Ranks alerts by score, applies fixed alert budget per virtual day, and evaluates
detection at the campaign level (not window level).

FUNDAMENTAL EVALUATION UNIT: Attack instance (Campaign).
- One campaign = one (actor, [t_start, t_end], flavor) ground-truth label.
- Detection = any top-K budgeted (actor, window_time) alert overlaps [t_start, t_end].
- One campaign counts ONCE whether it spans 1 window or 40 (no pseudo-replication).

This harness is detector-agnostic: works for any detector that outputs
(actor, window_time, score) tuples.
"""

from typing import List, Dict, Tuple, Set, Optional
from collections import defaultdict
from dataclasses import dataclass
from bakeoff.worldgen.model import Campaign


@dataclass(frozen=True)
class Alert:
    """
    A single (actor, window_time, score) alert from a detector.

    Attributes:
        actor: hashed actor ID (as appears in detector output)
        window_time: time stamp of the window end (float)
        score: detector score for this (actor, window) pair (float)
    """
    actor: str
    window_time: float
    score: float


@dataclass(frozen=True)
class DetectionResult:
    """
    Per-campaign detection result.

    Attributes:
        campaign: the Campaign object (ground truth)
        detected: bool — was this campaign detected (any budgeted alert overlapped)?
        overlapping_alert: Optional Alert — the budgeted alert that triggered detection,
                          or None if not detected. (For diagnostic/tracing purposes.)
        budget_day_index: int — which virtual day did the overlapping alert come from?
    """
    campaign: Campaign
    detected: bool
    overlapping_alert: Optional[Alert] = None
    budget_day_index: Optional[int] = None


def evaluate_per_instance(
    alerts: List[Alert],
    campaigns: List[Campaign],
    *,
    alerts_per_day: int,
    virtual_day_duration: float = 86400.0,  # seconds (1 day)
) -> Dict[str, any]:
    """
    Evaluate detection at the campaign (instance) level.

    Algorithm:
    1. Rank all alerts by score (descending).
    2. Allocate an alert budget per virtual day: top-K alerts per day are "budgeted"
       and count for detection. Remaining alerts are discarded.
    3. For each campaign, check if any budgeted alert (same actor, window_time in or
       overlapping [t_start, t_end]) exists. If yes, campaign is DETECTED.
    4. Return per-flavor detection rates and overall statistics.

    Args:
        alerts: list of Alert objects from the detector.
        campaigns: list of Campaign objects (ground truth).
        alerts_per_day: K — number of alerts budgeted per virtual day (e.g., K=9
                       per the falsification plan's Hopper scaling).
        virtual_day_duration: duration of one virtual day in seconds (default 86400 = 1 day).
                             Adjust for different simulation time scales.

    Returns:
        Dictionary with keys:
            'detection_results': List[DetectionResult] — per-campaign detection outcome
            'detected_campaigns': int — total number of detected campaigns
            'total_campaigns': int — total number of campaigns
            'detection_rate': float — overall detection rate (0.0 to 1.0)
            'per_flavor_detection_rates': Dict[str, float] — detection rate per attack flavor
            'per_flavor_counts': Dict[str, Tuple[int, int]] — (detected, total) per flavor
            'budgeted_alerts': List[Alert] — the alerts that were within budget
    """

    if not campaigns:
        return {
            'detection_results': [],
            'detected_campaigns': 0,
            'total_campaigns': 0,
            'detection_rate': 0.0,
            'per_flavor_detection_rates': {},
            'per_flavor_counts': {},
            'budgeted_alerts': [],
        }

    # === STEP 1: Rank alerts by score (descending) ===
    ranked_alerts = sorted(alerts, key=lambda a: a.score, reverse=True)

    # === STEP 2: Budget allocation per virtual day ===
    # Partition alerts into virtual days based on window_time
    alerts_by_day: Dict[int, List[Alert]] = defaultdict(list)

    for alert in ranked_alerts:
        day_index = int(alert.window_time / virtual_day_duration)
        alerts_by_day[day_index].append(alert)

    # Within each day, take only the top-K alerts
    budgeted_alerts: Set[Tuple[str, float]] = set()  # (actor, window_time) tuples

    for day_index in sorted(alerts_by_day.keys()):
        day_alerts = sorted(
            alerts_by_day[day_index],
            key=lambda a: a.score,
            reverse=True
        )
        for alert in day_alerts[:alerts_per_day]:
            budgeted_alerts.add((alert.actor, alert.window_time))

    # Reconstruct budgeted alerts as Alert objects for output
    budgeted_alert_list = [
        alert for alert in ranked_alerts
        if (alert.actor, alert.window_time) in budgeted_alerts
    ]

    # === STEP 3: Per-campaign detection ===
    detection_results: List[DetectionResult] = []
    detected_by_flavor: Dict[str, int] = defaultdict(int)
    total_by_flavor: Dict[str, int] = defaultdict(int)

    for campaign in campaigns:
        total_by_flavor[campaign.flavor] += 1

        # Check if any budgeted alert overlaps this campaign
        campaign_detected = False
        overlapping_alert: Optional[Alert] = None
        budget_day_index: Optional[int] = None

        for alert in budgeted_alert_list:
            # Alert overlaps campaign if:
            # - Same actor
            # - Alert's window_time falls within [t_start, t_end]
            if (
                alert.actor == campaign.actor_hash
                and campaign.t_start <= alert.window_time <= campaign.t_end
            ):
                campaign_detected = True
                overlapping_alert = alert
                budget_day_index = int(alert.window_time / virtual_day_duration)
                break  # Only need one overlapping alert per campaign

        if campaign_detected:
            detected_by_flavor[campaign.flavor] += 1

        result = DetectionResult(
            campaign=campaign,
            detected=campaign_detected,
            overlapping_alert=overlapping_alert,
            budget_day_index=budget_day_index,
        )
        detection_results.append(result)

    # === STEP 4: Compute statistics ===
    total_detected = sum(1 for r in detection_results if r.detected)
    total_campaigns = len(campaigns)

    overall_detection_rate = (
        total_detected / total_campaigns if total_campaigns > 0 else 0.0
    )

    # Per-flavor detection rates
    per_flavor_rates: Dict[str, float] = {}
    per_flavor_counts: Dict[str, Tuple[int, int]] = {}

    for flavor in total_by_flavor.keys():
        detected = detected_by_flavor[flavor]
        total = total_by_flavor[flavor]
        rate = detected / total if total > 0 else 0.0
        per_flavor_rates[flavor] = rate
        per_flavor_counts[flavor] = (detected, total)

    return {
        'detection_results': detection_results,
        'detected_campaigns': total_detected,
        'total_campaigns': total_campaigns,
        'detection_rate': overall_detection_rate,
        'per_flavor_detection_rates': per_flavor_rates,
        'per_flavor_counts': per_flavor_counts,
        'budgeted_alerts': budgeted_alert_list,
    }


def summarize_evaluation(eval_result: Dict[str, any]) -> str:
    """
    Generate a human-readable summary of evaluation results.

    Args:
        eval_result: dictionary returned by evaluate_per_instance().

    Returns:
        String summary (for logging/reporting).
    """
    lines = []
    lines.append("=" * 70)
    lines.append("PER-INSTANCE EVALUATION SUMMARY")
    lines.append("=" * 70)

    detected = eval_result['detected_campaigns']
    total = eval_result['total_campaigns']
    rate = eval_result['detection_rate']

    lines.append(f"Overall: {detected} / {total} campaigns detected ({rate:.1%})")
    lines.append("")

    if eval_result['per_flavor_detection_rates']:
        lines.append("Per-flavor breakdown:")
        for flavor in sorted(eval_result['per_flavor_detection_rates'].keys()):
            flavor_rate = eval_result['per_flavor_detection_rates'][flavor]
            detected_f, total_f = eval_result['per_flavor_counts'][flavor]
            lines.append(
                f"  {flavor:25s}: {detected_f:3d} / {total_f:3d} ({flavor_rate:.1%})"
            )

    lines.append("")
    lines.append(f"Total budgeted alerts: {len(eval_result['budgeted_alerts'])}")
    lines.append("=" * 70)

    return "\n".join(lines)


def confusion_matrix_per_flavor(eval_result: Dict[str, any]) -> Dict[str, Dict[str, int]]:
    """
    Compute confusion matrix (TP, FP, FN, TN) per flavor.

    In this context:
    - TP: campaign detected (as it should be)
    - FN: campaign not detected (should have been)
    - FP: alert that doesn't correspond to any campaign (not counted in eval_result;
           would require alerts without campaign overlaps, which we don't track here)
    - TN: N/A (no ground-truth negatives in the campaign set)

    This simplified version reports TP and FN per flavor.

    Args:
        eval_result: dictionary returned by evaluate_per_instance().

    Returns:
        Dict mapping flavor -> {'TP': int, 'FN': int, ...}
    """
    matrix = {}

    for flavor in sorted(eval_result['per_flavor_counts'].keys()):
        detected, total = eval_result['per_flavor_counts'][flavor]
        fn = total - detected
        matrix[flavor] = {
            'TP': detected,
            'FN': fn,
            'detected_rate': detected / total if total > 0 else 0.0,
        }

    return matrix
