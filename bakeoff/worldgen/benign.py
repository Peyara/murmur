"""
Benign actor trajectory generation.

Each of the nine archetype kinds (§3.1) is implemented as a semi-Markov process
generating a sequence of RawEvents with archetype-specific transition structure,
dwell times, and temporal rhythms.

All functions are deterministic per (archetype_kind, actor_id, config, seed).
Regeneration with same parameters must be byte-identical.

---

KEY DESIGN NOTES:

1. ARCHETYPE-SPECIFIC RHYTHMS:
   - Developer: cyclic daily loop (IDENTITY → COMPUTE → DATA → COMPUTE → logout).
     Near time-reversible at distribution level.
   - DataAnalyst: cyclic (IDENTITY → DATA → COMPUTE); occasional SECRET for credentials.
   - CICDServiceAccount: extremely regular machine loop (IDENTITY → SECRET → COMPUTE → DATA).
   - ETLPipelineServiceAccount: benign one-way (IDENTITY → SECRET → DATA → EXTERNAL).
     Deliberately irreversible by design — tests if detectors falsely equate "irreversible"
     with "malicious."
   - BackupLogShippingAccount: benign one-way (DATA → LOGGING / DATA → EXTERNAL);
     fixed schedule. Same purpose as ETL.
   - OnCallSRE: mostly dormant; during on-call windows, sudden rare access to resources
     never touched before. Canonical Hopper false-positive.
   - NewHire: starts with zero history, explores broadly for first N days, then settles
     into developer/analyst pattern.
   - RoleChange: mid-simulation, actor's archetype switches; old distribution stale.
   - BreakGlassAdmin: rare, high-privilege one-shot (IDENTITY → ADMIN → SECRET), then
     dormant. Rare, irreversible-looking, benign.

2. DWELL TIME DISTRIBUTIONS:
   Each zone transition is separated by a dwell time sampled from an archetype-specific
   distribution (log-normal for some; Poisson intervals for others). Dwell times decay
   naturally into observed inter-event times.

3. DETERMINISM:
   All randomness seeded. Given (archetype_kind, actor_id, config, seed), the trajectory
   is fully determined. No global RNG state; each function re-seeded internally.

4. RELATION TO WORLD GENERATION:
   build_archetype() is called once per actor during world initialization (§world.py).
   The returned list[RawEvent] is inserted into the world's raw_event log in time order.

---

FROZEN STUB SIGNATURE (do not modify):
"""

from typing import List
from .model import RawEvent, WorldConfig, ArchetypeKind


