"""
Attack trajectory injection.

Five attack types (§3.2) are overlaid onto compromised actors. Each attack is an
overlay on an existing benign actor (or rarely, a minted service account), never
a special node type.

Injection protocol:
- Per attack-world, compromise 1–3 actors, chosen uniformly from eligible archetypes.
- Attack onset uniformly in the middle third of horizon (so pre-attack history exists).
- Ground-truth labels: (actor, time-window) pairs, generator-side only.

All functions are deterministic per (attack_type, victim_actor, config, seed).

---

KEY DESIGN NOTES:

1. CREDENTIAL-THEFT LATERAL:
   Compromised developer begins traversing IDENTITY → COMPUTE → COMPUTE' → SECRET → DATA,
   using assume/grant action mid-path (credential-switch analog), reaching resources
   outside the causal actor's history. Tests Hopper-style gate (rare edge + credential switch).

2. SLOW EXFILTRATION:
   Compromised analyst adds low-rate DATA → EXTERNAL drip over weeks, keeping per-day
   rarity minimal. Tests whether trajectory-level asymmetry catches what per-edge rarity cannot.

3. SMASH-AND-GRAB:
   Fast one-session IDENTITY → SECRET → DATA → EXTERNAL burst. Easy anchor; every detector
   should catch this. Exempt from §4.3 cheat-detector fairness gate (it is meant to be
   aggregate-visible).

4. LIVING-OFF-THE-LAND (crown-jewel test, §3.2#4):
   Attack uses ONLY edges that exist benignly in the actor's own history, altering only
   sequencing/direction/rate. Example: ETL account's legitimate path (IDENTITY → SECRET →
   DATA → EXTERNAL) run in novel order or reversed, terminating in EXTERNAL at 10× volume.
   Per-edge rarity is ZERO signal by construction. If physics has a real edge over rarity+context,
   this is where it must show (per §5.1, via relative asymmetry to actor's own history).

5. SERVICE-ACCOUNT HIJACK:
   CI account (archetype 3) deviates from machine-regular loop into SECRET → EXTERNAL.
   Tests regularity-break detection. Compact; few transitions, but context-destroying.

---

FROZEN STUB SIGNATURE (do not modify):
"""

from typing import Tuple, List
from .model import RawEvent, Actor, WorldConfig, AttackType, ArchetypeKind
import numpy as np
import bisect


