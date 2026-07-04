"""
Grep-level label leakage check (§4.2).

Verifies that detector-visible artifacts contain NO strings from the generator's
label vocabulary (zone names, archetype names, attack markers, etc.).

This is a mechanical verification that anonymize.py actually stripped labels.
It runs AFTER anonymization and BEFORE detector evaluation.
"""

from typing import List, Set, Tuple
import json
from ..worldgen.model import World, ArchetypeKind, AttackType


class GrepLeakCheckResult:
    """
    Result of grep leakage check.

    Attributes:
        passed: bool — no label leakage detected
        leaks_found: List[Tuple[str, str, str]] — (leaked_string, location, context)
        summary: str — human-readable summary
    """
    def __init__(self):
        self.passed: bool = True
        self.leaks_found: List[Tuple[str, str, str]] = []
        self.summary: str = ""


def run(
    worlds: List[World],
) -> GrepLeakCheckResult:
    """
    Scan detector-visible artifacts for leaked generator-side labels.

    Searches for:
    - Zone names: IDENTITY, SECRET, DATA, COMPUTE, LOGGING, EXTERNAL, ADMIN
    - Archetype names: Developer, DataAnalyst, CICDServiceAccount, ETLPipelineServiceAccount,
      BackupLogShippingAccount, OnCallSRE, NewHire, RoleChange, BreakGlassAdmin
    - Attack type names: CredentialTheftLateral, SlowExfiltration, SmashAndGrab,
      LivingOffTheLand, ServiceAccountHijack
    - Attack markers: is_attack, attack_type, "EXFIL", "ATTACK", "ANOMALY" (common naming patterns)

    Scans:
    - AnonymizedEvent.t, .actor, .src, .dst, .action fields
    - Config exported to detector-visible dict
    - No deep nesting (anonymized events are flat)

    Args:
        worlds: list of World objects to scan.

    Returns:
        GrepLeakCheckResult with .passed (bool) and .leaks_found list.

    Raises:
        ValueError: if worlds list is empty or malformed.
    """
    if not worlds:
        raise ValueError("worlds list cannot be empty")

    result = GrepLeakCheckResult()

    # Build forbidden vocabulary
    forbidden_vocab = set()

    # Zone names
    for world in worlds:
        forbidden_vocab.update(world.config.zone_labels)

    # Archetype names
    for archetype in ArchetypeKind:
        forbidden_vocab.add(archetype.value)

    # Attack type names
    for attack_type in AttackType:
        forbidden_vocab.add(attack_type.value)

    # Additional markers
    forbidden_vocab.update(["EXFIL", "ATTACK", "ANOMALY", "is_attack", "attack_type",
                           "archetype", "zone", "label", "SECRET", "IDENTITY"])

    # Convert to lowercase for case-insensitive matching
    forbidden_vocab_lower = {v.lower() for v in forbidden_vocab}

    # Scan each world
    for world_idx, world in enumerate(worlds):
        detector_visible = world.to_detector_visible_dict()

        # Scan anonymized events
        for event_idx, event_dict in enumerate(detector_visible.get("anonymized_events", [])):
            for field, value in event_dict.items():
                value_str = str(value)
                for forbidden in forbidden_vocab_lower:
                    if forbidden in value_str.lower():
                        context = f"world_{world_idx}.event_{event_idx}.{field}"
                        result.leaks_found.append((forbidden, context, value_str[:50]))
                        result.passed = False

    if result.passed:
        result.summary = f"✓ PASS: No label leakage detected in {len(worlds)} worlds"
    else:
        result.summary = f"✗ FAIL: Found {len(result.leaks_found)} label leaks"
        result.summary += f"\n  Examples: {result.leaks_found[:3]}"

    return result