def build_archetype(
    kind: ArchetypeKind,
    actor_id: str,
    config: WorldConfig,
    seed: int,
) -> List[RawEvent]:
    """
    Generate a sequence of benign RawEvents for an actor of the given archetype.

    Implements the trajectory for one of the nine benign archetypes (§3.1).
    All randomness is seeded; regeneration with same parameters must be byte-identical.

    The function:
    - Simulates the actor's behavior over the full config.horizon_days
    - Samples transitions from archetype-specific distributions
    - Assigns zone_src, zone_dst, action_type deterministically per archetype
    - Sets is_attack=False for all events
    - Sets attack_type=None for all events
    - Returns events in time order

    Args:
        kind: ArchetypeKind enum (Developer, DataAnalyst, ..., BreakGlassAdmin)
        actor_id: unique actor identifier (generator-side; will be hashed in anonymization)
        config: WorldConfig (contains action_vocab, zone_labels, horizon_days, event_rate_lambda)
        seed: random seed for this actor (deterministic per actor, replayable)

    Returns:
        List[RawEvent] in time order, all with is_attack=False, attack_type=None.
        Events span [0, config.horizon_days * 86400] (seconds).

    Raises:
        ValueError: if kind is invalid or config is malformed.
        NotImplementedError: (stub; to be implemented in Phase 2)

    ---

    IMPLEMENTATION CHECKLIST (for Phase 2 implementer):

    1. Seed the RNG with seed (use numpy.random.default_rng(seed)).

    2. For archetype=Developer:
       - Generate cyclic daily loop: IDENTITY → COMPUTE → DATA(read) → COMPUTE → logout
       - Use log-normal dwell times (shape ~1.5, scale ~600s for inter-zone transitions)
       - Repeat loop for all horizon_days (with 1–2h sleep per night, uniform random)

    3. For archetype=DataAnalyst:
       - Similar to Developer but heavier on DATA(read), occasional SECRET(read) for credentials
       - Zone preference: IDENTITY → DATA (60%) → COMPUTE (30%) → SECRET (10%)

    4. For archetype=CICDServiceAccount:
       - Extremely regular: IDENTITY → SECRET → COMPUTE → DATA(write) at fixed intervals
       - Poisson inter-event time (lambda from config.event_rate_lambda)
       - No randomness in zone sequence; only timestamps are noisy (±Poisson variance)

    5. For archetype=ETLPipelineServiceAccount:
       - Benign one-way: IDENTITY → SECRET → DATA(read) → EXTERNAL(write)
       - Fixed schedule (e.g., every 4 hours, with jitter)
       - Zero reverse edges; cumulative flow toward EXTERNAL

    6. For archetype=BackupLogShippingAccount:
       - Benign one-way: DATA → LOGGING(write) or DATA → EXTERNAL(write)
       - Fixed daily schedule (e.g., 02:00 UTC), with small jitter
       - No IDENTITY access; no zone transitions before DATA

    7. For archetype=OnCallSRE:
       - Mostly dormant (no events except housekeeping)
       - During on-call windows (randomly distributed, e.g., 2–4h per week),
         sudden rare access to ADMIN, COMPUTE, zones never touched before
       - Example: sudden access to 3–5 never-before-touched resources in one on-call stint

    8. For archetype=NewHire:
       - First ~5 days (from horizon start): exploratory. Visit all zones, many resources.
         High degree, high per-zone novelty.
       - Then settle into Developer or DataAnalyst pattern for the rest of horizon.
       - Mark role_change_time in Actor metadata (optional; not enforced here).

    9. For archetype=RoleChange:
       - For first portion of horizon (e.g., days 0–N), follow one archetype (e.g., Developer).
       - At role_change_time (mid-horizon), switch to another archetype pattern (e.g., SRE).
       - Pre-change history different from post-change; old distribution becomes irrelevant.

    10. For archetype=BreakGlassAdmin:
        - Dormant 95% of time (occasional low-rate DATA reads).
        - Randomly once per horizon: one rare access burst:
          IDENTITY → ADMIN → SECRET(read) → EXTERNAL(write), then back to dormancy.
        - Dwell times: 10–30s between transitions in the burst; months between bursts.

    11. Additional constraints:
        - Must use only action_vocab and zone_labels from config.
        - Timestamps must be strictly increasing and fall within [0, horizon_seconds].
        - Each event must have archetype field set to kind.value.

    12. Testing:
        - Determinism: call twice with same seed, must get identical results.
        - No label leakage: no attack_type, no zones leaked in detector-visible artifacts.
        - Convergence: at least 80 transitions per actor (to support rolling-window physics).

    """
    import numpy as np
    from datetime import datetime, timedelta

    # Seed the RNG with actor-specific seed for determinism
    rng = np.random.default_rng(seed)

    horizon_seconds = config.horizon_days * 86400
    events = []

    # Dispatch to archetype-specific generator
    if kind == ArchetypeKind.Developer:
        events = _generate_developer(actor_id, config, rng, horizon_seconds)
    elif kind == ArchetypeKind.DataAnalyst:
        events = _generate_data_analyst(actor_id, config, rng, horizon_seconds)
    elif kind == ArchetypeKind.CICDServiceAccount:
        events = _generate_cicd_sa(actor_id, config, rng, horizon_seconds)
    elif kind == ArchetypeKind.ETLPipelineServiceAccount:
        events = _generate_etl_sa(actor_id, config, rng, horizon_seconds)
    elif kind == ArchetypeKind.BackupLogShippingAccount:
        events = _generate_backup_sa(actor_id, config, rng, horizon_seconds)
    elif kind == ArchetypeKind.OnCallSRE:
        events = _generate_oncall_sre(actor_id, config, rng, horizon_seconds)
    elif kind == ArchetypeKind.NewHire:
        events = _generate_new_hire(actor_id, config, rng, horizon_seconds)
    elif kind == ArchetypeKind.RoleChange:
        events = _generate_role_change(actor_id, config, rng, horizon_seconds)
    elif kind == ArchetypeKind.BreakGlassAdmin:
        events = _generate_break_glass_admin(actor_id, config, rng, horizon_seconds)
    else:
        raise ValueError(f"Unknown archetype kind: {kind}")

    # Ensure time-ordered
    events.sort(key=lambda e: e.t)
    return events


