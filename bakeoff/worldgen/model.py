"""
Frozen data contracts for Phase 2 worldgen.

All classes are immutable (frozen dataclasses) or tuple-based where possible.
Contracts are the boundary between generator (labels visible, zone names visible)
and evaluator/detectors (labels/zones stripped, events anonymized).

---

KEY EPISTEMIC CONSTRAINTS (non-negotiable; baked into the contracts):
1. RawEvent carries generator-side labels (zone, archetype, attack_type, is_attack).
   NEVER serialize or show RawEvent to detectors — use AnonymizedEvent only.
2. AnonymizedEvent STRIPS zone/archetype/attack labels; resource/actor IDs are hashed;
   action_type is mapped to opaque tokens. This is the ONLY contract detectors see.
3. GroundTruth (actor_hash, time_window, attack_type) is evaluator-side only.
4. World fully determined by (config, seed); byte-identical regeneration enforced.
5. Simulation horizon must give each actor >> 80 transitions (per PREDICTIONS.md Correction 2),
   supporting per-actor rolling-window physics scoring (locked decision §8).

---

ANONYMIZATION GUARANTEES:
- No zone name appears in AnonymizedEvent or any detector-visible artifact.
- No archetype name appears in detector-visible artifacts.
- No attack labels in detector-visible artifacts.
- Resource/actor hashes are salted deterministically per (seed, salt_key); stable across
  regenerations with the same seed, but opaque to detectors.
- Action type mapped to opaque token (e.g., 'auth' -> 'T001', deterministic per seed).
- Timestamps jittered uniformly [t - jitter_window, t + jitter_window] per event
  (jitter deterministic per seed + event).

---

ZONES (six minimum, per §2.1; generator-side only):
  IDENTITY, SECRET, DATA, COMPUTE, LOGGING, EXTERNAL, ADMIN
  Use >= 6 so zone-count cannot leak labels (§4.2).

ARCHETYPES (nine benign, §3.1; generator-side only):
  1. Developer
  2. DataAnalyst
  3. CICDServiceAccount
  4. ETLPipelineServiceAccount (benign one-way: IDENTITY → SECRET → DATA → EXTERNAL)
  5. BackupLogShippingAccount (benign one-way: DATA → LOGGING / DATA → EXTERNAL)
  6. OnCallSRE (rare, sudden access to never-before-touched resources)
  7. NewHire (starts with zero history, explores broadly N days, then settles)
  8. RoleChange (mid-simulation, archetype switches; old distribution stale)
  9. BreakGlassAdmin (rare, high-privilege one-shot: IDENTITY → ADMIN → SECRET, then dormant)

ATTACKS (five types, §3.2; generator-side only):
  1. CredentialTheftLateral — compromised actor: IDENTITY → COMPUTE → COMPUTE' → SECRET → DATA
     with assume/grant credential-switch mid-path, reaching out-of-history resources.
  2. SlowExfiltration — compromised analyst adds low-rate DATA → EXTERNAL drip over weeks.
  3. SmashAndGrab — fast one-session IDENTITY → SECRET → DATA → EXTERNAL burst (easy anchor).
  4. LivingOffTheLand — attack uses ONLY edges in actor's own history, altering
     sequencing/direction/rate (e.g., ETL's legitimate path in novel order, terminating in
     EXTERNAL at 10× volume). Per-edge rarity zero signal by construction.
  5. ServiceAccountHijack — CI account deviates from machine-regular loop into SECRET → EXTERNAL.

HARD NEGATIVES (§3.3; generator-side only):
  - ETL twin: for each world with SmashAndGrab or SlowExfil, benign ETL (arch 4) matches
    path length, per-edge rarity percentile, zone sequence. Only differ in behavioral
    regularity, rate profile, relation to own history.
  - On-call storm: at least one on-call window overlapping each attack window in time.
  - Novelty flood: new-hire and role-change events distributed across horizon.

GROUND-TRUTH LABELS (evaluator-side only):
  (actor_hash, time_window_start, time_window_end) -> attack_type
  Time windows for rolling-window scoring (per actor, last N transitions, NOT fixed clock).
"""

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set, Tuple
from enum import Enum
import json


# =====================================================================
# ENUMS AND TYPE ALIASES
# =====================================================================

class ArchetypeKind(Enum):
    """Nine benign actor archetypes (generator-side only)."""
    Developer = "Developer"
    DataAnalyst = "DataAnalyst"
    CICDServiceAccount = "CICDServiceAccount"
    ETLPipelineServiceAccount = "ETLPipelineServiceAccount"
    BackupLogShippingAccount = "BackupLogShippingAccount"
    OnCallSRE = "OnCallSRE"
    NewHire = "NewHire"
    RoleChange = "RoleChange"
    BreakGlassAdmin = "BreakGlassAdmin"