def inject_attack(
    attack_type: AttackType,
    victim_actor: Actor,
    world_events: List[RawEvent],
    config: WorldConfig,
    seed: int,
) -> Tuple[List[RawEvent], List[Tuple[str, float, float, str]]]:
    """
    Inject an attack overlay onto a compromised actor's trajectory.

    Modifies the world_events list in-place: inserts attack events into the log,
    updates their is_attack and attack_type fields, and returns ground-truth labels
    for the injected attack.

    The function:
    - Selects an onset time uniformly in the middle third of the horizon
      (attack_onset_phase from config)
    - Generates attack-specific event sequence over a duration (attack_type dependent:
      seconds for smash-and-grab, weeks for slow exfil)
    - Inserts events into world_events maintaining time order
    - Returns ground-truth labels as (actor_hash, t_start, t_end, attack_type_name)

    Args:
        attack_type: AttackType enum (CredentialTheftLateral, SlowExfiltration, ..., ServiceAccountHijack)
        victim_actor: Actor object to compromise (its actor_id will be used)
        world_events: list of RawEvent objects generated so far (will be modified in-place,
                     insertion maintaining time order)
        config: WorldConfig (horizon_days, action_vocab, zone_labels)
        seed: random seed for this attack (deterministic per attack, replayable)

    Returns:
        Tuple (modified_world_events, ground_truth_labels) where:
        - modified_world_events: world_events with attack events inserted
        - ground_truth_labels: list of (actor_id, t_window_start, t_window_end, attack_type_str)
                              (actor_id unhashed; hashing deferred to evaluator)

    Raises:
        ValueError: if attack_type or config is invalid, or victim_actor is ineligible.
        NotImplementedError: (stub; to be implemented in Phase 2)

    ---

    IMPLEMENTATION CHECKLIST (for Phase 2 implementer):

    1. Seed the RNG with seed (use numpy.random.default_rng(seed)).

    2. Validate victim_actor.archetype is eligible for this attack:
       - CredentialTheftLateral: Developer, DataAnalyst (need read access history)
       - SlowExfiltration: DataAnalyst (regular DATA access)
       - SmashAndGrab: any (no prior history required; fast single session)
       - LivingOffTheLand: ETLPipelineServiceAccount, BackupLogShippingAccount (reuse own edges)
       - ServiceAccountHijack: CICDServiceAccount only
       Raise ValueError if ineligible.

    3. Onset timing:
       - Compute t_onset uniformly in middle third of horizon.
         middle_third = (config.horizon_days * 86400 * 1/3, config.horizon_days * 86400 * 2/3)
         t_onset = uniform(middle_third[0], middle_third[1])

    4. For CredentialTheftLateral:
       - Duration: 2–5 hours
       - Path: IDENTITY(assume) → COMPUTE → COMPUTE'(grant) → SECRET → DATA(exfil)
       - Dwell times: 30–120s between transitions
       - COMPUTE' is a resource not in victim_actor's pre-compromise history
       - Traverses assume/grant actions (credential-switch analogs)
       - Mark all events is_attack=True, attack_type='CredentialTheftLateral'
       - Ground-truth window: [t_onset, t_onset + duration]

    5. For SlowExfiltration:
       - Duration: 3–6 weeks
       - Path: DATA(read) → EXTERNAL(write), repeated at low rate (e.g., every 6–12 hours)
       - Per-day event count: 2–4 (sparse)
       - Mark all events is_attack=True, attack_type='SlowExfiltration'
       - Ground-truth window: [t_onset, t_onset + duration]

    6. For SmashAndGrab:
       - Duration: 30–60 seconds
       - Path: IDENTITY → SECRET(read) → DATA(read+write) → EXTERNAL(write)
       - Dwell times: 5–15s between transitions
       - Fast, obvious, aggregate-visible
       - Mark all events is_attack=True, attack_type='SmashAndGrab'
       - Ground-truth window: [t_onset, t_onset + duration]

    7. For LivingOffTheLand (crown-jewel test):
       - Extract victim_actor's benign edge set from pre-compromise events in world_events.
       - Attack path: reorder/reverse/re-rate those edges, ending in EXTERNAL accumulation.
       - Example (ETL account): normally IDENTITY → SECRET → DATA → EXTERNAL.
         LOTL variant: EXTERNAL ← DATA ← SECRET ← IDENTITY (reversed) or interleaved differently.
       - Duration: 2–4 weeks
       - Per-edge rarity: ZERO signal by construction (all edges existed benignly).
       - Mark all events is_attack=True, attack_type='LivingOffTheLand'
       - Ground-truth window: [t_onset, t_onset + duration]

    8. For ServiceAccountHijack:
       - Duration: 1–3 hours
       - Victim: CICDServiceAccount, which normally does IDENTITY → SECRET → COMPUTE → DATA
       - Attack deviation: SECRET → EXTERNAL(write) instead of COMPUTE next
       - 3–8 events (compact)
       - Mark all events is_attack=True, attack_type='ServiceAccountHijack'
       - Ground-truth window: [t_onset, t_onset + duration]

    9. Event insertion:
       - All attack events must have action_type from config.action_vocab.
       - All events must have archetype set to victim_actor.archetype.value.
       - Timestamps must respect world_events time ordering post-insertion (sort by t after insert).

    10. Ground-truth labels:
        - Return list of (actor_id_unhashed, t_start, t_end, attack_type.value)
        - Hashing deferred to anonymize.py; only store unhashed actor_id here.

    11. Determinism:
        - Call twice with same seed, must get identical results.
        - No randomness in edge selection beyond the seeded RNG.

    12. Testing:
        - CredentialTheftLateral: reaches out-of-history resource
        - SlowExfiltration: matches per-day rarity of ETL twin hard-negative
        - SmashAndGrab: single-session, fast
        - LivingOffTheLand: all edges pre-exist benignly; only rate/order differ
        - ServiceAccountHijack: breaks regularity of machine loop

    """
    rng = np.random.default_rng(seed)

    # Validate attack type and archetype eligibility
    _validate_attack_eligibility(attack_type, victim_actor)

    # Compute onset time uniformly in middle third of horizon
    horizon_seconds = config.horizon_days * 86400
    t_min_onset = horizon_seconds * config.attack_onset_phase[0]
    t_max_onset = horizon_seconds * config.attack_onset_phase[1]
    t_onset = rng.uniform(t_min_onset, t_max_onset)

    # Generate attack events based on type
    if attack_type == AttackType.CredentialTheftLateral:
        attack_events, t_end = _credential_theft_lateral(
            victim_actor, world_events, config, t_onset, rng
        )
    elif attack_type == AttackType.SlowExfiltration:
        attack_events, t_end = _slow_exfiltration(
            victim_actor, world_events, config, t_onset, rng
        )
    elif attack_type == AttackType.SmashAndGrab:
        attack_events, t_end = _smash_and_grab(
            victim_actor, world_events, config, t_onset, rng
        )
    elif attack_type == AttackType.LivingOffTheLand:
        attack_events, t_end = _living_off_the_land(
            victim_actor, world_events, config, t_onset, rng
        )
    elif attack_type == AttackType.ServiceAccountHijack:
        attack_events, t_end = _service_account_hijack(
            victim_actor, world_events, config, t_onset, rng
        )
    else:
        raise ValueError(f"Unknown attack type: {attack_type}")

    # Insert attack events into world_events maintaining time order
    world_events.extend(attack_events)
    world_events.sort(key=lambda e: e.t)

    # Create ground-truth label
    ground_truth_labels = [
        (victim_actor.id, t_onset, t_end, attack_type.value)
    ]

    return world_events, ground_truth_labels


