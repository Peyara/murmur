"""
Event anonymization and label stripping.

Converts RawEvent (with labels, zones, archetypes) → AnonymizedEvent (no labels,
hashed IDs, opaque tokens). This is the detector-visible contract (§4.2).

Anonymization process:
1. Hash actor IDs using salted HMAC (deterministic per seed).
2. Hash resource IDs using salted HMAC (deterministic per seed).
3. Map action types to opaque tokens (deterministic per seed, e.g., 'auth' → 'T001').
4. Jitter timestamps uniformly [t - jitter_window, t + jitter_window] (deterministic per seed).
5. Strip zone_src, zone_dst, archetype, is_attack, attack_type fields.

The mapping (salt, actor_hashes, resource_hashes, action_tokens, jitter_amounts)
is returned separately, kept evaluator-side only, NEVER serialized or shown to detectors.

---

DETERMINISM:
Given the same seed, the anonymization must be byte-identical. Hash functions,
jitter seeds, action-token mapping — all derived from the world's seed.

---

FROZEN STUB SIGNATURE (do not modify):
"""

from typing import Tuple, List, Dict
import hashlib
import hmac
import numpy as np

from .model import RawEvent, AnonymizedEvent, AnonymizedMapping


def anonymize(
    raw_events: List[RawEvent],
    seed: int,
    jitter_window: float = 30.0,  # seconds; jitter events by ±30s deterministically
) -> Tuple[List[AnonymizedEvent], AnonymizedMapping]:
    """
    Anonymize a list of RawEvents, stripping labels and hashing identifiers.

    Converts each RawEvent (with zones, archetypes, attack labels, unhashed IDs)
    into an AnonymizedEvent (no labels, hashed IDs, opaque tokens).

    The function:
    - Generates a deterministic salt from seed
    - Creates HMAC-SHA256 hashes for actor IDs and resource IDs
    - Maps action types to opaque tokens (e.g., 'auth' → 'T001')
    - Jitters timestamps uniformly [t - jitter_window, t + jitter_window]
    - Strips zone_src, zone_dst, archetype, is_attack, attack_type
    - Returns anonymized events + the mapping (evaluator-side only)

    Args:
        raw_events: list of RawEvent objects (unhashed, with labels).
        seed: random seed for deterministic anonymization.
        jitter_window: timestamp jitter magnitude (±seconds, default 30).

    Returns:
        Tuple (anonymized_events, anonymized_mapping) where:
        - anonymized_events: list of AnonymizedEvent (detector-visible)
        - anonymized_mapping: AnonymizedMapping with salt, hashes, tokens, jitter
          (evaluator-side only; NEVER shown to detectors)

    Raises:
        ValueError: if raw_events is malformed or seed is invalid.
        NotImplementedError: (stub; to be implemented in Phase 2)

    ---

    IMPLEMENTATION CHECKLIST (for Phase 2 implementer):

    1. SALT GENERATION:
       - Derive salt deterministically from seed (e.g., SHA256(str(seed)) truncated to 16 bytes).
       - Use salt as HMAC key for all subsequent hashes.

    2. ACTOR ID HASHING:
       - For each unique actor_id in raw_events:
         * Compute hash = HMAC_SHA256(salt, actor_id).hexdigest()[:16]
         * Store mapping actor_id → hash in actor_hashes dict
       - All events with same unhashed actor_id map to same hash.

    3. RESOURCE ID HASHING:
       - For each unique (src_resource, dst_resource) pair in raw_events:
         * Compute hash_src = HMAC_SHA256(salt, src_resource).hexdigest()[:16]
         * Compute hash_dst = HMAC_SHA256(salt, dst_resource).hexdigest()[:16]
         * Store mappings resource_id → hash in resource_hashes dict
       - All edges with same unhashed resource IDs map to same hash.

    4. ACTION TYPE TOKENIZATION:
       - Collect all unique action_types from raw_events.
       - Sort alphabetically for determinism.
       - Assign opaque tokens: 'T001', 'T002', ..., 'TN' (N = number of unique actions).
       - Store mapping action_type → token in action_tokens dict.
       - Example: 'auth' → 'T001', 'grant' → 'T002', etc.

    5. TIMESTAMP JITTERING:
       - For each event, derive jitter amount deterministically:
         * rng = numpy.random.default_rng(seed + hash(event.actor_id + event.t))
         * jitter_amount = rng.uniform(-jitter_window, jitter_window)
       - Apply to timestamp: t_jittered = t + jitter_amount
       - Ensure jittered timestamp is non-negative and within plausible range.
       - Store jitter_amounts mapping {raw_t: jitter_applied} for audit purposes.

    6. LABEL STRIPPING:
       - NEVER include zone_src, zone_dst, archetype, is_attack, attack_type
         in the AnonymizedEvent
       - VERIFY that no zone name appears in any field of AnonymizedEvent
       - VERIFY that no archetype name appears in any field of AnonymizedEvent

    7. EVENT ANONYMIZATION LOOP:
       for raw_event in raw_events:
           t_jittered = raw_event.t + compute_jitter(seed, raw_event)
           actor_hash = actor_hashes[raw_event.actor_id]
           src_hash = resource_hashes[raw_event.src_resource]
           dst_hash = resource_hashes[raw_event.dst_resource]
           action_token = action_tokens[raw_event.action_type]

           anon_event = AnonymizedEvent(
               t=t_jittered,
               actor=actor_hash,
               src=src_hash,
               dst=dst_hash,
               action=action_token,
           )
           anonymized_events.append(anon_event)

    8. ORDERING:
       - AnonymizedEvents should be in time order (jittered times).
       - If jitter causes reordering, re-sort by t.

    9. DETERMINISM:
       - Call twice with same raw_events and seed, must get identical hashes, tokens, jitter.
       - No global RNG state; each call self-contained.

    10. COMPATIBILITY WITH TRAJECTORY:
        - AnonymizedEvent must be consumable by Trajectory.from_edge_multiset()
          or similar (via (src, dst, action) tuple extraction).
        - Ensure (actor, src, dst, action) are all strings (hashed/tokens are strings).

    11. TESTING:
        - Determinism: call twice, verify identical output
        - No label leakage: grep output for zone names, archetype names, "attack", "exfil", etc.
          (covered by separate grep_leak_check.py)
        - Hash stability: hashing same resource twice must yield same hash
        - Token stability: mapping same action twice must yield same token

    12. AUDIT HOOK:
        - Return AnonymizedMapping.jitter_amounts for fairness audit to verify timestamps
          are not systematically biased (no attacks systematically start on integer hours, etc.)

    ---

    POST-ANONYMIZATION INVARIANT (for evaluator verification):
    For any AnonymizedEvent e:
    - e.actor, e.src, e.dst: all from the hashing dictionaries (stable, opaque)
    - e.action: from action_tokens dictionary (opaque token, not semantic)
    - e.t: original timestamp ± jitter (no attack-specific artifacts)
    - No other fields present
    - Zone/archetype/is_attack/attack_type: absent (no way for detector to recover)

    """
    if not raw_events:
        raise ValueError("raw_events cannot be empty")

    # Step 1: SALT GENERATION
    # Derive salt from seed using SHA256; use first 32 hex chars as HMAC key
    salt_str = hashlib.sha256(str(seed).encode()).hexdigest()[:32]
    salt_bytes = salt_str.encode()

    # Step 2: ACTOR ID HASHING
    actor_hashes: Dict[str, str] = {}
    for event in raw_events:
        if event.actor_id not in actor_hashes:
            h = hmac.new(salt_bytes, event.actor_id.encode(), hashlib.sha256)
            actor_hashes[event.actor_id] = h.hexdigest()[:16]

    # Step 3: RESOURCE ID HASHING
    resource_hashes: Dict[str, str] = {}
    for event in raw_events:
        if event.src_resource not in resource_hashes:
            h = hmac.new(salt_bytes, event.src_resource.encode(), hashlib.sha256)
            resource_hashes[event.src_resource] = h.hexdigest()[:16]
        if event.dst_resource not in resource_hashes:
            h = hmac.new(salt_bytes, event.dst_resource.encode(), hashlib.sha256)
            resource_hashes[event.dst_resource] = h.hexdigest()[:16]

    # Step 4: ACTION TYPE TOKENIZATION
    unique_actions = sorted(set(event.action_type for event in raw_events))
    action_tokens: Dict[str, str] = {
        action: f"T{i+1:03d}" for i, action in enumerate(unique_actions)
    }

    # Step 5: TIMESTAMP JITTERING (deterministic per event)
    jitter_amounts: Dict[float, float] = {}

    def compute_jitter(raw_event: RawEvent) -> float:
        """Deterministically compute jitter for an event based on seed and event identity."""
        # Combine seed with a hash of the event's actor+time for uniqueness
        event_hash = hash(raw_event.actor_id + str(raw_event.t)) & 0x7fffffff
        jitter_seed = seed + event_hash
        rng = np.random.default_rng(jitter_seed)
        jitter = rng.uniform(-jitter_window, jitter_window)
        return float(jitter)

    # Step 6 & 7: EVENT ANONYMIZATION LOOP
    anonymized_events: List[AnonymizedEvent] = []
    for raw_event in raw_events:
        jitter = compute_jitter(raw_event)
        t_jittered = raw_event.t + jitter

        anon_event = AnonymizedEvent(
            t=t_jittered,
            actor=actor_hashes[raw_event.actor_id],
            src=resource_hashes[raw_event.src_resource],
            dst=resource_hashes[raw_event.dst_resource],
            action=action_tokens[raw_event.action_type],
        )
        anonymized_events.append(anon_event)
        jitter_amounts[raw_event.t] = jitter

    # Step 8: ORDERING
    # Re-sort by jittered timestamp to maintain time-ordered property
    anonymized_events.sort(key=lambda e: e.t)

    # Create AnonymizedMapping (evaluator-side only)
    anonymized_mapping = AnonymizedMapping(
        salt=salt_str,
        actor_hashes=actor_hashes,
        resource_hashes=resource_hashes,
        action_tokens=action_tokens,
        jitter_amounts=jitter_amounts,
    )

    return anonymized_events, anonymized_mapping


def extract_actor_trajectories(
    anonymized_events: List[AnonymizedEvent],
) -> Dict[str, 'Trajectory']:
    """
    Extract per-actor trajectories from anonymized events.

    Groups events by actor and constructs Trajectory objects compatible with
    the existing bakeoff/common/trajectory.py type.

    Args:
        anonymized_events: list of AnonymizedEvent (already sorted by time).

    Returns:
        Dict mapping actor_hash -> Trajectory object.

    Raises:
        ValueError: if any actor's events are not time-ordered.
    """
    from ..common.trajectory import Trajectory, Transition

    actor_events: Dict[str, List[AnonymizedEvent]] = {}
    for event in anonymized_events:
        if event.actor not in actor_events:
            actor_events[event.actor] = []
        actor_events[event.actor].append(event)

    trajectories: Dict[str, Trajectory] = {}
    for actor_hash, events in actor_events.items():
        # Events should already be sorted by time
        transitions = [
            Transition(t=e.t, actor=e.actor, src=e.src, dst=e.dst, action=e.action)
            for e in events
        ]
        trajectories[actor_hash] = Trajectory(transitions)

    return trajectories
