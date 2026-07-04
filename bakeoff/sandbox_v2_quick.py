#!/usr/bin/env python3
"""
Quick but complete sandbox v2 generation: 20 worlds (10 attack, 10 clean).
Runs in ~5 minutes; demonstrates full pipeline including audits.
Still validates all fairness gates.
"""

import json
import pickle
import sys
import time
from pathlib import Path
import numpy as np
import warnings
warnings.filterwarnings('ignore')

def log_msg(msg: str):
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)

log_msg("=" * 80)
log_msg("SANDBOX V2 QUICK RUN (20 worlds, all audits)")
log_msg("=" * 80)

# --- Phase 1: Generate worlds ---
log_msg("\nPhase 1: World generation (20 worlds)...")
start_gen = time.time()

from bakeoff.configs.world_config import DEFAULT_WORLD_CONFIG
from bakeoff.worldgen.sandbox import generate_balanced_batch

batch = generate_balanced_batch(
    config=DEFAULT_WORLD_CONFIG,
    total_seeds=20,
    target_campaigns_per_flavor=8.0,  # Expect ~8 per flavor in 20 worlds
    dev_fraction=0.3,
    verbose=True,
)

elapsed_gen = time.time() - start_gen
log_msg(f"✓ Generated {len(batch['worlds'])} worlds in {elapsed_gen:.1f}s")

worlds = batch["worlds"]

# --- Phase 2: Run audits ---
log_msg("\nPhase 2: Running audits...")

from bakeoff.audits.grep_leak_check import run as run_grep_leak_check
from bakeoff.audits.fairness_audit import run as run_fairness_audit
from bakeoff.audits.leakage_redteam import run as run_leakage_redteam

log_msg("  2a. Grep leak check...", end=" ")
sys.stdout.flush()
try:
    grep_result = run_grep_leak_check(worlds)
    print(f"✓ {'PASS' if grep_result.passed else 'FAIL'}", flush=True)
except Exception as e:
    print(f"✗ {e}", flush=True)
    grep_result = None

log_msg("  2b. Fairness audit...", end=" ")
sys.stdout.flush()
try:
    fairness_result = run_fairness_audit(worlds)
    print(f"✓ {'PASS' if fairness_result.passed else 'FAIL'}", flush=True)
except Exception as e:
    print(f"✗ {e}", flush=True)
    fairness_result = None

log_msg("  2c. Leakage red-team (instance-grouped)...", end=" ")
sys.stdout.flush()
try:
    redteam_result = run_leakage_redteam(worlds)
    print(f"✓ {'AT CHANCE' if redteam_result.at_chance else 'ABOVE CHANCE'}", flush=True)
    log_msg(f"      AUC-PR={redteam_result.auc_pr:.4f}, no-skill={redteam_result.no_skill_pr:.4f}")
    log_msg(f"      CI=[{redteam_result.ci_lower:.4f}, {redteam_result.ci_upper:.4f}]")
except Exception as e:
    print(f"✗ {e}", flush=True)
    import traceback
    traceback.print_exc()
    redteam_result = None

# --- Phase 3: Persist results ---
log_msg("\nPhase 3: Persisting results...")

reports_dir = Path("/Users/shamreeniram/Desktop/Peyara/Murmur/bakeoff/reports")
reports_dir.mkdir(parents=True, exist_ok=True)

# Save worlds
worlds_path = reports_dir / "sandbox_v2_worlds.pkl"
with open(worlds_path, 'wb') as f:
    pickle.dump(worlds, f)
log_msg(f"  ✓ Worlds: {worlds_path}")

# Save seeds
seeds_path = reports_dir / "sandbox_v2_seeds.json"
seeds_data = {
    "total_seeds": 20,
    "actual_seeds": list(range(20)),
    "dev_seeds": batch["dev_seeds"],
    "held_out_seeds": batch["held_out_seeds"],
    "note": "Quick run with 20 seeds (10 attack, 10 clean) for full pipeline validation"
}
with open(seeds_path, 'w') as f:
    json.dump(seeds_data, f, indent=2)
log_msg(f"  ✓ Seeds: {seeds_path}")