def _validate_attack_eligibility(attack_type: AttackType, victim_actor: Actor) -> None:
    """Validate that victim_actor is eligible for this attack type."""
    archetype = victim_actor.archetype

    if attack_type == AttackType.CredentialTheftLateral:
        if archetype not in [ArchetypeKind.Developer, ArchetypeKind.DataAnalyst]:
            raise ValueError(
                f"CredentialTheftLateral requires Developer or DataAnalyst; got {archetype}"
            )
    elif attack_type == AttackType.SlowExfiltration:
        if archetype != ArchetypeKind.DataAnalyst:
            raise ValueError(
                f"SlowExfiltration requires DataAnalyst; got {archetype}"
            )
    elif attack_type == AttackType.SmashAndGrab:
        # Any archetype is eligible
        pass
    elif attack_type == AttackType.LivingOffTheLand:
        if archetype not in [
            ArchetypeKind.ETLPipelineServiceAccount,
            ArchetypeKind.BackupLogShippingAccount,
        ]:
            raise ValueError(
                f"LivingOffTheLand requires ETL or Backup account; got {archetype}"
            )
    elif attack_type == AttackType.ServiceAccountHijack:
        if archetype != ArchetypeKind.CICDServiceAccount:
            raise ValueError(
                f"ServiceAccountHijack requires CICDServiceAccount; got {archetype}"
            )