class AttackType(Enum):
    """Five attack types (generator-side only)."""
    CredentialTheftLateral = "CredentialTheftLateral"
    SlowExfiltration = "SlowExfiltration"
    SmashAndGrab = "SmashAndGrab"
    LivingOffTheLand = "LivingOffTheLand"
    ServiceAccountHijack = "ServiceAccountHijack"


# =====================================================================
# GENERATOR-SIDE CONTRACTS (with labels, zones, archetypes visible)
# =====================================================================

@dataclass(frozen=True)
class RawEvent:
    """
    Single cloud IAM event as seen by the generator.
    Contains labels (zone, archetype, attack markers) — NEVER shown to detectors.

    Attributes:
        t: timestamp (float, seconds since epoch or virtual time)
        actor_id: actor identifier (unhashed, generator-side only)
        src_resource: source resource ID (unhashed, generator-side only)
        dst_resource: destination resource ID (unhashed, generator-side only)
        action_type: semantic action (e.g., 'auth', 'read', 'write', 'invoke', 'grant', 'assume')
        zone_src: source zone (e.g., 'IDENTITY', 'DATA', 'SECRET', ...; GENERATOR ONLY)
        zone_dst: destination zone (GENERATOR ONLY)
        archetype: actor's archetype (GENERATOR ONLY)
        is_attack: whether this event is part of an injected attack
        attack_type: type of attack if is_attack is True; None otherwise (GENERATOR ONLY)
    """
    t: float
    actor_id: str
    src_resource: str
    dst_resource: str
    action_type: str
    zone_src: str
    zone_dst: str
    archetype: str
    is_attack: bool
    attack_type: Optional[str] = None

    def __hash__(self):
        return hash((
            self.t, self.actor_id, self.src_resource, self.dst_resource,
            self.action_type, self.zone_src, self.zone_dst, self.archetype,
            self.is_attack, self.attack_type
        ))


@dataclass(frozen=True)
class Actor:
    """
    Generator-side actor (benign or to-be-compromised).

    Attributes:
        id: unhashed actor identifier (generator-side only)
        archetype: ArchetypeKind enum value
        role_change_time: if this actor's archetype changes mid-simulation, the time at which
                         it changes. None if archetype is static. (Optional feature; may be None.)
        metadata: optional dict for additional archetype-specific properties (e.g., zone affinity).
    """
    id: str
    archetype: ArchetypeKind
    role_change_time: Optional[float] = None
    metadata: Dict[str, any] = field(default_factory=dict)


@dataclass(frozen=True)
class Campaign:
    """
    Attack instance (campaign): the fundamental evaluation unit.
    Represents one realized attack injected into one actor's trajectory.

    One campaign = one ground-truth label. Detection = any (actor, rolling-window)
    alert overlapping [t_start, t_end] interval (no pseudo-replication).

    Attributes:
        actor_id: unhashed actor ID (generator-side, for determinism/traceability)
        actor_hash: hashed actor ID (as appears in AnonymizedEvent, evaluator-side)
        t_start: attack onset (float, seconds in virtual time)
        t_end: attack end (float, seconds in virtual time)
        flavor: AttackType enum value or string name (which of 5 attack types)
        world_seed: which world this campaign belongs to (for tracking allocation)
    """
    actor_id: str
    actor_hash: str
    t_start: float
    t_end: float
    flavor: str  # string name of AttackType for JSON compatibility
    world_seed: int


@dataclass(frozen=True)
class GroundTruthLabel:
    """
    Single ground-truth attack label (evaluator-side only).
    DEPRECATED: replaced by Campaign. Kept for backward compatibility during transition.

    Attributes:
        actor_hash: hashed actor ID (as appears in AnonymizedEvent)
        t_window_start: start of attack window (float, or rolling-window anchor time)
        t_window_end: end of attack window (float, or rolling-window anchor + window_size)
        attack_type: AttackType enum value or string name
    """
    actor_hash: str
    t_window_start: float
    t_window_end: float
    attack_type: str  # string name of AttackType for JSON compatibility


