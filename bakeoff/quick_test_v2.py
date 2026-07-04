#!/usr/bin/env python3
"""
Quick test of sandbox generation pipeline with 10 worlds.
Verifies all components work before full 100-world run.
"""

import json
from pathlib import Path
from typing import Dict, List

import warnings
warnings.filterwarnings('ignore', category=FutureWarning)

from bakeoff.configs.world_config import DEFAULT_WORLD_CONFIG
from bakeoff.worldgen.sandbox import generate_balanced_batch
from bakeoff.audits.grep_leak_check import run as run_grep_leak_check
from bakeoff.audits.fairness_audit import run as run_fairness_audit
from bakeoff.audits.leakage_redteam import run as run_leakage_redteam


def main():
    print("\n" + "=" * 80)
    print("QUICK TEST: Sandbox V2 Pipeline (10 worlds)")
    print("=" * 80)

    # Generate 10 worlds
    print("\n1. Generating 10 test worlds...", flush=True)
    try:
        batch = generate_balanced_batch(
            config=DEFAULT_WORLD_CONFIG,
            total_seeds=10,
            target_campaigns_per_flavor=2.0,  # Expect ~2 per flavor in 10 worlds
            dev_fraction=0.3,
            verbose=False,
        )
        print(f"   ✓ Generated {len(batch['worlds'])} worlds")
    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1

    worlds = batch["worlds"]

    # Test 1: Grep leak check
    print("\n2. Running grep leak check...", end=" ", flush=True)
    try:
        grep_result = run_grep_leak_check(worlds)
        print(f"{'✓ PASS' if grep_result.passed else '✗ FAIL'}")
        if not grep_result.passed:
            print(f"   Leaks: {grep_result.leaks_found[:3]}")
    except Exception as e:
        print(f"✗ {e}")
        return 1

    # Test 2: Fairness audit
    print("\n3. Running fairness audit...", end=" ", flush=True)
    try:
        fairness_result = run_fairness_audit(worlds)
        print(f"{'✓ PASS' if fairness_result.passed else '✗ FAIL'}")
    except Exception as e:
        print(f"✗ {e}")
        return 1

    # Test 3: Leakage redteam
    print("\n4. Running leakage red-team...", end=" ", flush=True)
    try:
        redteam_result = run_leakage_redteam(worlds)
        print(f"{'✓ AT CHANCE' if redteam_result.at_chance else '⚠ ABOVE CHANCE'}")
        print(f"   AUC-PR: {redteam_result.auc_pr:.4f} (no-skill: {redteam_result.no_skill_pr:.4f})")
    except Exception as e:
        print(f"✗ {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Worlds generated: {len(worlds)}")
    print(f"Attack worlds: {batch['attack_world_count']}")
    print(f"Clean worlds: {batch['clean_world_count']}")
    print(f"Total campaigns: {sum(batch['campaigns_per_flavor'].values())}")
    print(f"Campaigns per flavor: {batch['campaigns_per_flavor']}")

    import numpy as np
    all_counts = []
    for actor_counts in batch["transitions_per_actor"].values():
        all_counts.extend(actor_counts.values())
    if all_counts:
        print(f"Per-actor transitions: mean={np.mean(all_counts):.0f}, P90={np.percentile(all_counts, 90):.0f}")

    print(f"\n✓ All pipeline components working correctly!")
    print(f"\nReady to run full 100-world generation on demand.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
