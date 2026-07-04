#!/usr/bin/env python3
"""
Full sandbox v2 generation with progress tracking.
Estimated runtime: 25-30 minutes for 100 worlds + audits.
"""

import json
import pickle
import sys
import time
from pathlib import Path
from typing import Dict
import warnings
warnings.filterwarnings('ignore')

def log_progress(msg: str, end: str = "\n"):
    """Print timestamped progress message."""
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}", end=end, flush=True)

def _determine_gate(grep_result, fairness_result, redteam_result, batch, all_counts):
    """Simple gate logic."""
    import numpy as np
    if not grep_result or not grep_result.passed:
        return "rigged"
    if not fairness_result or not fairness_result.passed:
        return "rigged"
    if redteam_result and not redteam_result.at_chance:
        return "rigged"
    if all_counts and np.percentile(all_counts, 90) < 80:
        return "inconclusive"
    if sum(batch["campaigns_per_flavor"].values()) < 150:
        return "inconclusive"
    return "fair"

log_progress("Starting Sandbox V2 generation")

# --- Phase 1: Generate worlds ---
log_progress("Phase 1: World generation (estimated 20 min for 100 worlds)...")

from bakeoff.configs.world_config import DEFAULT_WORLD_CONFIG
from bakeoff.worldgen.sandbox import generate_balanced_batch

try:
    start_gen = time.time()
    batch = generate_balanced_batch(
        config=DEFAULT_WORLD_CONFIG,
        total_seeds=100,
        target_campaigns_per_flavor=40.0,
        dev_fraction=0.3,
        verbose=True,
    )
    elapsed_gen = time.time() - start_gen
    log_progress(f"✓ Generated {len(batch['worlds'])} worlds in {elapsed_gen:.1f}s")
except Exception as e:
    log_progress(f"✗ World generation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

worlds = batch["worlds"]

# --- Phase 2: Audits ---
log_progress("\nPhase 2: Running audits...")

from bakeoff.audits.grep_leak_check import run as run_grep_leak_check
from bakeoff.audits.fairness_audit import run as run_fairness_audit
from bakeoff.audits.leakage_redteam import run as run_leakage_redteam

grep_result = None
fairness_result = None
redteam_result = None

log_progress("  2a. Grep leak check...", end=" ")
try:
    grep_result = run_grep_leak_check(worlds)
    print(f"✓ {'PASS' if grep_result.passed else 'FAIL'}", flush=True)
except Exception as e:
    print(f"✗ {e}", flush=True)

log_progress("  2b. Fairness audit...", end=" ")
try:
    fairness_result = run_fairness_audit(worlds)
    print(f"✓ {'PASS' if fairness_result.passed else 'FAIL'}", flush=True)
except Exception as e:
    print(f"✗ {e}", flush=True)

log_progress("  2c. Leakage red-team...", end=" ")
try:
    redteam_result = run_leakage_redteam(worlds)
    print(f"✓ {'AT_CHANCE' if redteam_result.at_chance else 'ABOVE_CHANCE'}", flush=True)
except Exception as e:
    print(f"✗ {e}", flush=True)
    import traceback
    traceback.print_exc()

# --- Phase 3: Persist results ---
log_progress("\nPhase 3: Persisting results...")

reports_dir = Path("/Users/shamreeniram/Desktop/Peyara/Murmur/bakeoff/reports")
reports_dir.mkdir(parents=True, exist_ok=True)

# Pickle worlds
worlds_path = reports_dir / "sandbox_v2_worlds.pkl"
with open(worlds_path, 'wb') as f:
    pickle.dump(worlds, f)
log_progress(f"  Worlds saved to {worlds_path}")

# Save seeds
seeds_path = reports_dir / "sandbox_v2_seeds.json"
with open(seeds_path, 'w') as f:
    json.dump({
        "total_seeds": 100,
        "dev_seeds": batch["dev_seeds"],
        "held_out_seeds": batch["held_out_seeds"],
    }, f, indent=2)
log_progress(f"  Seeds saved to {seeds_path}")

# Compute summary
import numpy as np
campaigns_per_flavor = batch["campaigns_per_flavor"]
all_counts = []
for actor_counts in batch["transitions_per_actor"].values():
    all_counts.extend(actor_counts.values())

summary = {
    "date": "2026-07-03",
    "gate": _determine_gate(grep_result, fairness_result, redteam_result, batch, all_counts),
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
        "mean": float(np.mean(all_counts)),
        "median": float(np.median(all_counts)),
        "p90": float(np.percentile(all_counts, 90)),
        "min": int(np.min(all_counts)),
        "max": int(np.max(all_counts)),
    },
    "audits": {
        "grep_leak_check": grep_result.passed if grep_result else None,
        "fairness_audit": fairness_result.passed if fairness_result else None,
        "leakage_redteam_at_chance": redteam_result.at_chance if redteam_result else None,
        "redteam_auc_pr": redteam_result.auc_pr if redteam_result else None,
        "redteam_no_skill": redteam_result.no_skill_pr if redteam_result else None,
        "redteam_ci": [redteam_result.ci_lower, redteam_result.ci_upper] if redteam_result else None,
    },
}

summary_path = reports_dir / "sandbox_v2_summary.json"
with open(summary_path, 'w') as f:
    json.dump(summary, f, indent=2)
log_progress(f"  Summary saved to {summary_path}")

# --- Final report ---
log_progress("\n" + "=" * 80)
log_progress("SANDBOX V2 GENERATION COMPLETE")
log_progress("=" * 80)
log_progress(f"Gate: {summary['gate']}")
log_progress(f"Campaigns: {summary['campaigns']['total']} total, {min(campaigns_per_flavor.values())}-{max(campaigns_per_flavor.values())} per flavor")
log_progress(f"Per-actor transitions P90: {summary['transitions']['p90']:.0f}")
log_progress("")

sys.exit(0)
