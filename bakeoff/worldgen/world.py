"""
Main world generation orchestrator.

Coordinates all phases:
1. Actor population generation (archetypes, counts per mixture weights)
2. Benign trajectory generation (per actor via build_archetype)
3. Attack injection (if world is attack-world, per config.attack_mix)
4. Hard-negative injection (mandatory confounds per §3.3)
5. Anonymization (strip labels, hash IDs per §4.2)

Each world is fully determined by (config, seed); regeneration must be byte-identical.
"""

import numpy as np
from typing import List, Tuple, Dict
from .model import World, WorldConfig, Actor, ArchetypeKind, AttackType, GroundTruth
from .benign import build_archetype
from .attacks import inject_attack
from .hard_negatives import ensure_hard_negatives
from .anonymize import anonymize


def generate(
    config: WorldConfig,
    seed: int,
    *,
    force_attack_world: bool = None,
    forced_flavor: "AttackType" = None,
) -> World:
    """
    Generate a complete synthetic world: actors, events, ground truth, anonymization.

    Orchestrates the full pipeline:
    1. Initialize population of actors per config.population_size and archetype_mixture
    2. Generate benign trajectories for each actor (via benign.build_archetype)
    3. Inject attacks if this is an attack-world (via attacks.inject_attack)
    4. Inject hard negatives (via hard_negatives.ensure_hard_negatives)
    5. Anonymize events and build detector-visible log (via anonymize.anonymize)
    6. Return complete World

    Args:
        config: WorldConfig (population_size, archetype_mixture, horizon_days, attack_mix, seed, etc.)
        seed: random seed for this world (all generation deterministic per seed)

    Returns:
        World object containing:
        - config: input WorldConfig
        - seed: input seed
        - actors: list of Actor (generator-side)
        - raw_events: list of RawEvent (unhashed, labeled; generator-side only)
        - ground_truth: GroundTruth (evaluator-side only)
        - anonymized_events: list of AnonymizedEvent (detector-visible)
        - anonymized_mapping: AnonymizedMapping (evaluator-side only)

    Raises:
        ValueError: if config is malformed.
    """
    rng = np.random.default_rng(seed)

    # Phase 1: Initialize population of actors
    actors = _initialize_population(config, rng)

    # Phase 2: Generate benign trajectories
    raw_events: List = []
    for actor in actors:
        # Seed each actor's generation with a derivative of the main seed
        actor_seed = seed + hash(actor.id) % (2**31)
        actor_events = build_archetype(actor.archetype, actor.id, config, actor_seed)
        raw_events.extend(actor_events)

    # Sort by time
    raw_events.sort(key=lambda e: e.t)

    # Phase 3: Decide if this is an attack world and inject attacks
    is_attack_world = (_should_be_attack_world(seed, config)
                       if force_attack_world is None else force_attack_world)
    ground_truth = GroundTruth()

    if is_attack_world:
        num_attacks = config.attack_compromise_count

        if forced_flavor is not None:
            # BALANCED ALLOCATION (2026-07-03, autonomous fix): this whole world uses ONE
            # flavor; compromise up to num_attacks victims ELIGIBLE FOR THAT FLAVOR. The driver
            # cycles flavors across attack worlds so every flavor gets an equal, sufficient
            # number of independent campaigns (the previous random attack_mix + eligibility
            # interaction systematically starved LOTL, which needs ETL/backup victims).
            pool = [a for a in actors if _is_victim_eligible(forced_flavor, a)]
            k = min(num_attacks, len(pool))
            chosen = ([pool[int(i)] for i in rng.choice(len(pool), size=k, replace=False)]
                      if k > 0 else [])
            for victim in chosen:
                raw_events, labels = inject_attack(
                    forced_flavor, victim, raw_events, config,
                    seed + hash(victim.id) % (2**31)
                )
                for actor_id, t_start, t_end, attack_type_str in labels:
                    ground_truth.add_label(actor_id, t_start, t_end, attack_type_str)
        else:
            # Legacy random allocation (retained for back-compat; not used by the balanced driver).
            eligible_actors = [a for a in actors if _is_eligible_for_any_attack(a)]
            if len(eligible_actors) >= num_attacks:
                victim_indices = rng.choice(len(eligible_actors), size=num_attacks, replace=False)
                victims = [eligible_actors[i] for i in victim_indices]
            else:
                victims = eligible_actors
            attack_types = list(AttackType)
            for victim in victims:
                eligible_attacks = [at for at in attack_types
                                   if _is_victim_eligible(at, victim)]
                if eligible_attacks:
                    attack_type = rng.choice(eligible_attacks)
                    raw_events, labels = inject_attack(
                        attack_type, victim, raw_events, config,
                        seed + hash(victim.id) % (2**31)
                    )
                    for actor_id, t_start, t_end, attack_type_str in labels:
                        ground_truth.add_label(actor_id, t_start, t_end, attack_type_str)

    # Re-sort events after injection
    raw_events.sort(key=lambda e: e.t)

    # Phase 4: Inject hard negatives
    world_temp = World(
        config=config,
        seed=seed,
        actors=actors,
        raw_events=raw_events,
        ground_truth=ground_truth,
        anonymized_events=[],  # placeholder
        anonymized_mapping=None,  # placeholder
    )
    world_temp = ensure_hard_negatives(world_temp)
    raw_events = world_temp.raw_events
    ground_truth = world_temp.ground_truth
    actors = world_temp.actors

    # Re-sort events after hard-negative injection
    raw_events.sort(key=lambda e: e.t)

    # Phase 5: Anonymize
    anonymized_events, anonymized_mapping = anonymize(raw_events, seed)

    # Build ground truth with hashed actor IDs
    # Convert from old label format to new campaign format
    ground_truth_hashed = GroundTruth()

    # Handle campaigns (new format) — hash the actor_id to get actor_hash
    for campaign in ground_truth.campaigns:
        actor_hash = anonymized_mapping.actor_hashes.get(campaign.actor_id, campaign.actor_id)
        ground_truth_hashed.add_campaign(
            actor_id=campaign.actor_id,
            actor_hash=actor_hash,
            t_start=campaign.t_start,
            t_end=campaign.t_end,
            flavor=campaign.flavor,
            world_seed=seed
        )

    # Handle legacy labels (old format) — convert to campaigns for evaluation
    # This bridges the transition from label-based to campaign-based ground truth.
    for label in ground_truth.labels:
        # Labels store actor_hash field, but it's actually the unhashed actor_id during generation
        # Resolve it to get the true hashed value
        actor_id_from_label = label.actor_hash
        actor_hash = anonymized_mapping.actor_hashes.get(actor_id_from_label, actor_id_from_label)

        # Convert label to campaign (attack instance)
        ground_truth_hashed.add_campaign(
            actor_id=actor_id_from_label,
            actor_hash=actor_hash,
            t_start=label.t_window_start,
            t_end=label.t_window_end,
            flavor=label.attack_type,
            world_seed=seed
        )

    # Assemble final World
    world = World(
        config=config,
        seed=seed,
        actors=actors,
        raw_events=raw_events,
        ground_truth=ground_truth_hashed,
        anonymized_events=anonymized_events,
        anonymized_mapping=anonymized_mapping,
    )

    return world