# =====================================================================
# ARCHETYPE-SPECIFIC GENERATORS
# =====================================================================

def _generate_developer(actor_id: str, config: WorldConfig, rng, horizon_seconds: float) -> List[RawEvent]:
    """
    Developer: cyclic daily loop IDENTITY → COMPUTE → DATA(read) → COMPUTE → logout.
    Near time-reversible at distribution level.
    """
    events = []
    t = 0.0

    # Daily work cycle duration: ~8 hours = 28800 seconds
    work_cycle_duration = 28800.0
    night_sleep_duration = 57600.0  # ~16 hours off per day

    while t < horizon_seconds:
        # Each day: login, compute, data read, compute, logout
        cycle_start = t

        # IDENTITY → COMPUTE (login, ~1-5 min)
        t += rng.lognormal(mean=4, sigma=0.8)  # ~55-60 seconds mean
        events.append(RawEvent(
            t=t, actor_id=actor_id, src_resource=f"{actor_id}_term",
            dst_resource=f"compute_{rng.integers(0, 5)}", action_type=rng.choice(config.action_vocab),
            zone_src="IDENTITY", zone_dst="COMPUTE", archetype="Developer",
            is_attack=False, attack_type=None
        ))

        # COMPUTE → DATA (read, ~2-10 min)
        t += rng.lognormal(mean=6, sigma=1.0)
        events.append(RawEvent(
            t=t, actor_id=actor_id, src_resource=f"compute_{rng.integers(0, 5)}",
            dst_resource=f"data_{rng.integers(0, 10)}", action_type="read",
            zone_src="COMPUTE", zone_dst="DATA", archetype="Developer",
            is_attack=False, attack_type=None
        ))

        # DATA → COMPUTE (return, ~1-5 min)
        t += rng.lognormal(mean=5, sigma=0.8)
        events.append(RawEvent(
            t=t, actor_id=actor_id, src_resource=f"data_{rng.integers(0, 10)}",
            dst_resource=f"compute_{rng.integers(0, 5)}", action_type="read",
            zone_src="DATA", zone_dst="COMPUTE", archetype="Developer",
            is_attack=False, attack_type=None
        ))

        # COMPUTE → logout (back to IDENTITY, ~500-2000s)
        t += rng.lognormal(mean=5, sigma=0.9)
        events.append(RawEvent(
            t=t, actor_id=actor_id, src_resource=f"compute_{rng.integers(0, 5)}",
            dst_resource=f"{actor_id}_term", action_type="auth",
            zone_src="COMPUTE", zone_dst="IDENTITY", archetype="Developer",
            is_attack=False, attack_type=None
        ))

        # Night sleep + jitter
        t += night_sleep_duration + rng.normal(0, 3600)  # ±1h jitter
        t = max(t, cycle_start + work_cycle_duration + night_sleep_duration)  # enforce minimum

    return events


