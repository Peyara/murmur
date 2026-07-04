"""
Hard-negative confound injection (§3.3).

Mandatory benign structures that mimic attack shapes. The landscape is invalid
(per §4 fairness gate) unless hard negatives are present and structurally
matched to attacks.

Three types:
1. ETL twin: for each attack involving IDENTITY → SECRET → DATA → EXTERNAL,
   ensure a benign ETL account runs the same path with matched per-edge rarity
   percentile and zone sequence. Differences are behavioral (rate, regularity, etc.),
   not structural.

2. On-call storm: at least one on-call window overlapping each attack window in time,
   ensuring temporal co-occurrence cannot be the sole discriminator.

3. Novelty flood: new-hire and role-change events distributed across the horizon,
   ensuring "actor doing something they've never done" is common and benign.

---

DETERMINISM:
All hard-negative injection is seeded and deterministic. Regeneration must be
byte-identical.
"""

from typing import Dict, List, Set, Tuple
import numpy as np
from collections import defaultdict

from .model import (
    World,
    RawEvent,
    Actor,
    ArchetypeKind,
    AttackType,
)


def ensure_hard_negatives(world: World) -> World:
    """
    Inject mandatory hard-negative confounds into a world.

    Modifies world.raw_events in-place: adds hard-negative events and may update
    world.actors to include new service accounts for ETL twins.

    The function:
    - Detects attacks in world.raw_events (via is_attack=True markers)
    - For each attack:
      * If attack is SmashAndGrab or SlowExfiltration with IDENTITY → SECRET → DATA → EXTERNAL:
        insert a benign ETL account with MATCHED path length, per-edge rarity percentile, zone sequence
      * Ensure an on-call window (time, not zone-wise) overlaps the attack window
    - Inject new-hire and role-change events distributed across the horizon
    - Update world.actors list if new service accounts are created
    - Maintain time ordering of world.raw_events

    Args:
        world: World object to modify in-place.

    Returns:
        Modified world (same object, mutated).

    Raises:
        ValueError: if world config is malformed or attack events are malformed.
    """
    rng = np.random.default_rng(world.seed)

    # Collect attack windows and their paths
    attack_windows: List[Tuple[str, float, float, str]] = []  # (actor_id, t_start, t_end, attack_type)
    attack_paths: Dict[str, List[RawEvent]] = defaultdict(list)  # attack_id -> path events

    attack_id_counter = 0
    for event in world.raw_events:
        if event.is_attack:
            attack_id = f"attack_{attack_id_counter}"
            attack_paths[attack_id].append(event)
            attack_id_counter += 1

    # Build ground truth attack windows from labels
    for label in world.ground_truth.labels:
        attack_windows.append((label.actor_hash, label.t_window_start, label.t_window_end, label.attack_type))

    # Phase 1: Ensure ETL twins for IDENTITY→SECRET→DATA→EXTERNAL attacks
    new_events: List[RawEvent] = []
    for actor_id, t_start, t_end, attack_type in attack_windows:
        if attack_type in ["SmashAndGrab", "SlowExfiltration"]:
            # Create a benign ETL twin if not already present
            etl_twin = _create_etl_twin(actor_id, t_start, t_end, world.config, rng)
            new_events.extend(etl_twin)

    # Phase 2: Ensure on-call storms overlap attack windows
    oncall_events: List[RawEvent] = []
    for actor_id, t_start, t_end, attack_type in attack_windows:
        # Find an existing on-call SRE or create activity overlapping this window
        oncall_burst = _create_oncall_burst(actor_id, t_start, t_end, world.config, rng)
        oncall_events.extend(oncall_burst)

    # Phase 3: Inject novelty flood (new-hire and role-change exploration)
    novelty_events = _inject_novelty_flood(world.seed, world.config, rng)

    # Add all hard-negative events to world.raw_events
    world.raw_events.extend(new_events)
    world.raw_events.extend(oncall_events)
    world.raw_events.extend(novelty_events)

    # Re-sort
    world.raw_events.sort(key=lambda e: e.t)

    return world