def _initialize_population(config: WorldConfig, rng) -> List[Actor]:
    """
    Initialize a population of actors according to archetype_mixture.

    Args:
        config: WorldConfig with population_size and archetype_mixture
        rng: numpy random generator

    Returns:
        List of Actor objects
    """
    actors = []
    archetype_kinds = list(ArchetypeKind)

    # Get mixture weights
    weights = []
    for ak in archetype_kinds:
        weights.append(config.archetype_mixture.get(ak.value, 0.0))

    # Normalize if needed
    total_weight = sum(weights)
    if total_weight > 0:
        weights = [w / total_weight for w in weights]
    else:
        # Default uniform
        weights = [1.0 / len(archetype_kinds)] * len(archetype_kinds)

    # Sample archetypes according to weights
    archetype_counts = rng.multinomial(config.population_size, weights)

    actor_id_counter = 0
    for archetype, count in zip(archetype_kinds, archetype_counts):
        for _ in range(count):
            actor = Actor(
                id=f"actor_{actor_id_counter:05d}",
                archetype=archetype,
                role_change_time=None,
                metadata={}
            )
            actors.append(actor)
            actor_id_counter += 1

    return actors


def _should_be_attack_world(seed: int, config: WorldConfig) -> bool:
    """
    Deterministically decide if this world should be an attack world.

    Uses seed to split worlds per config.attack_world_ratio (default 0.5, per §6.2).

    BUGFIX 2026-07-03: previously used sum(config.attack_mix.values()), which is 1.0
    whenever attack-type weights are normalized -> 100% attack worlds, 0 benign. The
    attack/benign split must be governed by attack_world_ratio; attack_mix only selects
    WHICH attack type is injected within an attack world.
    """
    attack_ratio = config.attack_world_ratio
    rng = np.random.default_rng(seed)
    return rng.random() < attack_ratio


def _is_eligible_for_any_attack(actor: Actor) -> bool:
    """
    Check if an actor is eligible for at least one attack type.
    """
    eligible_attacks = {
        "CredentialTheftLateral": [ArchetypeKind.Developer, ArchetypeKind.DataAnalyst],
        "SlowExfiltration": [ArchetypeKind.DataAnalyst],
        "SmashAndGrab": list(ArchetypeKind),  # any
        "LivingOffTheLand": [ArchetypeKind.ETLPipelineServiceAccount, ArchetypeKind.BackupLogShippingAccount],
        "ServiceAccountHijack": [ArchetypeKind.CICDServiceAccount],
    }

    for attack_type, eligible_archetypes in eligible_attacks.items():
        if actor.archetype in eligible_archetypes:
            return True
    return False


def _is_victim_eligible(attack_type: AttackType, actor: Actor) -> bool:
    """
    Check if an actor is eligible for a specific attack type.
    """
    if attack_type == AttackType.CredentialTheftLateral:
        return actor.archetype in [ArchetypeKind.Developer, ArchetypeKind.DataAnalyst]
    elif attack_type == AttackType.SlowExfiltration:
        return actor.archetype == ArchetypeKind.DataAnalyst
    elif attack_type == AttackType.SmashAndGrab:
        return True
    elif attack_type == AttackType.LivingOffTheLand:
        return actor.archetype in [ArchetypeKind.ETLPipelineServiceAccount, ArchetypeKind.BackupLogShippingAccount]
    elif attack_type == AttackType.ServiceAccountHijack:
        return actor.archetype == ArchetypeKind.CICDServiceAccount
    return False
