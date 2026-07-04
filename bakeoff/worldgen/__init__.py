"""
World generation package (Phase 2 — Frozen design).

Exports:
- model: WorldConfig, World, RawEvent, AnonymizedEvent, GroundTruth, Actor (all frozen contracts)
- worldgen.benign: build_archetype(kind, actor_id, config, seed) -> List[RawEvent]
- worldgen.attacks: inject_attack(attack_type, victim_actor, world_events, config, seed) -> (events, labels)
- worldgen.hard_negatives: ensure_hard_negatives(world) -> world
- worldgen.anonymize: anonymize(raw_events, seed) -> (anonymized_events, mapping)
- worldgen.world: generate(config, seed) -> World
"""

from .model import (
    RawEvent,
    Actor,
    ArchetypeKind,
    AttackType,
    World,
    WorldConfig,
    AnonymizedEvent,
    GroundTruth,
    GroundTruthLabel,
    AnonymizedMapping,
)

__all__ = [
    "RawEvent",
    "Actor",
    "ArchetypeKind",
    "AttackType",
    "World",
    "WorldConfig",
    "AnonymizedEvent",
    "GroundTruth",
    "GroundTruthLabel",
    "AnonymizedMapping",
]