@dataclass
class GroundTruth:
    """
    Ground-truth attack data (evaluator-side only).
    Deterministic per world (config, seed).

    As of Phase 3 (2026-07-03), uses campaigns (attack instances) as the fundamental
    evaluation unit, not per-window labels. One campaign = one ground-truth label.

    Attributes:
        campaigns: frozenset of Campaign (attack instances)
        labels: frozenset of GroundTruthLabel (DEPRECATED; for backward compat during transition)
        schema_version: "campaign" (per-instance) or "rolling_window" (deprecated).
                       Phase 3+ uses "campaign" per locked decision (SANDBOX_CONTRACT.md §1).
    """
    campaigns: FrozenSet[Campaign] = field(default_factory=frozenset)
    labels: FrozenSet[GroundTruthLabel] = field(default_factory=frozenset)
    schema_version: str = "campaign"

    def add_campaign(
        self,
        actor_id: str,
        actor_hash: str,
        t_start: float,
        t_end: float,
        flavor: str,
        world_seed: int
    ) -> None:
        """
        Add a campaign (attack instance).
        Mutates; intended for use during world generation before freezing.
        """
        new_campaign = Campaign(
            actor_id=actor_id,
            actor_hash=actor_hash,
            t_start=t_start,
            t_end=t_end,
            flavor=flavor,
            world_seed=world_seed
        )
        self.campaigns = self.campaigns | {new_campaign}

    def add_label(self, actor_id_or_hash: str, t_start: float, t_end: float, attack_type: str) -> None:
        """
        DEPRECATED: Add a label (old interface for backward compat).
        New code should use add_campaign() instead.

        Note: During generation, actor_id_or_hash is the unhashed actor_id.
        After anonymization, it gets hashed. The parameter name is a misnomer for backward compat.
        """
        new_label = GroundTruthLabel(
            actor_hash=actor_id_or_hash,  # Will be hashed in phase 5
            t_window_start=t_start,
            t_window_end=t_end,
            attack_type=attack_type
        )
        self.labels = self.labels | {new_label}

    def to_dict(self) -> Dict:
        """Serialize to JSON-compatible dict (evaluator-side only)."""
        return {
            "schema_version": self.schema_version,
            "campaigns": [
                {
                    "actor_id": c.actor_id,
                    "actor_hash": c.actor_hash,
                    "t_start": c.t_start,
                    "t_end": c.t_end,
                    "flavor": c.flavor,
                    "world_seed": c.world_seed,
                }
                for c in self.campaigns
            ],
            "labels": [
                {
                    "actor_hash": label.actor_hash,
                    "t_window_start": label.t_window_start,
                    "t_window_end": label.t_window_end,
                    "attack_type": label.attack_type,
                }
                for label in self.labels
            ] if self.labels else []
        }


# =====================================================================
# DETECTOR-VISIBLE CONTRACT (anonymized, no labels)
# =====================================================================

@dataclass(frozen=True)
class AnonymizedEvent:
    """
    Detector-visible event; all labels/zones/archetypes stripped.
    This is the ONLY contract detectors receive.

    Attributes:
        t: timestamp (float, jittered deterministically per seed)
        actor: hashed actor ID (stable per seed, opaque to detector)
        src: hashed source resource (stable per seed, opaque to detector)
        dst: hashed destination resource (stable per seed, opaque to detector)
        action: action type mapped to opaque token (deterministic per seed)

    Invariant:
        - No zone name in any field
        - No archetype name in any field
        - No attack label in any field
        - No unmasked resource/actor IDs
    """
    t: float
    actor: str
    src: str
    dst: str
    action: str

    def __hash__(self):
        return hash((self.t, self.actor, self.src, self.dst, self.action))

    def to_transition(self) -> Tuple[float, str, str, str, str]:
        """
        Convert to (t, actor, src, dst, action) tuple for Trajectory.Transition compatibility.
        """
        return (self.t, self.actor, self.src, self.dst, self.action)


# =====================================================================
# CONFIGURATION AND WORLD CONTRACTS
# =====================================================================