def _credential_theft_lateral(
    victim_actor: Actor,
    world_events: List[RawEvent],
    config: WorldConfig,
    t_onset: float,
    rng,
) -> Tuple[List[RawEvent], float]:
    """
    Credential-theft lateral movement attack.

    Path: IDENTITY(assume) → COMPUTE → COMPUTE'(grant) → SECRET → DATA
    Duration: 2-5 hours
    Reaches out-of-history resources with credential-switch actions.
    """
    # Duration: 2-5 hours in seconds
    duration = rng.uniform(2 * 3600, 5 * 3600)
    t_end = t_onset + duration

    # Identify victim's historical resource set (pre-compromise)
    victim_resources = set()
    for event in world_events:
        if event.actor_id == victim_actor.id:
            victim_resources.add(event.src_resource)
            victim_resources.add(event.dst_resource)

    # Create new COMPUTE resource not in history
    compute_prime_id = f"compute_lateral_{rng.integers(100000, 999999)}"

    # Build attack path: IDENTITY → COMPUTE → COMPUTE' → SECRET → DATA
    # Use zones from config
    action_vocab = list(config.action_vocab)
    zone_labels = list(config.zone_labels)

    # Find zone indices (or use provided strings)
    identity_zone = "IDENTITY"
    compute_zone = "COMPUTE"
    secret_zone = "SECRET"
    data_zone = "DATA"

    # Ensure these zones exist in config
    if identity_zone not in zone_labels:
        identity_zone = zone_labels[0]  # fallback
    if compute_zone not in zone_labels:
        compute_zone = zone_labels[1]  # fallback
    if secret_zone not in zone_labels:
        secret_zone = zone_labels[2]  # fallback
    if data_zone not in zone_labels:
        data_zone = zone_labels[3]  # fallback

    attack_events = []
    current_time = t_onset

    # Step 1: IDENTITY → COMPUTE (assume action for credential-switch analog)
    assume_action = "assume" if "assume" in action_vocab else action_vocab[0]
    identity_resource = f"identity_{victim_actor.id}"
    compute_resource = f"compute_{victim_actor.id}"

    dwell_time = rng.uniform(30, 120)
    attack_events.append(RawEvent(
        t=current_time,
        actor_id=victim_actor.id,
        src_resource=identity_resource,
        dst_resource=compute_resource,
        action_type=assume_action,
        zone_src=identity_zone,
        zone_dst=compute_zone,
        archetype=victim_actor.archetype.value,
        is_attack=True,
        attack_type=AttackType.CredentialTheftLateral.value,
    ))
    current_time += dwell_time

    # Step 2: COMPUTE → COMPUTE' (transition to new compute resource)
    transition_action = "invoke" if "invoke" in action_vocab else action_vocab[1]
    dwell_time = rng.uniform(30, 120)
    attack_events.append(RawEvent(
        t=current_time,
        actor_id=victim_actor.id,
        src_resource=compute_resource,
        dst_resource=compute_prime_id,
        action_type=transition_action,
        zone_src=compute_zone,
        zone_dst=compute_zone,
        archetype=victim_actor.archetype.value,
        is_attack=True,
        attack_type=AttackType.CredentialTheftLateral.value,
    ))
    current_time += dwell_time

    # Step 3: COMPUTE' → SECRET (grant action for credential-switch)
    grant_action = "grant" if "grant" in action_vocab else action_vocab[2]
    secret_resource = f"secret_{rng.integers(100000, 999999)}"
    dwell_time = rng.uniform(30, 120)
    attack_events.append(RawEvent(
        t=current_time,
        actor_id=victim_actor.id,
        src_resource=compute_prime_id,
        dst_resource=secret_resource,
        action_type=grant_action,
        zone_src=compute_zone,
        zone_dst=secret_zone,
        archetype=victim_actor.archetype.value,
        is_attack=True,
        attack_type=AttackType.CredentialTheftLateral.value,
    ))
    current_time += dwell_time

    # Step 4: SECRET → DATA (exfiltration read)
    read_action = "read" if "read" in action_vocab else action_vocab[3]
    data_resource = f"data_{rng.integers(100000, 999999)}"
    attack_events.append(RawEvent(
        t=current_time,
        actor_id=victim_actor.id,
        src_resource=secret_resource,
        dst_resource=data_resource,
        action_type=read_action,
        zone_src=secret_zone,
        zone_dst=data_zone,
        archetype=victim_actor.archetype.value,
        is_attack=True,
        attack_type=AttackType.CredentialTheftLateral.value,
    ))

    return attack_events, t_end