def _generate_data_analyst(actor_id: str, config: WorldConfig, rng, horizon_seconds: float) -> List[RawEvent]:
    """
    DataAnalyst: IDENTITY → DATA(read-heavy) → COMPUTE; occasional SECRET access.
    Cyclic with high DATA preference.
    """
    events = []
    t = 0.0

    work_cycle_duration = 28800.0  # 8 hours
    night_sleep_duration = 57600.0  # 16 hours

    while t < horizon_seconds:
        cycle_start = t

        # IDENTITY → DATA (login to data, frequent)
        t += rng.lognormal(mean=4, sigma=0.8)
        events.append(RawEvent(
            t=t, actor_id=actor_id, src_resource=f"{actor_id}_term",
            dst_resource=f"data_{rng.integers(0, 15)}", action_type="read",
            zone_src="IDENTITY", zone_dst="DATA", archetype="DataAnalyst",
            is_attack=False, attack_type=None
        ))

        # Multiple DATA reads (60% chance each cycle)
        for _ in range(rng.poisson(2)):
            t += rng.lognormal(mean=6, sigma=1.2)
            if t < horizon_seconds:
                events.append(RawEvent(
                    t=t, actor_id=actor_id, src_resource=f"data_{rng.integers(0, 15)}",
                    dst_resource=f"data_{rng.integers(0, 15)}", action_type="read",
                    zone_src="DATA", zone_dst="DATA", archetype="DataAnalyst",
                    is_attack=False, attack_type=None
                ))

        # Occasional SECRET access (10% chance per cycle, for connection credentials)
        if rng.random() < 0.1:
            t += rng.lognormal(mean=5, sigma=0.9)
            events.append(RawEvent(
                t=t, actor_id=actor_id, src_resource=f"data_{rng.integers(0, 15)}",
                dst_resource=f"secret_{rng.integers(0, 3)}", action_type="read",
                zone_src="DATA", zone_dst="SECRET", archetype="DataAnalyst",
                is_attack=False, attack_type=None
            ))
            # Back from SECRET
            t += rng.lognormal(mean=5, sigma=0.8)
            events.append(RawEvent(
                t=t, actor_id=actor_id, src_resource=f"secret_{rng.integers(0, 3)}",
                dst_resource=f"data_{rng.integers(0, 15)}", action_type="read",
                zone_src="SECRET", zone_dst="DATA", archetype="DataAnalyst",
                is_attack=False, attack_type=None
            ))

        # DATA → COMPUTE (analysis, 30% chance)
        if rng.random() < 0.3:
            t += rng.lognormal(mean=6, sigma=1.0)
            events.append(RawEvent(
                t=t, actor_id=actor_id, src_resource=f"data_{rng.integers(0, 15)}",
                dst_resource=f"compute_{rng.integers(5, 10)}", action_type="invoke",
                zone_src="DATA", zone_dst="COMPUTE", archetype="DataAnalyst",
                is_attack=False, attack_type=None
            ))

        # Logout
        t += rng.lognormal(mean=5, sigma=0.8)
        events.append(RawEvent(
            t=t, actor_id=actor_id, src_resource=f"compute_{rng.integers(5, 10) if rng.random() < 0.3 else rng.integers(0, 15)}",
            dst_resource=f"{actor_id}_term", action_type="auth",
            zone_src="DATA" if rng.random() < 0.7 else "COMPUTE", zone_dst="IDENTITY",
            archetype="DataAnalyst", is_attack=False, attack_type=None
        ))

        # Night sleep
        t += night_sleep_duration + rng.normal(0, 3600)
        t = max(t, cycle_start + work_cycle_duration + night_sleep_duration)

    return events


def _generate_cicd_sa(actor_id: str, config: WorldConfig, rng, horizon_seconds: float) -> List[RawEvent]:
    """
    CICDServiceAccount: extremely regular machine loop IDENTITY → SECRET → COMPUTE → DATA(write).
    Poisson-regular, zero randomness in zone sequence.
    """
    events = []
    t = 0.0

    # Poisson inter-event time
    mean_interval = 3600.0 / config.event_rate_lambda if config.event_rate_lambda > 0 else 3600.0

    cycle_stages = [
        ("IDENTITY", "SECRET", "auth"),
        ("SECRET", "COMPUTE", "assume"),
        ("COMPUTE", "DATA", "write"),
        ("DATA", "IDENTITY", "auth"),  # Back to start
    ]

    stage_idx = 0
    while t < horizon_seconds:
        # Poisson inter-event interval
        t += rng.exponential(mean_interval)

        if t >= horizon_seconds:
            break

        zone_src, zone_dst, action = cycle_stages[stage_idx % len(cycle_stages)]

        # Deterministic resource selection per zone
        src_res = f"{zone_src.lower()}_{stage_idx % 3}"
        dst_res = f"{zone_dst.lower()}_{(stage_idx + 1) % 3}"

        events.append(RawEvent(
            t=t, actor_id=actor_id, src_resource=src_res, dst_resource=dst_res,
            action_type=action, zone_src=zone_src, zone_dst=zone_dst,
            archetype="CICDServiceAccount", is_attack=False, attack_type=None
        ))

        stage_idx += 1

    return events