@dataclass(frozen=True)
class WorldConfig:
    """
    Configuration for a single generated world.
    Fully determines world when combined with seed (via generate(config, seed) -> World).

    Attributes:
        population_size: number of actors (200–500 per §3.1)
        archetype_mixture: dict mapping ArchetypeKind.value -> float (sums to 1.0).
                          Must guarantee >= 3 instances each of archetypes 4–9.
        horizon_days: simulation duration in virtual days (60–90 per §3.1).
        event_rate_lambda: Poisson rate parameter for event generation (events/day).
                          Must be tuned so each actor accumulates >> 80 transitions over horizon.
        attack_mix: dict mapping AttackType.value -> float (sums to 1.0 or 0 if no attacks).
                    probability distribution over attack types to inject.
        attack_compromise_count: number of actors to compromise (1–3 per §3.2).
        attack_onset_phase: (t_min, t_max) in [0, 1] fraction of horizon; attacks start uniformly
                            in middle third of horizon (so pre-attack history exists for baselining).
        action_vocab: list of action types (e.g., ['auth', 'read', 'write', 'invoke', 'grant', 'assume']).
        zone_labels: list of zone names (minimum 6 per §2.1, e.g.,
                    ['IDENTITY', 'SECRET', 'DATA', 'COMPUTE', 'LOGGING', 'EXTERNAL', 'ADMIN']).
        seed: random seed for determinism (world generation reproducible given config + seed).
    """
    population_size: int
    archetype_mixture: Dict[str, float]  # ArchetypeKind.value -> weight
    horizon_days: float
    event_rate_lambda: float
    attack_mix: Dict[str, float]  # AttackType.value -> weight
    attack_compromise_count: int
    attack_onset_phase: Tuple[float, float]  # (t_min_frac, t_max_frac) in [0, 1]
    action_vocab: Tuple[str, ...]  # frozen tuple
    zone_labels: Tuple[str, ...]  # frozen tuple, >= 6
    seed: int
    attack_world_ratio: float = 0.5  # P(this world is an attack world); §6.2 wants 0.5.
    # Decoupled from attack_mix, which only selects WHICH attack type is injected in an attack world.

    def to_dict(self) -> Dict:
        """Serialize to JSON-compatible dict."""
        return {
            "population_size": self.population_size,
            "attack_world_ratio": self.attack_world_ratio,
            "archetype_mixture": self.archetype_mixture,
            "horizon_days": self.horizon_days,
            "event_rate_lambda": self.event_rate_lambda,
            "attack_mix": self.attack_mix,
            "attack_compromise_count": self.attack_compromise_count,
            "attack_onset_phase": self.attack_onset_phase,
            "action_vocab": list(self.action_vocab),
            "zone_labels": list(self.zone_labels),
            "seed": self.seed,
        }


@dataclass
class AnonymizedMapping:
    """
    Evaluator-side only: the salt and hashes used to anonymize a world.
    NEVER serialize to disk or show to detectors.

    Attributes:
        salt: random bytes or string used as HMAC key for hashing (deterministic per seed).
        actor_hashes: dict mapping unhashed actor_id -> hashed actor_id.
        resource_hashes: dict mapping unhashed resource_id -> hashed resource_id.
        action_tokens: dict mapping semantic action -> opaque token (deterministic).
        jitter_amounts: dict mapping raw event timestamp -> jitter applied
                        (for auditing/verification purposes; not shown to detectors).
    """
    salt: str
    actor_hashes: Dict[str, str]
    resource_hashes: Dict[str, str]
    action_tokens: Dict[str, str]
    jitter_amounts: Dict[float, float] = field(default_factory=dict)


@dataclass
class World:
    """
    A fully-generated world: actors, events, ground truth, config, and anonymization mapping.

    Attributes:
        config: WorldConfig (determines all generation, all tuning parameters).
        seed: random seed (redundant with config.seed; kept for clarity).
        actors: list of Actor objects (generator-side).
        raw_events: list of RawEvent objects in time order, fully labeled (generator-side only).
        ground_truth: GroundTruth labels (evaluator-side only).
        anonymized_events: list of AnonymizedEvent objects (detector-visible; derived from raw_events).
        anonymized_mapping: AnonymizedMapping (evaluator-side only; used to verify anonymization,
                            compute ground-truth hashes, etc.).
    """
    config: WorldConfig
    seed: int
    actors: List[Actor]
    raw_events: List[RawEvent]
    ground_truth: GroundTruth
    anonymized_events: List[AnonymizedEvent]
    anonymized_mapping: AnonymizedMapping

    def raw_event_log_size(self) -> int:
        """Total number of raw events."""
        return len(self.raw_events)

    def anonymized_event_log_size(self) -> int:
        """Total number of anonymized events (should equal raw_event_log_size)."""
        return len(self.anonymized_events)

    def to_detector_visible_dict(self) -> Dict:
        """
        Return ONLY detector-visible fields (anonymized events + config).
        NEVER include raw_events, ground_truth, or anonymized_mapping.

        Returns dict with:
        - config: world config as dict
        - anonymized_events: list of (t, actor, src, dst, action) tuples
        """
        return {
            "config": self.config.to_dict(),
            "anonymized_events": [
                {
                    "t": e.t,
                    "actor": e.actor,
                    "src": e.src,
                    "dst": e.dst,
                    "action": e.action,
                }
                for e in self.anonymized_events
            ]
        }

    def to_evaluator_visible_dict(self) -> Dict:
        """
        Return evaluator-visible fields (config, ground truth, anonymized events).
        DOES NOT include raw_events or anonymized_mapping (kept in-memory).

        Used for passing to audits, harness, metric computation.
        """
        return {
            "config": self.config.to_dict(),
            "ground_truth": self.ground_truth.to_dict(),
            "anonymized_events": [
                {
                    "t": e.t,
                    "actor": e.actor,
                    "src": e.src,
                    "dst": e.dst,
                    "action": e.action,
                }
                for e in self.anonymized_events
            ]
        }