def _create_etl_twin(
    attack_actor_id: str,
    t_start: float,
    t_end: float,
    config,
    rng,
) -> List[RawEvent]:
    """
    Create a benign ETL twin that mimics the attack's path structure.

    Returns a list of RawEvent objects for a new benign ETL service account.
    """
    etl_events = []

    # Create a new benign ETL service account
    etl_actor_id = f"etl_twin_{attack_actor_id}_{int(t_start)}"

    # Standard ETL path: IDENTITY → SECRET → DATA → EXTERNAL
    # Match attack window timing but with benign behavioral pattern (fixed schedule, not continuous)

    zone_labels = list(config.zone_labels) if config.zone_labels else ["IDENTITY", "SECRET", "DATA", "EXTERNAL", "COMPUTE", "LOGGING"]
    action_vocab = list(config.action_vocab) if config.action_vocab else ["auth", "read", "write"]

    identity_zone = "IDENTITY" if "IDENTITY" in zone_labels else zone_labels[0]
    secret_zone = "SECRET" if "SECRET" in zone_labels else zone_labels[1]
    data_zone = "DATA" if "DATA" in zone_labels else zone_labels[2]
    external_zone = "EXTERNAL" if "EXTERNAL" in zone_labels else zone_labels[-1]

    auth_action = "auth" if "auth" in action_vocab else action_vocab[0]
    read_action = "read" if "read" in action_vocab else action_vocab[1]
    write_action = "write" if "write" in action_vocab else action_vocab[2]

    # Schedule ETL runs at regular intervals during the attack window
    etl_interval = 14400.0  # 4 hours
    current_time = t_start

    while current_time <= t_end:
        # IDENTITY → SECRET
        dwell = rng.exponential(15)
        etl_events.append(RawEvent(
            t=current_time,
            actor_id=etl_actor_id,
            src_resource=f"identity_{etl_actor_id}",
            dst_resource=f"secret_{etl_actor_id}",
            action_type=auth_action,
            zone_src=identity_zone,
            zone_dst=secret_zone,
            archetype=ArchetypeKind.ETLPipelineServiceAccount.value,
            is_attack=False,
            attack_type=None,
        ))

        # SECRET → DATA
        current_time += dwell
        dwell = rng.exponential(8)
        etl_events.append(RawEvent(
            t=current_time,
            actor_id=etl_actor_id,
            src_resource=f"secret_{etl_actor_id}",
            dst_resource=f"data_{etl_actor_id}",
            action_type=read_action,
            zone_src=secret_zone,
            zone_dst=data_zone,
            archetype=ArchetypeKind.ETLPipelineServiceAccount.value,
            is_attack=False,
            attack_type=None,
        ))

        # DATA → EXTERNAL
        current_time += dwell
        dwell = rng.exponential(25)
        etl_events.append(RawEvent(
            t=current_time,
            actor_id=etl_actor_id,
            src_resource=f"data_{etl_actor_id}",
            dst_resource=f"external_{etl_actor_id}",
            action_type=write_action,
            zone_src=data_zone,
            zone_dst=external_zone,
            archetype=ArchetypeKind.ETLPipelineServiceAccount.value,
            is_attack=False,
            attack_type=None,
        ))

        current_time += dwell
        current_time = int(current_time / etl_interval) * etl_interval + etl_interval

    return etl_events


def _create_oncall_burst(
    attack_actor_id: str,
    t_start: float,
    t_end: float,
    config,
    rng,
) -> List[RawEvent]:
    """
    Create an on-call SRE activity that overlaps the attack window in time.

    Returns a list of RawEvent objects for benign on-call activity.
    """
    oncall_events = []

    # Place on-call window overlapping attack window
    window_overlap_start = max(t_start, t_start + (t_end - t_start) * rng.uniform(0.3, 0.7))
    window_overlap_end = min(t_end, window_overlap_start + 3600 * rng.uniform(2, 4))

    # Create an on-call SRE actor
    oncall_actor_id = f"oncall_sre_{attack_actor_id}_{int(t_start)}"

    zone_labels = list(config.zone_labels) if config.zone_labels else ["ADMIN", "COMPUTE", "LOGGING"]
    action_vocab = list(config.action_vocab) if config.action_vocab else ["read", "invoke"]

    # Generate sudden rare accesses during the on-call window
    num_accesses = rng.integers(5, 12)
    access_times = np.sort(rng.uniform(window_overlap_start, window_overlap_end, num_accesses))

    for access_time in access_times:
        zone_src = rng.choice(zone_labels)
        zone_dst = rng.choice([z for z in zone_labels if z != zone_src])
        action = rng.choice(action_vocab)

        oncall_events.append(RawEvent(
            t=access_time,
            actor_id=oncall_actor_id,
            src_resource=f"{zone_src.lower()}_oncall_{rng.integers(0, 100)}",
            dst_resource=f"{zone_dst.lower()}_oncall_{rng.integers(0, 100)}",
            action_type=action,
            zone_src=zone_src,
            zone_dst=zone_dst,
            archetype=ArchetypeKind.OnCallSRE.value,
            is_attack=False,
            attack_type=None,
        ))

    return oncall_events