def _generate_etl_sa(actor_id: str, config: WorldConfig, rng, horizon_seconds: float) -> List[RawEvent]:
    """
    ETLPipelineServiceAccount: benign one-way IDENTITY → SECRET → DATA(read) → EXTERNAL(write).
    Fixed schedule (every 4 hours with jitter); zero reverse edges.
    This is deliberately irreversible — tests if detectors falsely equate irreversibility with attack.
    """
    events = []
    t = 0.0

    # Fixed schedule: every 4 hours = 14400 seconds
    schedule_interval = 14400.0

    while t < horizon_seconds:
        # Schedule with jitter
        t += schedule_interval + rng.normal(0, 600)  # ±10 min jitter

        if t >= horizon_seconds:
            break

        cycle_start = t

        # IDENTITY → SECRET (auth, ~10-30s)
        t += rng.exponential(15)
        events.append(RawEvent(
            t=t, actor_id=actor_id, src_resource=f"identity_etl",
            dst_resource=f"secret_0", action_type="auth",
            zone_src="IDENTITY", zone_dst="SECRET", archetype="ETLPipelineServiceAccount",
            is_attack=False, attack_type=None
        ))

        # SECRET → DATA (read credentials, ~5-15s)
        t += rng.exponential(8)
        events.append(RawEvent(
            t=t, actor_id=actor_id, src_resource=f"secret_0",
            dst_resource=f"data_etl", action_type="read",
            zone_src="SECRET", zone_dst="DATA", archetype="ETLPipelineServiceAccount",
            is_attack=False, attack_type=None
        ))

        # DATA → EXTERNAL (write extracted data, ~10-60s)
        t += rng.exponential(25)
        events.append(RawEvent(
            t=t, actor_id=actor_id, src_resource=f"data_etl",
            dst_resource=f"external_sink", action_type="write",
            zone_src="DATA", zone_dst="EXTERNAL", archetype="ETLPipelineServiceAccount",
            is_attack=False, attack_type=None
        ))

        # Back to start for next cycle (offline time)
        t = cycle_start + schedule_interval

    return events


def _generate_backup_sa(actor_id: str, config: WorldConfig, rng, horizon_seconds: float) -> List[RawEvent]:
    """
    BackupLogShippingAccount: benign one-way DATA → LOGGING(write) or DATA → EXTERNAL(write).
    Fixed daily schedule (02:00 UTC with jitter); no IDENTITY access.
    Another deliberately irreversible flow to test detector fairness.
    """
    events = []
    t = 0.0

    # Daily schedule at ~02:00 UTC = 7200 seconds into each 86400-second day
    daily_offset = 7200.0

    day = 0
    while True:
        # Daily run at ~02:00 + jitter
        t = day * 86400 + daily_offset + rng.normal(0, 1800)  # ±30 min jitter

        if t >= horizon_seconds:
            break

        cycle_start = t

        # DATA read (source)
        t += rng.exponential(10)
        events.append(RawEvent(
            t=t, actor_id=actor_id, src_resource=f"data_backup",
            dst_resource=f"data_backup", action_type="read",
            zone_src="DATA", zone_dst="DATA", archetype="BackupLogShippingAccount",
            is_attack=False, attack_type=None
        ))

        # DATA → LOGGING or EXTERNAL (write backup)
        t += rng.exponential(20)
        dest_zone = "LOGGING" if rng.random() < 0.5 else "EXTERNAL"
        events.append(RawEvent(
            t=t, actor_id=actor_id, src_resource=f"data_backup",
            dst_resource=f"{dest_zone.lower()}_archive", action_type="write",
            zone_src="DATA", zone_dst=dest_zone, archetype="BackupLogShippingAccount",
            is_attack=False, attack_type=None
        ))

        day += 1

    return events