def _slow_exfiltration(
    victim_actor: Actor,
    world_events: List[RawEvent],
    config: WorldConfig,
    t_onset: float,
    rng,
) -> Tuple[List[RawEvent], float]:
    """
    Slow exfiltration attack.

    Path: DATA(read) → EXTERNAL(write), repeated at low rate
    Duration: 3-6 weeks
    Per-day event count: 2-4 (sparse, low-rate) — counts the DATA→EXTERNAL drip events,
    not the individual read/write pair components.
    """
    # Duration: 3-6 weeks in seconds
    duration = rng.uniform(3 * 7 * 86400, 6 * 7 * 86400)
    t_end = t_onset + duration

    action_vocab = list(config.action_vocab)
    zone_labels = list(config.zone_labels)

    data_zone = "DATA" if "DATA" in zone_labels else zone_labels[0]
    external_zone = "EXTERNAL" if "EXTERNAL" in zone_labels else zone_labels[-1]
    read_action = "read" if "read" in action_vocab else action_vocab[0]
    write_action = "write" if "write" in action_vocab else action_vocab[1]

    attack_events = []

    # Generate exfil drip events at low rate: 2-4 per day on average
    # Each "drip" is a DATA→EXTERNAL pair (2 events)
    num_days = duration / 86400
    drips_per_day = rng.uniform(2, 4)
    num_drips = max(3, int(num_days * drips_per_day))

    # Generate timestamps uniformly distributed over the attack duration
    drip_times = np.sort(rng.uniform(t_onset, t_end, num_drips))

    for i, event_time in enumerate(drip_times):
        # DATA(read) → EXTERNAL(write) drip
        data_resource = f"data_exfil_{i}"
        external_resource = f"external_exfil_{i}"

        # Read from data
        attack_events.append(RawEvent(
            t=event_time,
            actor_id=victim_actor.id,
            src_resource=data_resource,
            dst_resource=data_resource,
            action_type=read_action,
            zone_src=data_zone,
            zone_dst=data_zone,
            archetype=victim_actor.archetype.value,
            is_attack=True,
            attack_type=AttackType.SlowExfiltration.value,
        ))

        # Write to external - small delay after read
        event_time_write = event_time + rng.uniform(1, 10)
        attack_events.append(RawEvent(
            t=event_time_write,
            actor_id=victim_actor.id,
            src_resource=data_resource,
            dst_resource=external_resource,
            action_type=write_action,
            zone_src=data_zone,
            zone_dst=external_zone,
            archetype=victim_actor.archetype.value,
            is_attack=True,
            attack_type=AttackType.SlowExfiltration.value,
        ))

    return attack_events, t_end


