"""Parameterized attack trajectory generator (Sprint 2).

Produces synthetic CanonicalEvent sequences from a 6-axis parameter space
(speed x spread x zone_path x evasion x closure x objective) for testing
the robustness of physics-informed scoring signals across attack strategies.

Per sprint spec line 85: synthetic events bypass the temporal-identity
correlation pipeline. trigger_ref is set directly on each CanonicalEvent.
This is the right call because Sprint 2 tests scoring robustness, not
ingestion correctness (Sprint 1 scope).

Determinism: same (params, seed) -> same trajectory.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from src.schema import (
    ActionType,
    ActorType,
    CanonicalEvent,
    EventResult,
    ProvenanceLevel,
    ProvenanceSource,
    TargetType,
    TargetZone,
)
from src.synthetic.actors import ActorPopulation
from src.synthetic.provenance import ProvenanceGenerator
from src.synthetic.temporal import TemporalEngine

Speed = Literal["slow", "medium", "fast"]
Spread = Literal["single_actor", "multi_actor"]
ZonePath = Literal["direct", "indirect", "full_chain"]
Evasion = Literal["none", "timing_jitter", "pattern_mimicry", "split_actions"]
Closure = Literal["none", "partial", "full"]
Objective = Literal["secret_access", "key_exfil", "compute_persist", "data_exfil"]

SPEEDS: tuple[Speed, ...] = ("slow", "medium", "fast")
SPREADS: tuple[Spread, ...] = ("single_actor", "multi_actor")
ZONE_PATHS: tuple[ZonePath, ...] = ("direct", "indirect", "full_chain")
EVASIONS: tuple[Evasion, ...] = ("none", "timing_jitter", "pattern_mimicry", "split_actions")
CLOSURES: tuple[Closure, ...] = ("none", "partial", "full")
OBJECTIVES: tuple[Objective, ...] = ("secret_access", "key_exfil", "compute_persist", "data_exfil")


@dataclass(frozen=True)
class AttackParams:
    speed: Speed
    spread: Spread
    zone_path: ZonePath
    evasion: Evasion
    closure: Closure
    objective: Objective


@dataclass
class AttackTrajectory:
    events: list[CanonicalEvent]
    params: AttackParams
    seed: int
    expected_zone_path: list[TargetZone]
    expected_signals: list[str]


# Speed -> base interval (seconds between events)
SPEED_INTERVALS: dict[Speed, float] = {
    "slow": 300.0,    # 1 event / 5 min
    "medium": 60.0,   # 1 event / min
    "fast": 12.0,     # 5 events / min
}

# Sampleable (action, target_type) per zone, derived from src/ingest/parser.py ACTION_MAP.
ZONE_ACTION_TABLE: dict[TargetZone, list[tuple[ActionType, TargetType]]] = {
    TargetZone.CONTROL: [
        (ActionType.IAM_SET_POLICY, TargetType.IAM_POLICY),
        (ActionType.SCHEDULER_ADMIN, TargetType.OTHER),
    ],
    TargetZone.IDENTITY: [
        (ActionType.IAM_CREATE_KEY, TargetType.SA_KEY),
        (ActionType.IAM_CREATE_SA, TargetType.SERVICE_ACCOUNT),
        (ActionType.IAM_IMPERSONATE, TargetType.SERVICE_ACCOUNT),
    ],
    TargetZone.SECRET: [
        (ActionType.SECRET_ACCESS, TargetType.SECRET),
        (ActionType.KMS_DECRYPT, TargetType.KMS_KEY),
    ],
    TargetZone.DATA: [
        (ActionType.GCS_READ, TargetType.GCS_BUCKET),
        (ActionType.GCS_LIST, TargetType.GCS_BUCKET),
        (ActionType.BQ_JOB_SUBMIT, TargetType.BIGQUERY),
    ],
    TargetZone.EXFIL_RISK: [
        (ActionType.GCS_WRITE, TargetType.EXFIL_RISK_DEST),
    ],
    TargetZone.COMPUTE: [
        (ActionType.COMPUTE_CREATE, TargetType.COMPUTE),
        (ActionType.COMPUTE_METADATA_CHANGE, TargetType.COMPUTE),
    ],
}

# Opening action -> closing action (when closure injection triggers).
# Only IAM_CREATE_KEY has a clean inverse in the ActionType enum.
CLOSURE_PAIRS: dict[ActionType, ActionType] = {
    ActionType.IAM_CREATE_KEY: ActionType.IAM_DELETE_KEY,
}

# Zone-path templates by (zone_path, objective).
ZONE_PATH_TEMPLATES: dict[tuple[ZonePath, Objective], list[TargetZone]] = {
    ("direct", "secret_access"): [TargetZone.IDENTITY, TargetZone.SECRET],
    ("direct", "key_exfil"): [TargetZone.IDENTITY, TargetZone.EXFIL_RISK],
    ("direct", "compute_persist"): [TargetZone.IDENTITY, TargetZone.COMPUTE],
    ("direct", "data_exfil"): [TargetZone.IDENTITY, TargetZone.DATA],
    ("indirect", "secret_access"): [TargetZone.IDENTITY, TargetZone.DATA, TargetZone.SECRET],
    ("indirect", "key_exfil"): [TargetZone.IDENTITY, TargetZone.SECRET, TargetZone.EXFIL_RISK],
    ("indirect", "compute_persist"): [TargetZone.IDENTITY, TargetZone.SECRET, TargetZone.COMPUTE],
    ("indirect", "data_exfil"): [TargetZone.IDENTITY, TargetZone.SECRET, TargetZone.DATA],
    ("full_chain", "secret_access"): [
        TargetZone.CONTROL, TargetZone.IDENTITY, TargetZone.SECRET,
    ],
    ("full_chain", "key_exfil"): [
        TargetZone.CONTROL, TargetZone.IDENTITY, TargetZone.SECRET,
        TargetZone.DATA, TargetZone.EXFIL_RISK,
    ],
    ("full_chain", "compute_persist"): [
        TargetZone.CONTROL, TargetZone.IDENTITY, TargetZone.COMPUTE, TargetZone.SECRET,
    ],
    ("full_chain", "data_exfil"): [
        TargetZone.CONTROL, TargetZone.IDENTITY, TargetZone.SECRET,
        TargetZone.DATA, TargetZone.EXFIL_RISK,
    ],
}


def _floor_to_window(ts: datetime, window_minutes: int = 15) -> datetime:
    minute = (ts.minute // window_minutes) * window_minutes
    return ts.replace(minute=minute, second=0, microsecond=0)


def _zone_path_for(params: AttackParams) -> list[TargetZone]:
    return list(ZONE_PATH_TEMPLATES[(params.zone_path, params.objective)])


def _expected_signals(params: AttackParams, zones: list[TargetZone]) -> list[str]:
    """Predict which scoring signals SHOULD fire on this trajectory.

    Confirmation-bias guard: predict before observing. If the grid run
    contradicts these predictions, that divergence IS the finding.
    """
    sigs: list[str] = []
    # Novelty: synthetic actors have no history -> always fires.
    sigs.append("novelty_score")
    # Bridge: actor crossing zones in the same window. Defeated by split_actions.
    if len(zones) >= 2 and params.evasion != "split_actions":
        sigs.append("bridge_new")
    # Sigma_coarse / delta_f: zone-flux variance, sensitive to fast bursts.
    if params.speed == "fast" and params.evasion != "split_actions":
        sigs.append("sigma_coarse")
        sigs.append("delta_f")
    # Invariants: IAM_CREATE_KEY/SET_POLICY/IMPERSONATE all trigger inv signals.
    if TargetZone.IDENTITY in zones or TargetZone.CONTROL in zones:
        sigs.append("inv_score")
    # Closure: opens without matching close.
    if params.closure in ("none", "partial") and TargetZone.IDENTITY in zones:
        sigs.append("closure_gap")
        if params.objective == "key_exfil":
            sigs.append("orphaned_priv")
    return sigs


def _resolve_actors(params: AttackParams, seed: int) -> list[str]:
    """Return the actor IDs to cycle through for trajectory steps.

    single_actor -> [one actor]; multi_actor -> [2-4 distinct actors].
    """
    pop = ActorPopulation(count=10, seed=seed)
    if params.spread == "single_actor":
        return [pop.get_random().email]
    rng = random.Random(seed + 1)  # noqa: S311  # nosec B311
    n_actors = rng.randint(2, 4)
    chosen: list[str] = []
    seen: set[str] = set()
    # Bounded retry loop guarantees termination since pool size > 4.
    for _ in range(n_actors * 4):
        if len(chosen) >= n_actors:
            break
        a = rng.choice(pop.get_all())
        if a.email not in seen:
            chosen.append(a.email)
            seen.add(a.email)
    return chosen


def _resolve_trigger_ref(
    params: AttackParams,
    actor_email: str,
    prov: ProvenanceGenerator,
    rng: random.Random,
) -> tuple[str | None, ProvenanceLevel, ProvenanceSource]:
    """Map evasion strategy to (trigger_ref, provenance_level, provenance_source)."""
    if params.evasion == "pattern_mimicry":
        ref = prov.benign_trigger_ref(actor_email)
        return ref, ProvenanceLevel.WEAK, ProvenanceSource.CLOUD_SCHEDULER
    if rng.random() < 0.5:
        return None, ProvenanceLevel.NONE, ProvenanceSource.UNKNOWN
    return prov.forged_trigger_ref(actor_email), ProvenanceLevel.WEAK, ProvenanceSource.UNKNOWN


def _resolve_timestamps(
    params: AttackParams,
    n_steps: int,
    rng: random.Random,
    base: datetime,
) -> list[datetime]:
    """Generate strictly-ordered timestamps according to speed + evasion."""
    interval = SPEED_INTERVALS[params.speed]
    out: list[datetime] = []
    cur = base + timedelta(seconds=interval)
    for _ in range(n_steps):
        ts = cur
        if params.evasion == "timing_jitter":
            ts = cur + timedelta(seconds=rng.gauss(0, 0.3 * interval))
        out.append(ts)
        if params.evasion == "split_actions":
            # 16 min > 15 min window -> each event lands in a new window.
            cur += timedelta(minutes=16)
        else:
            cur += timedelta(seconds=interval)
    return sorted(out)


def _make_event(
    seed: int,
    idx: int,
    actor_id: str,
    ts: datetime,
    action: ActionType,
    target_type: TargetType,
    target_zone: TargetZone,
    trigger_ref: str | None,
    prov_level: ProvenanceLevel,
    prov_source: ProvenanceSource,
) -> CanonicalEvent:
    target_id = f"projects/synth-project/{action.value.lower()}/synth-{idx:03d}"
    return CanonicalEvent(
        event_id=f"synthetic_{seed:04d}_{idx:03d}",
        ts=ts,
        window_start=_floor_to_window(ts),
        actor_id=actor_id,
        actor_type=ActorType.SERVICE_ACCOUNT,
        action_type=action,
        target_id=target_id,
        target_type=target_type,
        target_zone=target_zone,
        result=EventResult.SUCCESS,
        trigger_ref=trigger_ref,
        provenance_level=prov_level,
        provenance_source=prov_source,
        action_subtype=action.value,
        project_id="synth-project",
        env="rd",
    )


def generate_attack(
    params: AttackParams,
    seed: int,
    *,
    base_time: datetime | None = None,
) -> AttackTrajectory:
    """Generate a synthetic attack trajectory matching the params.

    Returns an AttackTrajectory containing CanonicalEvents (not raw audit
    log dicts). Per sprint spec, these are inserted directly into DuckDB
    via insert_event, bypassing parser/correlation. trigger_ref is set
    directly here.
    """
    rng = random.Random(seed)  # noqa: S311  # nosec B311
    if base_time is None:
        base_time = TemporalEngine.PROJECT_START

    zones = _zone_path_for(params)
    actors = _resolve_actors(params, seed)
    prov = ProvenanceGenerator(seed=seed + 200)
    trig_rng = random.Random(seed + 300)  # noqa: S311  # nosec B311

    # Build the (zone, action, target_type) sequence.
    steps: list[tuple[TargetZone, ActionType, TargetType]] = []
    for z in zones:
        action_options = ZONE_ACTION_TABLE[z]
        action, target_type = action_options[rng.randint(0, len(action_options) - 1)]
        steps.append((z, action, target_type))

    # Inject closure actions where a clean inverse exists.
    closures: list[tuple[TargetZone, ActionType, TargetType]] = []
    for z, action, ttype in steps:
        if action not in CLOSURE_PAIRS:
            continue
        close_action = CLOSURE_PAIRS[action]
        if params.closure == "full":
            closures.append((z, close_action, ttype))
        elif params.closure == "partial" and rng.random() < 0.5:
            closures.append((z, close_action, ttype))
    steps.extend(closures)

    timestamps = _resolve_timestamps(params, len(steps), rng, base_time)

    events: list[CanonicalEvent] = []
    for i, ((z, action, ttype), ts) in enumerate(zip(steps, timestamps, strict=True)):
        actor_id = actors[i % len(actors)]
        trigger_ref, prov_level, prov_source = _resolve_trigger_ref(
            params, actor_id, prov, trig_rng,
        )
        events.append(_make_event(
            seed=seed,
            idx=i,
            actor_id=actor_id,
            ts=ts,
            action=action,
            target_type=ttype,
            target_zone=z,
            trigger_ref=trigger_ref,
            prov_level=prov_level,
            prov_source=prov_source,
        ))

    return AttackTrajectory(
        events=events,
        params=params,
        seed=seed,
        expected_zone_path=zones,
        expected_signals=_expected_signals(params, zones),
    )