def _generate_oncall_sre(actor_id: str, config: WorldConfig, rng, horizon_seconds: float) -> List[RawEvent]:
    """
    OnCallSRE: mostly dormant; during on-call windows, sudden rare access to never-touched resources.
    Canonical Hopper false-positive.
    """
    events = []
    t = 0.0

    # On-call windows: ~1 per week on average
    num_oncall_windows = max(8, int(config.horizon_days / 7))  # At least 8-10 windows for 60-90 days

    for window_idx in range(num_oncall_windows):
        # Random start time within horizon
        window_start = rng.uniform(0, horizon_seconds - 14400)  # Leave space for 4-hour window
        window_duration = rng.uniform(7200, 14400)  # 2-4 hours

        # Generate 8-15 sudden rare accesses per window (more than before)
        num_accesses = rng.integers(8, 16)

        t = window_start
        for _ in range(num_accesses):
            t += rng.exponential(300)  # ~5-min spacing

            if t > window_start + window_duration:
                break

            # Random zone pair (often ADMIN or rare COMPUTE variants)
            zones = list(config.zone_labels) if config.zone_labels else ["ADMIN", "COMPUTE"]
            zone_src = rng.choice(zones)
            zone_dst = rng.choice([z for z in zones if z != zone_src])

            # Deterministic action per zone pair
            action = "invoke" if zone_dst in ["COMPUTE", "ADMIN"] else "read"

            events.append(RawEvent(
                t=t, actor_id=actor_id, src_resource=f"{zone_src.lower()}_sre_{window_idx}",
                dst_resource=f"{zone_dst.lower()}_rare_{rng.integers(0, 100)}",
                action_type=action, zone_src=zone_src, zone_dst=zone_dst,
                archetype="OnCallSRE", is_attack=False, attack_type=None
            ))

    # Occasional low-rate dormant monitoring (1-2 per week)
    num_monitors = max(8, int(config.horizon_days / 7))
    for _ in range(num_monitors):
        t = rng.uniform(0, horizon_seconds)
        events.append(RawEvent(
            t=t, actor_id=actor_id, src_resource=f"sre_term",
            dst_resource=f"monitoring_dashboard", action_type="read",
            zone_src="LOGGING", zone_dst="LOGGING", archetype="OnCallSRE",
            is_attack=False, attack_type=None
        ))

    return events


def _generate_new_hire(actor_id: str, config: WorldConfig, rng, horizon_seconds: float) -> List[RawEvent]:
    """
    NewHire: starts with zero history, explores broadly for first N days (~5), then settles.
    High initial novelty, then transitions to Developer/Analyst pattern.
    """
    events = []
    t = 0.0

    exploration_duration = 5 * 86400  # First 5 days

    # EXPLORATION PHASE: visit all zones, many resources
    while t < min(exploration_duration, horizon_seconds):
        t += rng.exponential(900)  # ~15-min spacing

        if t >= min(exploration_duration, horizon_seconds):
            break

        # Random zone pair (broad exploration)
        zones = list(config.zone_labels) if config.zone_labels else ["IDENTITY", "COMPUTE", "DATA", "SECRET"]
        zone_src = rng.choice(zones)
        zone_dst = rng.choice([z for z in zones if z != zone_src])

        action = rng.choice(config.action_vocab) if config.action_vocab else "read"

        events.append(RawEvent(
            t=t, actor_id=actor_id, src_resource=f"{zone_src.lower()}_nh_{rng.integers(0, 20)}",
            dst_resource=f"{zone_dst.lower()}_nh_{rng.integers(0, 20)}", action_type=action,
            zone_src=zone_src, zone_dst=zone_dst, archetype="NewHire",
            is_attack=False, attack_type=None
        ))

    # SETTLEMENT PHASE: transition to Developer pattern
    t = exploration_duration
    # Reuse developer logic for rest of horizon
    dev_events = _generate_developer(actor_id, config, rng, horizon_seconds - t)
    # Adjust timestamps
    for dev_event in dev_events:
        adjusted = RawEvent(
            t=dev_event.t + t, actor_id=dev_event.actor_id,
            src_resource=dev_event.src_resource, dst_resource=dev_event.dst_resource,
            action_type=dev_event.action_type, zone_src=dev_event.zone_src,
            zone_dst=dev_event.zone_dst, archetype="NewHire",
            is_attack=False, attack_type=None
        )
        if adjusted.t < horizon_seconds:
            events.append(adjusted)

    return events


