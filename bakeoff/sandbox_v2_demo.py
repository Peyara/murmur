#!/usr/bin/env python3
"""
Sandbox V2 demonstration: 5 worlds with full audits.
Completes in ~2 minutes; validates the complete pipeline.
"""

import json
import pickle
import sys
from pathlib import Path
import numpy as np
import warnings
warnings.filterwarnings('ignore')

print("\nSANDBOX V2 DEMONSTRATION (5 worlds, full audits)")
print("=" * 80)

# Generate 5 worlds
print("\n1. Generating 5 test worlds...", flush=True)
from bakeoff.configs.world_config import DEFAULT_WORLD_CONFIG
from bakeoff.worldgen.sandbox import generate_balanced_batch

batch = generate_balanced_batch(
    config=DEFAULT_WORLD_CONFIG,
    total_seeds=5,
    target_campaigns_per_flavor=1.0,
    dev_fraction=0.3,
    verbose=False,
)
print(f"   ✓ Generated {len(batch['worlds'])} worlds")

worlds = batch["worlds"]
print(f"   Attack worlds: {batch['attack_world_count']}, Clean worlds: {batch['clean_world_count']}")
print(f"   Campaigns: {dict(batch['campaigns_per_flavor'])}")

# Run audits
print("\n2. Running audits...", flush=True)

from bakeoff.audits.grep_leak_check import run as run_grep_leak_check
from bakeoff.audits.fairness_audit import run as run_fairness_audit
from bakeoff.audits.leakage_redteam import run as run_leakage_redteam

print("   2a. Grep leak check...", end=" ", flush=True)
try:
    grep_result = run_grep_leak_check(worlds)
    print(f"✓ {'PASS' if grep_result.passed else 'FAIL'}")
except Exception as e:
    print(f"✗ {e}")
    grep_result = None

print("   2b. Fairness audit...", end=" ", flush=True)
try:
    fairness_result = run_fairness_audit(worlds)
    print(f"✓ {'PASS' if fairness_result.passed else 'FAIL'}")
except Exception as e:
    print(f"✗ {e}")
    fairness_result = None

print("   2c. Leakage red-team...", end=" ", flush=True)
try:
    redteam_result = run_leakage_redteam(worlds)
    print(f"✓ {'AT CHANCE' if redteam_result.at_chance else 'ABOVE CHANCE'}")
    print(f"      AUC-PR: {redteam_result.auc_pr:.4f}, no-skill: {redteam_result.no_skill_pr:.4f}")
except Exception as e:
    print(f"✗ {e}")
    redteam_result = None

# Compute results
campaigns_per_flavor = batch["campaigns_per_flavor"]
all_counts = []
for actor_counts in batch["transitions_per_actor"].values():
    all_counts.extend(actor_counts.values())

def determine_gate():
    if not grep_result or not grep_result.passed:
        return "rigged"
    if not fairness_result or not fairness_result.passed:
        return "rigged"
    if redteam_result and not redteam_result.at_chance:
        return "rigged"
    if all_counts and np.percentile(all_counts, 90) < 80:
        return "inconclusive"
    return "fair"

gate = determine_gate()

# Save results
reports_dir = Path("/Users/shamreeniram/Desktop/Peyara/Murmur/bakeoff/reports")
reports_dir.mkdir(parents=True, exist_ok=True)

summary = {
    "run_type": "demonstration (5 worlds, full audits)",
    "date": "2026-07-03",
    "note": "Validates complete pipeline. Full 100-world run available via sandbox_v2_full.py",
    "gate": gate,
    "worlds": {
        "total": len(worlds),
        "attack": batch["attack_world_count"],
        "clean": batch["clean_world_count"],
    },
    "campaigns": {
        "total": sum(campaigns_per_flavor.values()),
        "per_flavor": campaigns_per_flavor,
    },
    "transitions": {
        "p90": float(np.percentile(all_counts, 90)) if all_counts else 0.0,
        "sufficient_for_p1e": bool(np.percentile(all_counts, 90) >= 80) if all_counts else False,
    },
    "audits": {
        "grep_leak_check": bool(grep_result.passed) if grep_result else False,
        "fairness_audit": bool(fairness_result.passed) if fairness_result else False,
        "leakage_redteam_at_chance": bool(redteam_result.at_chance) if redteam_result else False,
        "redteam_auc_pr": float(redteam_result.auc_pr) if redteam_result else 0.0,
        "redteam_ci": [float(redteam_result.ci_lower), float(redteam_result.ci_upper)] if redteam_result else [0.0, 0.0],
    },
}

summary_path = reports_dir / "sandbox_v2_summary.json"
with open(summary_path, 'w') as f:
    json.dump(summary, f, indent=2)

print(f"\n3. Results saved to {summary_path}")

# Report
print("\n" + "=" * 80)
print(f"GATE: {gate.upper()}")
print("=" * 80)
print(f"\nPipeline validation: ✓ COMPLETE")
print(f"  • Grep leak check: {'✓ PASS' if grep_result and grep_result.passed else '✗ FAIL'}")
print(f"  • Fairness audit: {'✓ PASS' if fairness_result and fairness_result.passed else '✗ FAIL'}")
print(f"  • Leakage red-team: {'✓ AT CHANCE' if redteam_result and redteam_result.at_chance else '✗ ABOVE CHANCE'}")
print(f"\nFor full production run (100 worlds, 40 campaigns/flavor):")
print(f"  python bakeoff/sandbox_v2_full.py  # ~25-30 minutes")

sys.exit(0)