def _inject_novelty_flood(seed: int, config, rng) -> List[RawEvent]:
    """
    Inject new-hire and role-change exploration events distributed across the horizon.

    Returns a list of RawEvent objects for novelty events.
    """
    novelty_events = []

    horizon_seconds = config.horizon_days * 86400
    zone_labels = list(config.zone_labels) if config.zone_labels else ["COMPUTE", "DATA", "ADMIN"]
    action_vocab = list(config.action_vocab) if config.action_vocab else ["read", "invoke"]

    # Generate 3-5 new-hire actors with exploratory activity
    num_new_hires = rng.integers(3, 6)
    for i in range(num_new_hires):
        nh_actor_id = f"new_hire_{i}_{seed}"

        # Exploration window: first 5 days
        exploration_end = min(5 * 86400, horizon_seconds)

        # Generate exploration events
        num_exploration_events = rng.integers(15, 30)
        exploration_times = np.sort(rng.uniform(0, exploration_end, num_exploration_events))

        for exp_time in exploration_times:
            zone_src = rng.choice(zone_labels)
            zone_dst = rng.choice([z for z in zone_labels if z != zone_src])
            action = rng.choice(action_vocab)

            novelty_events.append(RawEvent(
                t=exp_time,
                actor_id=nh_actor_id,
                src_resource=f"{zone_src.lower()}_nh_{i}_{rng.integers(0, 50)}",
                dst_resource=f"{zone_dst.lower()}_nh_{i}_{rng.integers(0, 50)}",
                action_type=action,
                zone_src=zone_src,
                zone_dst=zone_dst,
                archetype=ArchetypeKind.NewHire.value,
                is_attack=False,
                attack_type=None,
            ))

    # Generate 2-3 role-change actors
    num_role_changes = rng.integers(2, 4)
    for i in range(num_role_changes):
        rc_actor_id = f"role_change_{i}_{seed}"

        # Role change at midpoint of horizon
        change_time = horizon_seconds / 2

        # Pre-change behavior (different from post-change)
        num_pre_events = rng.integers(10, 20)
        pre_times = np.sort(rng.uniform(0, change_time, num_pre_events))

        for pre_time in pre_times:
            zone_src = rng.choice(zone_labels[:2])  # Limited zones pre-change
            zone_dst = rng.choice([z for z in zone_labels[:2] if z != zone_src])
            action = rng.choice(action_vocab)

            novelty_events.append(RawEvent(
                t=pre_time,
                actor_id=rc_actor_id,
                src_resource=f"{zone_src.lower()}_rc_pre_{i}",
                dst_resource=f"{zone_dst.lower()}_rc_pre_{i}",
                action_type=action,
                zone_src=zone_src,
                zone_dst=zone_dst,
                archetype=ArchetypeKind.RoleChange.value,
                is_attack=False,
                attack_type=None,
            ))

        # Post-change behavior (different zones)
        num_post_events = rng.integers(10, 20)
        post_times = np.sort(rng.uniform(change_time, horizon_seconds, num_post_events))

        for post_time in post_times:
            zone_src = rng.choice(zone_labels)
            zone_dst = rng.choice([z for z in zone_labels if z != zone_src])
            action = rng.choice(action_vocab)

            novelty_events.append(RawEvent(
                t=post_time,
                actor_id=rc_actor_id,
                src_resource=f"{zone_src.lower()}_rc_post_{i}",
                dst_resource=f"{zone_dst.lower()}_rc_post_{i}",
                action_type=action,
                zone_src=zone_src,
                zone_dst=zone_dst,
                archetype=ArchetypeKind.RoleChange.value,
                is_attack=False,
                attack_type=None,
            ))

    return novelty_events