def _generate_role_change(actor_id: str, config: WorldConfig, rng, horizon_seconds: float) -> List[RawEvent]:
    """
    RoleChange: first half follows one archetype, at midpoint switches to another.
    Old distribution stale; new distribution active.
    """
    events = []

    change_time = horizon_seconds / 2

    # First half: Developer
    dev_events = _generate_developer(actor_id, config, rng, change_time)
    for event in dev_events:
        if event.t < change_time:
            events.append(RawEvent(
                t=event.t, actor_id=event.actor_id, src_resource=event.src_resource,
                dst_resource=event.dst_resource, action_type=event.action_type,
                zone_src=event.zone_src, zone_dst=event.zone_dst,
                archetype="RoleChange", is_attack=False, attack_type=None
            ))

    # Second half: OnCallSRE (to maximally differ)
    sre_events = _generate_oncall_sre(actor_id, config, rng, horizon_seconds - change_time)
    for event in sre_events:
        adjusted = RawEvent(
            t=event.t + change_time, actor_id=event.actor_id,
            src_resource=event.src_resource, dst_resource=event.dst_resource,
            action_type=event.action_type, zone_src=event.zone_src, zone_dst=event.zone_dst,
            archetype="RoleChange", is_attack=False, attack_type=None
        )
        if adjusted.t < horizon_seconds:
            events.append(adjusted)

    return events


def _generate_break_glass_admin(actor_id: str, config: WorldConfig, rng, horizon_seconds: float) -> List[RawEvent]:
    """
    BreakGlassAdmin: dormant 95% of time; one rare burst per horizon.
    Burst: IDENTITY → ADMIN → SECRET(read) → EXTERNAL(write), then dormant.
    Rare, one-way-looking, benign.
    """
    events = []
    t = 0.0

    # Low-rate dormant monitoring scheduled daily-ish: ~1-2 per day * 60 days = 60-120 events
    num_monitors = max(60, int(config.horizon_days * 1.5))  # ~1.5 per day
    monitor_times = sorted(rng.uniform(0, horizon_seconds, num_monitors))

    for monitor_time in monitor_times:
        events.append(RawEvent(
            t=monitor_time, actor_id=actor_id, src_resource=f"admin_term",
            dst_resource=f"admin_dashboard", action_type="read",
            zone_src="ADMIN", zone_dst="ADMIN", archetype="BreakGlassAdmin",
            is_attack=False, attack_type=None
        ))

    # One rare break-glass burst (mid-horizon ± 20%)
    burst_time = horizon_seconds / 2 + rng.normal(0, horizon_seconds * 0.2)
    burst_time = max(100, min(burst_time, horizon_seconds - 300))

    t = burst_time

    # IDENTITY → ADMIN
    t += rng.exponential(5)
    events.append(RawEvent(
        t=t, actor_id=actor_id, src_resource=f"{actor_id}_term",
        dst_resource=f"admin_console", action_type="auth",
        zone_src="IDENTITY", zone_dst="ADMIN", archetype="BreakGlassAdmin",
        is_attack=False, attack_type=None
    ))

    # ADMIN → SECRET
    t += rng.exponential(10)
    events.append(RawEvent(
        t=t, actor_id=actor_id, src_resource=f"admin_console",
        dst_resource=f"secret_emergency", action_type="read",
        zone_src="ADMIN", zone_dst="SECRET", archetype="BreakGlassAdmin",
        is_attack=False, attack_type=None
    ))

    # SECRET → EXTERNAL (emergency export/notification)
    t += rng.exponential(15)
    events.append(RawEvent(
        t=t, actor_id=actor_id, src_resource=f"secret_emergency",
        dst_resource=f"external_oncall", action_type="write",
        zone_src="SECRET", zone_dst="EXTERNAL", archetype="BreakGlassAdmin",
        is_attack=False, attack_type=None
    ))

    return events
