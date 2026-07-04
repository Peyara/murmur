#!/usr/bin/env python3
"""
Phase 2 Fairness Harness: World Generation + Audit Pipeline

Generates synthetic worlds and runs the fairness audit battery:
1. Grep leak check (§4.2)
2. Fairness audit (§4.1)
3. Leakage red-team (§4.3)

Iterates up to 2 rounds if leakage is found.
Reports structured results.
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Any

import numpy as np

# Add repo root to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from bakeoff.worldgen.model import WorldConfig, ArchetypeKind, AttackType
from bakeoff.worldgen.world import generate
from bakeoff.audits.grep_leak_check import run as grep_leak_check
from bakeoff.audits.fairness_audit import run as fairness_audit
from bakeoff.audits.leakage_redteam import run as leakage_redteam


def create_default_config(seed: int) -> WorldConfig:
    """Create a default WorldConfig for testing."""
    return WorldConfig(
        population_size=200,
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
        horizon_days=90.0,  # 90 days to ensure >>80 transitions per active actor
        event_rate_lambda=3.0,  # 3 events/day average
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
        seed=seed,
    )


def run_phase2_harness(num_seeds: int = 10, max_rounds: int = 2) -> Dict[str, Any]:
    """
    Generate worlds and run fairness audits.

    Args:
        num_seeds: number of trial seeds to generate
        max_rounds: maximum rounds of regeneration if leakage found

    Returns:
        Dict with results from all audits
    """
    print(f"\n{'='*80}")
    print("MURMUR PHASE 2: WORLD GENERATION + FAIRNESS AUDIT")
    print(f"{'='*80}\n")

    all_results = {
        "timestamp": str(np.datetime64("now")),
        "num_seeds": num_seeds,
        "max_rounds": max_rounds,
        "round_results": [],
    }

    for round_num in range(max_rounds):
        print(f"\n{'='*80}")
        print(f"ROUND {round_num + 1}")
        print(f"{'='*80}\n")

        round_seeds = list(range(10000 + round_num * 10000, 10000 + round_num * 10000 + num_seeds))
        worlds = []

        print(f"Generating {num_seeds} worlds...")
        for seed in round_seeds:
            config = create_default_config(seed)
            world = generate(config, seed)
            worlds.append(world)
            print(f"  ✓ Seed {seed}: {len(world.raw_events)} events, {len(world.actors)} actors")

        print(f"\nRunning audits on {len(worlds)} worlds...")

        # Audit 1: Grep leak check
        print("\n[1/3] Grep leak check (§4.2)...")
        grep_result = grep_leak_check(worlds)
        print(f"      {grep_result.summary}")

        # Audit 2: Fairness audit
        print("[2/3] Fairness audit (§4.1)...")
        fairness_result = fairness_audit(worlds)
        print(f"      {fairness_result.summary}")

        # Audit 3: Leakage red-team
        print("[3/3] Leakage red-team (§4.3)...")
        redteam_result = leakage_redteam(worlds)
        print(f"      {redteam_result.message}")

        # Store round results
        round_data = {
            "round": round_num + 1,
            "seeds": round_seeds,
            "grep_leak_check": {
                "passed": grep_result.passed,
                "summary": grep_result.summary,
                "leaks_found": len(grep_result.leaks_found),
            },
            "fairness_audit": {
                "passed": fairness_result.passed,
                "summary": fairness_result.summary,
                "details_count": len(fairness_result.details),
                "per_actor_transitions": fairness_result.per_actor_transitions,
            },
            "leakage_redteam": {
                "at_chance": redteam_result.at_chance,
                "auc_pr": float(redteam_result.auc_pr),
                "ci": [float(redteam_result.ci_lower), float(redteam_result.ci_upper)],
                "no_skill": float(redteam_result.no_skill_pr),
                "message": redteam_result.message,
                "stratified": redteam_result.stratified_results,
            },
        }

        all_results["round_results"].append(round_data)

        # Check if we pass and can exit early
        if grep_result.passed and fairness_result.passed and redteam_result.at_chance:
            print(f"\n✓ ROUND {round_num + 1} PASSED ALL GATES")
            print("\nPhase 2 COMPLETE: Landscape is FAIR")
            all_results["outcome"] = "FAIR"
            break
        else:
            print(f"\n✗ ROUND {round_num + 1} FAILED")
            if not grep_result.passed:
                print(f"   - Grep leak check: {len(grep_result.leaks_found)} leaks found")
            if not fairness_result.passed:
                failed = [d[1] for d in fairness_result.details if not d[2]]
                print(f"   - Fairness audit: {len(failed)} gates failed")
            if not redteam_result.at_chance:
                print(f"   - Leakage red-team: detector NOT at chance (AUC-PR {redteam_result.auc_pr:.3f})")

            if round_num < max_rounds - 1:
                print(f"\n   Regenerating for round {round_num + 2}...")
            else:
                print(f"\n   Max rounds reached. Phase 2 FAILED.")
                all_results["outcome"] = "RIGGED"
    else:
        # All rounds exhausted without passing
        if "outcome" not in all_results:
            all_results["outcome"] = "RIGGED"

    print(f"\n{'='*80}")
    print(f"PHASE 2 OUTCOME: {all_results['outcome']}")
    print(f"{'='*80}\n")

    return all_results


def main():
    """Entry point."""
    # Dependencies are managed by uv (scikit-learn, scipy added via `uv add`). Fail loudly if absent —
    # NEVER pip install (project rule: uv only).
    import scipy  # noqa: F401
    import sklearn  # noqa: F401

    # Run harness. 24 seeds so a group-by-world 70/30 split has both classes on each side.
    results = run_phase2_harness(num_seeds=24, max_rounds=2)

    # Write report
    output_file = Path(__file__).parent / "reports" / "phase2_fairness_results.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nResults written to: {output_file}")

    # Return exit code based on outcome
    sys.exit(0 if results["outcome"] == "FAIR" else 1)


if __name__ == "__main__":
    main()