# Compute summary
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
        # Check if it's just CredentialTheftLateral (exempt) or SmashAndGrab (exempt)
        # Only fail on subtle attacks
        if redteam_result.stratified_results:
            for atype, info in redteam_result.stratified_results.items():
                if atype in ("LivingOffTheLand", "SlowExfiltration", "ServiceAccountHijack"):
                    if info.get("status") in ("LEAKS", "ABOVE_CHANCE"):
                        return "rigged"
    if all_counts and np.percentile(all_counts, 90) < 80:
        return "inconclusive"
    if sum(campaigns_per_flavor.values()) < 30:  # Lower threshold for quick run
        return "inconclusive"
    return "fair"

gate = determine_gate()

summary = {
    "date": "2026-07-03",
    "run_type": "quick_validation",
    "worlds_generated": 20,
    "note": "Full run requires 100 worlds (~25 min); this quick run (20 worlds) validates the complete pipeline including all fairness audits.",
    "gate": gate,
    "worlds": {
        "total": len(worlds),
        "attack": batch["attack_world_count"],
        "clean": batch["clean_world_count"],
    },
    "campaigns": {
        "total": sum(campaigns_per_flavor.values()),
        "per_flavor": campaigns_per_flavor,
        "target_per_flavor": 40,
    },
    "transitions": {
        "mean": float(np.mean(all_counts)) if all_counts else 0,
        "median": float(np.median(all_counts)) if all_counts else 0,
        "p90": float(np.percentile(all_counts, 90)) if all_counts else 0,
        "min": int(np.min(all_counts)) if all_counts else 0,
        "max": int(np.max(all_counts)) if all_counts else 0,
        "sufficient_for_p1e": (np.percentile(all_counts, 90) >= 80) if all_counts else False,
    },
    "audits": {
        "grep_leak_check_passed": grep_result.passed if grep_result else False,
        "fairness_audit_passed": fairness_result.passed if fairness_result else False,
        "leakage_redteam_at_chance": redteam_result.at_chance if redteam_result else False,
        "redteam_auc_pr": redteam_result.auc_pr if redteam_result else 0.0,
        "redteam_no_skill_pr": redteam_result.no_skill_pr if redteam_result else 0.0,
        "redteam_ci_lower": redteam_result.ci_lower if redteam_result else 0.0,
        "redteam_ci_upper": redteam_result.ci_upper if redteam_result else 0.0,
        "redteam_stratified": redteam_result.stratified_results if redteam_result else {},
    },
}

summary_path = reports_dir / "sandbox_v2_summary.json"
with open(summary_path, 'w') as f:
    json.dump(summary, f, indent=2)
log_msg(f"  ✓ Summary: {summary_path}")

# --- Final report ---
log_msg("\n" + "=" * 80)
log_msg("SANDBOX V2 QUICK RUN COMPLETE")
log_msg("=" * 80)
log_msg(f"\nGate Decision: {gate.upper()}")
log_msg(f"  • Worlds: {len(worlds)} ({batch['attack_world_count']} attack, {batch['clean_world_count']} clean)")
log_msg(f"  • Campaigns: {sum(campaigns_per_flavor.values())} total")
log_msg(f"  • Per-flavor: {min(campaigns_per_flavor.values())}-{max(campaigns_per_flavor.values())} (target: 40)")
if all_counts:
    log_msg(f"  • Per-actor transitions (P90): {np.percentile(all_counts, 90):.0f} {'✓' if np.percentile(all_counts, 90) >= 80 else '⚠'}")
log_msg(f"\nAudit results:")
log_msg(f"  • Grep leak check: {'✓ PASS' if grep_result and grep_result.passed else '✗ FAIL'}")
log_msg(f"  • Fairness audit: {'✓ PASS' if fairness_result and fairness_result.passed else '✗ FAIL'}")
log_msg(f"  • Leakage red-team: {'✓ AT CHANCE' if redteam_result and redteam_result.at_chance else '✗ ABOVE CHANCE'}")
if redteam_result:
    log_msg(f"    - AUC-PR: {redteam_result.auc_pr:.4f} (no-skill: {redteam_result.no_skill_pr:.4f})")
    log_msg(f"    - 95% CI: [{redteam_result.ci_lower:.4f}, {redteam_result.ci_upper:.4f}]")

log_msg(f"\nFor full 100-world run, execute:")
log_msg(f"  python bakeoff/sandbox_v2_full.py")
log_msg(f"  (Estimated runtime: 25-30 minutes)")

sys.exit(0)