def _smash_and_grab(
    victim_actor: Actor,
    world_events: List[RawEvent],
    config: WorldConfig,
    t_onset: float,
    rng,
) -> Tuple[List[RawEvent], float]:
    """
    Smash-and-grab attack: fast single-session burst.

    Path: IDENTITY → SECRET(read) → DATA(read+write) → EXTERNAL(write)
    Duration: 30-60 seconds
    Easy anchor; aggregate-visible.
    """
    # Duration: 30-60 seconds
    duration = rng.uniform(30, 60)
    t_end = t_onset + duration

    action_vocab = list(config.action_vocab)
    zone_labels = list(config.zone_labels)

    identity_zone = "IDENTITY" if "IDENTITY" in zone_labels else zone_labels[0]
    secret_zone = "SECRET" if "SECRET" in zone_labels else zone_labels[1]
    data_zone = "DATA" if "DATA" in zone_labels else zone_labels[2]
    external_zone = "EXTERNAL" if "EXTERNAL" in zone_labels else zone_labels[-1]

    read_action = "read" if "read" in action_vocab else action_vocab[0]
    write_action = "write" if "write" in action_vocab else action_vocab[1]

    attack_events = []
    current_time = t_onset

    # IDENTITY resource
    identity_resource = f"identity_{victim_actor.id}"

    # Step 1: IDENTITY → SECRET (read)
    secret_resource = f"secret_sag_{rng.integers(100000, 999999)}"
    dwell_time = rng.uniform(5, 15)
    attack_events.append(RawEvent(
        t=current_time,
        actor_id=victim_actor.id,
        src_resource=identity_resource,
        dst_resource=secret_resource,
        action_type=read_action,
        zone_src=identity_zone,
        zone_dst=secret_zone,
        archetype=victim_actor.archetype.value,
        is_attack=True,
        attack_type=AttackType.SmashAndGrab.value,
    ))
    current_time += dwell_time

    # Step 2: SECRET → DATA (read)
    data_resource = f"data_sag_{rng.integers(100000, 999999)}"
    dwell_time = rng.uniform(5, 15)
    attack_events.append(RawEvent(
        t=current_time,
        actor_id=victim_actor.id,
        src_resource=secret_resource,
        dst_resource=data_resource,
        action_type=read_action,
        zone_src=secret_zone,
        zone_dst=data_zone,
        archetype=victim_actor.archetype.value,
        is_attack=True,
        attack_type=AttackType.SmashAndGrab.value,
    ))
    current_time += dwell_time

    # Step 3: DATA → DATA (write within DATA zone)
    dwell_time = rng.uniform(5, 15)
    attack_events.append(RawEvent(
        t=current_time,
        actor_id=victim_actor.id,
        src_resource=data_resource,
        dst_resource=data_resource,
        action_type=write_action,
        zone_src=data_zone,
        zone_dst=data_zone,
        archetype=victim_actor.archetype.value,
        is_attack=True,
        attack_type=AttackType.SmashAndGrab.value,
    ))
    current_time += dwell_time

    # Step 4: DATA → EXTERNAL (write exfiltration)
    external_resource = f"external_sag_{rng.integers(100000, 999999)}"
    attack_events.append(RawEvent(
        t=current_time,
        actor_id=victim_actor.id,
        src_resource=data_resource,
        dst_resource=external_resource,
        action_type=write_action,
        zone_src=data_zone,
        zone_dst=external_zone,
        archetype=victim_actor.archetype.value,
        is_attack=True,
        attack_type=AttackType.SmashAndGrab.value,
    ))

    return attack_events, t_end


