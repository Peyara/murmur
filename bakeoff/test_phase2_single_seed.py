#!/usr/bin/env python3
"""
Quick test: generate 1 world and run all 3 audits to validate the pipeline.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bakeoff.worldgen.model import WorldConfig, ArchetypeKind, AttackType
from bakeoff.worldgen.world import generate
from bakeoff.audits.grep_leak_check import run as grep_leak_check
from bakeoff.audits.fairness_audit import run as fairness_audit
from bakeoff.audits.leakage_redteam import run as leakage_redteam


def main():
    print("=" * 80)
    print("PHASE 2 SINGLE-SEED TEST")
    print("=" * 80)

    # Create config
    config = WorldConfig(
        population_size=200,  # Larger to ensure each actor gets >>80 transitions
        archetype_mixture={
            ArchetypeKind.Developer.value: 0.40,
            ArchetypeKind.DataAnalyst.value: 0.15,
            ArchetypeKind.CICDServiceAccount.value: 0.10,
            ArchetypeKind.ETLPipelineServiceAccount.value: 0.08,
            ArchetypeKind.BackupLogShippingAccount.value: 0.07,
            ArchetypeKind.OnCallSRE.value: 0.08,
            ArchetypeKind.NewHire.value: 0.06,
            ArchetypeKind.RoleChange.value: 0.04,
            ArchetypeKind.BreakGlassAdmin.value: 0.02,
        },
        horizon_days=90.0,  # 90 days as per spec
        event_rate_lambda=3.0,  # Increase event rate
        attack_mix={
            AttackType.CredentialTheftLateral.value: 0.20,
            AttackType.SlowExfiltration.value: 0.20,
            AttackType.SmashAndGrab.value: 0.25,
            AttackType.LivingOffTheLand.value: 0.20,
            AttackType.ServiceAccountHijack.value: 0.15,
        },
        attack_compromise_count=2,
        attack_onset_phase=(1/3, 2/3),
        action_vocab=("auth", "read", "write", "invoke", "grant", "assume"),
        zone_labels=("IDENTITY", "SECRET", "DATA", "COMPUTE", "LOGGING", "EXTERNAL", "ADMIN"),
        seed=42,
    )

    print("\n[1/4] Generating world...")
    try:
        world = generate(config, 42)
        print(f"  ✓ Generated world: {len(world.raw_events)} events, {len(world.actors)} actors")
        print(f"  ✓ Attack windows: {len(world.ground_truth.labels)}")
        print(f"  ✓ Anonymized events: {len(world.anonymized_events)}")
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Test audits with single world
    worlds = [world]

    print("\n[2/4] Grep leak check...")
    try:
        result = grep_leak_check(worlds)
        print(f"  {result.summary}")
        if not result.passed:
            print(f"    Leaks: {result.leaks_found[:3]}")
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print("\n[3/4] Fairness audit...")
    try:
        result = fairness_audit(worlds)
        print(f"  {result.summary}")
        if result.per_actor_transitions:
            for actor_group, (min_t, med_t, mean_t) in result.per_actor_transitions.items():
                print(f"    {actor_group}: min={min_t}, median={med_t}, mean={mean_t:.1f}")
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print("\n[4/4] Leakage red-team...")
    try:
        result = leakage_redteam(worlds)
        print(f"  {result.message}")
        print(f"    AUC-PR: {result.auc_pr:.3f} [CI {result.ci_lower:.3f}—{result.ci_upper:.3f}]")
        print(f"    No-skill: {result.no_skill_pr:.3f}")
        if result.stratified_results:
            print(f"    Stratified results:")
            for attack_type, metrics in result.stratified_results.items():
                print(f"      {attack_type}: AUC-PR {metrics.get('auc_pr', 0):.3f}, at_chance={metrics.get('at_chance')}")
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print("\n" + "=" * 80)
    print("✓ SINGLE-SEED TEST PASSED")
    print("=" * 80 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