def _living_off_the_land(
    victim_actor: Actor,
    world_events: List[RawEvent],
    config: WorldConfig,
    t_onset: float,
    rng,
) -> Tuple[List[RawEvent], float]:
    """
    Living-off-the-land attack: crown-jewel test.

    Reuses edges from actor's own benign history, altering only sequencing/rate/destination.
    Per-edge rarity is ZERO signal by construction.
    Duration: 2-4 weeks
    """
    # Duration: 2-4 weeks in seconds
    duration = rng.uniform(2 * 7 * 86400, 4 * 7 * 86400)
    t_end = t_onset + duration

    # Extract victim's benign edge set from world_events
    victim_edges = []
    victim_zones = {}  # resource_id -> zone
    for event in world_events:
        if event.actor_id == victim_actor.id and not event.is_attack:
            edge = (event.src_resource, event.dst_resource, event.action_type)
            victim_edges.append(edge)
            victim_zones[event.src_resource] = event.zone_src
            victim_zones[event.dst_resource] = event.zone_dst

    if not victim_edges:
        # Fallback: generate a simple path using benign ETL pattern
        action_vocab = list(config.action_vocab)
        zone_labels = list(config.zone_labels)
        identity_zone = "IDENTITY" if "IDENTITY" in zone_labels else zone_labels[0]
        secret_zone = "SECRET" if "SECRET" in zone_labels else zone_labels[1]
        data_zone = "DATA" if "DATA" in zone_labels else zone_labels[2]
        external_zone = "EXTERNAL" if "EXTERNAL" in zone_labels else zone_labels[-1]

        read_action = "read" if "read" in action_vocab else action_vocab[0]
        write_action = "write" if "write" in action_vocab else action_vocab[1]

        victim_edges = [
            (f"id_{victim_actor.id}", f"secret_{victim_actor.id}", read_action),
            (f"secret_{victim_actor.id}", f"data_{victim_actor.id}", read_action),
            (f"data_{victim_actor.id}", f"external_{victim_actor.id}", write_action),
        ]
        victim_zones = {
            f"id_{victim_actor.id}": identity_zone,
            f"secret_{victim_actor.id}": secret_zone,
            f"data_{victim_actor.id}": data_zone,
            f"external_{victim_actor.id}": external_zone,
        }

    # Reorder benign edges and amplify rate (e.g., 10x volume)
    # Shuffle the edges and repeat them with increased rate
    shuffled_edges = victim_edges.copy()
    rng.shuffle(shuffled_edges)

    # Repeat edges to increase volume (~10x)
    num_repetitions = max(3, int(10 * len(victim_edges)))
    attack_times = np.sort(rng.uniform(t_onset, t_end, num_repetitions))

    attack_events = []
    for i, event_time in enumerate(attack_times):
        # Pick an edge from the shuffled list (cycling)
        edge_idx = i % len(shuffled_edges)
        src, dst, action = shuffled_edges[edge_idx]

        src_zone = victim_zones.get(src, "DATA")
        dst_zone = victim_zones.get(dst, "EXTERNAL")

        attack_events.append(RawEvent(
            t=event_time,
            actor_id=victim_actor.id,
            src_resource=src,
            dst_resource=dst,
            action_type=action,
            zone_src=src_zone,
            zone_dst=dst_zone,
            archetype=victim_actor.archetype.value,
            is_attack=True,
            attack_type=AttackType.LivingOffTheLand.value,
        ))

    return attack_events, t_end


def _service_account_hijack(
    victim_actor: Actor,
    world_events: List[RawEvent],
    config: WorldConfig,
    t_onset: float,
    rng,
) -> Tuple[List[RawEvent], float]:
    """
    Service-account hijack attack.

    CI account (normally IDENTITY → SECRET → COMPUTE → DATA) deviates to SECRET → EXTERNAL.
    Tests regularity-break detection.
    Duration: 1-3 hours
    Compact: 3-8 events
    """
    # Duration: 1-3 hours in seconds
    duration = rng.uniform(1 * 3600, 3 * 3600)
    t_end = t_onset + duration

    action_vocab = list(config.action_vocab)
    zone_labels = list(config.zone_labels)

    secret_zone = "SECRET" if "SECRET" in zone_labels else zone_labels[0]
    external_zone = "EXTERNAL" if "EXTERNAL" in zone_labels else zone_labels[-1]
    read_action = "read" if "read" in action_vocab else action_vocab[0]
    write_action = "write" if "write" in action_vocab else action_vocab[1]

    attack_events = []
    current_time = t_onset

    # Generate 3-8 SECRET → EXTERNAL events
    num_events = rng.integers(3, 9)

    for i in range(num_events):
        secret_resource = f"secret_hijack_{i}"
        external_resource = f"external_hijack_{i}"

        # Alternate between read and write for variety
        action = read_action if i % 2 == 0 else write_action

        dwell_time = rng.uniform(30, 300) if i == 0 else rng.uniform(5, 30)
        attack_events.append(RawEvent(
            t=current_time,
            actor_id=victim_actor.id,
            src_resource=secret_resource,
            dst_resource=external_resource,
            action_type=action,
            zone_src=secret_zone,
            zone_dst=external_zone,
            archetype=victim_actor.archetype.value,
            is_attack=True,
            attack_type=AttackType.ServiceAccountHijack.value,
        ))
        current_time += dwell_time

    return attack_events, t_end
