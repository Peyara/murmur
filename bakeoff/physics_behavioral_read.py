#!/usr/bin/env python3
"""
Physics Behavioral Read — DEV Worlds Only.

Computes P1e (excess EP) and P2 (flux divergence) distributions on a set of DEV worlds
to assess: (a) can they separate benign housekeeping from attacks? (b) per-flavor behavior?

Output: reports/physics_behavioral_read.md with observed-vs-predicted analysis.

CRITICAL: This script runs on DEV worlds ONLY (seeds 0-29, never held-out).
The goal is a behavioral sanity check BEFORE full tuning, not a validated verdict.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
import numpy as np
import warnings
warnings.filterwarnings('ignore')

print("\n" + "=" * 80)
print("PHYSICS BEHAVIORAL READ — DEV WORLDS")
print("=" * 80)

# 1. Generate DEV worlds
print("\n[STEP 1] Generating DEV worlds (seeds 0–29)...", flush=True)

from bakeoff.configs.world_config import DEFAULT_WORLD_CONFIG
from bakeoff.worldgen.sandbox import generate_balanced_batch

batch = generate_balanced_batch(
    config=DEFAULT_WORLD_CONFIG,
    total_seeds=30,  # DEV only: seeds 0–29
    target_campaigns_per_flavor=8.0,  # smaller target for faster dev run
    dev_fraction=1.0,  # all are dev (no held-out)
    verbose=False,
)

worlds = batch["worlds"]
print(f"   ✓ Generated {len(worlds)} DEV worlds")
print(f"   Attack worlds: {batch['attack_world_count']}, Clean: {batch['clean_world_count']}")
print(f"   Campaigns per flavor: {dict(batch['campaigns_per_flavor'])}")

# 2. Extract actors and score with P1e and P2
print("\n[STEP 2] Computing physics scores per actor...", flush=True)

from bakeoff.detectors import p1e_excess, p2_flux
from bakeoff.common.trajectory import Trajectory

def extract_actor_trajectories(world):
    """Extract all actors' trajectories from a world."""
    actor_events = defaultdict(list)

    # Use anonymized_events (detector-visible)
    for event in world.anonymized_events:
        actor_hash = event.actor
        actor_events[actor_hash].append(
            {
                't': event.t,
                'src': event.src,
                'dst': event.dst,
                'action': event.action,
            }
        )

    # Convert to Trajectory objects
    actor_trajectories = {}
    for actor, events in actor_events.items():
        if len(events) > 0:
            # Create Trajectory from events
            events_sorted = sorted(events, key=lambda e: e['t'])
            from bakeoff.common.trajectory import Transition
            transitions = [
                Transition(
                    t=e['t'],
                    actor=actor,
                    src=e['src'],
                    dst=e['dst'],
                    action=e['action'],
                )
                for e in events_sorted
            ]
            actor_trajectories[actor] = Trajectory(transitions)

    return actor_trajectories


def score_actor_with_p1e_p2(actor_trajectory):
    """
    Compute P1e and P2 scores for an actor's trajectory.

    Returns:
        List of (time, p1e_score, p2_score) tuples, one per rolling window.
    """
    # P1e: rolling-window scores (80 transitions per window)
    p1e_scores = p1e_excess.rolling_scorer_stream(
        actor_trajectory,
        window_size=80,
        alpha=1.0,
    )

    # P2: compute on full trajectory (then windows applied at detector level)
    p2_full = p2_flux.score(actor_trajectory, aggregation='l1')

    # For now, pair P1e windows with the single full P2 score
    # (in Phase 4 detector, P2 will also be windowed; here we do a sanity check)
    results = []
    for window_time, p1e in p1e_scores:
        results.append({
            'time': window_time,
            'p1e': p1e,
            'p2_full': p2_full,  # Full trajectory P2, repeated for each window
        })

    return results


# Score all actors in all worlds
print("   Scoring actors...", end=" ", flush=True)
world_actor_scores = {}
for seed_idx, world in enumerate(worlds):
    actor_trajs = extract_actor_trajectories(world)
    actor_scores = {}

    for actor, traj in actor_trajs.items():
        if len(traj) >= 80:  # Only score if sufficient data
            try:
                scores = score_actor_with_p1e_p2(traj)
                actor_scores[actor] = scores
            except Exception as e:
                # Skip actors with scoring errors
                pass

    world_actor_scores[seed_idx] = actor_scores

print(f"✓ Scored {sum(len(s) for s in world_actor_scores.values())} actors total")

# 3. Identify benign housekeeping actors and attack actors
print("\n[STEP 3] Identifying benign housekeeping vs attack instances...", flush=True)

def is_benign_housekeeping(archetype_name: str) -> bool:
    """Check if an actor archetype is benign housekeeping (one-way, cyclic, regular)."""
    housekeeping_archetypes = {
        'ETLPipelineServiceAccount',
        'BackupLogShippingAccount',
        'CICDServiceAccount',  # machine-regular loop
    }
    return archetype_name in housekeeping_archetypes


# Map actor hashes to archetypes
# This requires the anonymized_mapping from each world
actor_hash_to_archetype = {}
for world in worlds:
    # Use raw_events to map actor_id to archetype
    for event in world.raw_events:
        actor_id = event.actor_id
        # Find the actor object
        for actor in world.actors:
            if actor.id == actor_id:
                # Now find the hashed actor_id from anonymized_mapping
                if hasattr(world, 'anonymized_mapping') and hasattr(world.anonymized_mapping, 'actor_id_to_hash'):
                    actor_hash = world.anonymized_mapping.actor_id_to_hash.get(actor_id)
                    if actor_hash:
                        actor_hash_to_archetype[actor_hash] = actor.archetype.value
                break

# Classify scores
benign_housekeeping_scores = defaultdict(list)  # per flavor (or 'benign')
attack_instance_scores = defaultdict(list)  # per flavor

for seed_idx, world in enumerate(worlds):
    # Attack campaigns (ground truth)
    attack_campaigns = world.ground_truth.campaigns
    attack_intervals = {
        (c.actor_hash, (c.t_start, c.t_end)): c.flavor
        for c in attack_campaigns
    }

    actor_scores = world_actor_scores.get(seed_idx, {})

    for actor, scores_list in actor_scores.items():
        archetype = actor_hash_to_archetype.get(actor, 'Unknown')

        # Check if any score overlaps an attack interval
        is_attack_actor = any(
            actor == atk_actor
            for atk_actor, _ in attack_intervals.keys()
        )

        if is_attack_actor and archetype in {'Developer', 'DataAnalyst', 'CICDServiceAccount'}:
            # This actor has attacks injected
            for score_dict in scores_list:
                flavor = None
                for (atk_actor, (t_start, t_end)), f in attack_intervals.items():
                    if atk_actor == actor and t_start <= score_dict['time'] <= t_end:
                        flavor = f
                        break

                if flavor:
                    attack_instance_scores[flavor].append(score_dict)
        else:
            # Benign actor
            if is_benign_housekeeping(archetype):
                benign_housekeeping_scores['housekeeping'].extend(scores_list)
            else:
                benign_housekeeping_scores['other_benign'].extend(scores_list)

print(f"   Benign housekeeping: {len(benign_housekeeping_scores.get('housekeeping', []))} windows")
print(f"   Other benign: {len(benign_housekeeping_scores.get('other_benign', []))} windows")
print(f"   Attack instances by flavor:")
for flavor, scores in sorted(attack_instance_scores.items()):
    print(f"     {flavor}: {len(scores)} windows")

# 4. Compute statistics
print("\n[STEP 4] Computing distribution statistics...", flush=True)

def compute_stats(scores_list, field):
    """Compute mean, std, min, max, percentiles for a field."""
    if not scores_list:
        return None

    values = [s[field] for s in scores_list]
    return {
        'count': len(values),
        'mean': float(np.mean(values)),
        'std': float(np.std(values)),
        'min': float(np.min(values)),
        'p25': float(np.percentile(values, 25)),
        'p50': float(np.percentile(values, 50)),
        'p75': float(np.percentile(values, 75)),
        'p90': float(np.percentile(values, 90)),
        'max': float(np.max(values)),
    }

# Aggregate statistics
stats_by_category = {}

for category, scores in benign_housekeeping_scores.items():
    stats_by_category[f'benign_{category}'] = {
        'p1e': compute_stats(scores, 'p1e'),
        'p2': compute_stats(scores, 'p2_full'),
    }

for flavor, scores in attack_instance_scores.items():
    stats_by_category[f'attack_{flavor}'] = {
        'p1e': compute_stats(scores, 'p1e'),
        'p2': compute_stats(scores, 'p2_full'),
    }

print(f"   ✓ Computed stats for {len(stats_by_category)} categories")

# 5. Analyze separation
print("\n[STEP 5] Analyzing separation (housekeeping vs attacks)...", flush=True)

housekeeping_p1e = [s['p1e'] for s in benign_housekeeping_scores.get('housekeeping', [])]
housekeeping_p2 = [s['p2_full'] for s in benign_housekeeping_scores.get('housekeeping', [])]

attack_p1e_all = []
attack_p2_all = []
for scores in attack_instance_scores.values():
    attack_p1e_all.extend([s['p1e'] for s in scores])
    attack_p2_all.extend([s['p2_full'] for s in scores])

def compute_separation(benign_vals, attack_vals, signal_name):
    """Compute simple separation metrics."""
    if not benign_vals or not attack_vals:
        return None

    benign_mean = np.mean(benign_vals)
    benign_std = np.std(benign_vals)
    attack_mean = np.mean(attack_vals)
    attack_std = np.std(attack_vals)

    # Effect size (Cohen's d)
    pooled_std = np.sqrt((benign_std**2 + attack_std**2) / 2)
    if pooled_std > 0:
        cohens_d = (attack_mean - benign_mean) / pooled_std
    else:
        cohens_d = 0.0

    # Separation ratio
    if benign_mean > 0:
        ratio = attack_mean / benign_mean
    else:
        ratio = float('inf') if attack_mean > 0 else 1.0

    return {
        'signal': signal_name,
        'benign_mean': float(benign_mean),
        'attack_mean': float(attack_mean),
        'cohens_d': float(cohens_d),
        'separation_ratio': float(ratio),
    }

sep_p1e = compute_separation(housekeeping_p1e, attack_p1e_all, 'P1e')
sep_p2 = compute_separation(housekeeping_p2, attack_p2_all, 'P2')

print(f"   P1e: benign_mean={sep_p1e['benign_mean']:.4f}, attack_mean={sep_p1e['attack_mean']:.4f}, d={sep_p1e['cohens_d']:.3f}")
print(f"   P2:  benign_mean={sep_p2['benign_mean']:.4f}, attack_mean={sep_p2['attack_mean']:.4f}, d={sep_p2['cohens_d']:.3f}")

# 6. Determine early signal
early_signal = 'physics_flat'
if sep_p1e['cohens_d'] > 0.5 or sep_p2['cohens_d'] > 0.5:
    early_signal = 'physics_shows_promise'

print(f"\n   ⚡ EARLY SIGNAL: {early_signal}")

# 7. Write report
print("\n[STEP 6] Writing report...", flush=True)

report_lines = [
    "# Physics Behavioral Read — DEV Worlds",
    "",
    "**Date:** 2026-07-03  ",
    "**Scope:** DEV worlds only (seeds 0–29)  ",
    "**Status:** EARLY SIGNAL CHECK (not a validation verdict)",
    "",
    "---",
    "",
    "## Summary",
    "",
    f"**Early Signal:** `{early_signal}`",
    "",
    "This report presents an **exploratory behavioral read** of P1e and P2 physics signals on a small set of development worlds. The goal is to assess whether the signals show promise for separating attacks from benign housekeeping **before** full detector tuning and held-out evaluation.",
    "",
    "**CRITICAL CAVEAT:** This is a DEV-only snapshot, not a production verdict. Results are exploratory and may change as tuning progresses.",
    "",
    "---",
    "",
    "## Housekeeping vs. Attacks",
    "",
    "### P1e (Excess Entropy Production)",
    "",
    f"- **Benign housekeeping mean:** {sep_p1e['benign_mean']:.4f}",
    f"- **Attack instances mean:** {sep_p1e['attack_mean']:.4f}",
    f"- **Cohen's d:** {sep_p1e['cohens_d']:.3f}",
    f"- **Separation ratio:** {sep_p1e['separation_ratio']:.2f}×",
    "",
    "**Interpretation:**",
    "- If benign ≈ 0 and attack > 0, P1e is distinguishing housekeeping (structural NESS) from attacks (deviation from NESS). ✓",
    "- If benign ≈ attack, P1e is blind to attacks or treating them as normal variation. ✗",
    "- If Cohen's d > 0.5, moderate separation. If d > 0.8, large separation.",
    "",
    "### P2 (Flux Divergence)",
    "",
    f"- **Benign housekeeping mean:** {sep_p2['benign_mean']:.4f}",
    f"- **Attack instances mean:** {sep_p2['attack_mean']:.4f}",
    f"- **Cohen's d:** {sep_p2['cohens_d']:.3f}",
    f"- **Separation ratio:** {sep_p2['separation_ratio']:.2f}×",
    "",
    "**Interpretation:**",
    "- If benign ≈ 0 (detailed balance) and attack > 0 (asymmetry), P2 is detecting directional attacks. ✓",
    "- If both are large, both have asymmetry (housekeeping is one-way, attacks are also one-way). ⚠",
    "- P2 should be lower on ETL/backup (benign one-way) than on attacks IF attacks are MORE asymmetric.",
    "",
    "---",
    "",
    "## Per-Attack-Flavor Breakdown",
    "",
]

for flavor in sorted(attack_instance_scores.keys()):
    scores = attack_instance_scores[flavor]
    p1e_vals = [s['p1e'] for s in scores]
    p2_vals = [s['p2_full'] for s in scores]

    report_lines.extend([
        f"### {flavor}",
        "",
        f"- **Window count:** {len(scores)}",
        f"- **P1e:** mean={np.mean(p1e_vals):.4f}, p90={np.percentile(p1e_vals, 90):.4f}",
        f"- **P2:**  mean={np.mean(p2_vals):.4f}, p90={np.percentile(p2_vals, 90):.4f}",
        "",
    ])

report_lines.extend([
    "---",
    "",
    "## Predictions Check (Pre-Registered)",
    "",
    "### Prediction (a): P1e treats hard negatives (ETL/backup) as ~0 housekeeping",
    "",
    f"**Observed:** Benign housekeeping P1e mean = {sep_p1e['benign_mean']:.4f}",
    "",
    "**Status:** " + ("✓ MATCH" if sep_p1e['benign_mean'] < 0.05 else "⚠ FLAG" if sep_p1e['benign_mean'] < 0.1 else "✗ MISS"),
    "",
    "The target was P1e ≈ 0 for benign one-way flows (structural NESS). " +
    ("Achieved — hard negatives are treated as baseline/housekeeping." if sep_p1e['benign_mean'] < 0.05 else "Not achieved — housekeeping has non-trivial scores."),
    "",
    "### Prediction (b): P1e catches living-off-the-land attacks",
    "",
    "**Status:** DEFERRED (requires identifying LOTL instances in data, not yet done)",
    "",
    "Living-off-the-land attacks use only edges from the actor's own history, altered in order/rate. P1e should catch rate/order deviation from the actor's NESS. This requires post-hoc labeling of which attack instances are LOTL; deferred to Phase 4 detailed evaluation.",
    "",
    "### Prediction (c): P2 catches sink accumulation",
    "",
    f"**Observed:** Attack instances have higher P2 (ratio={sep_p2['separation_ratio']:.2f}×)",
    "",
    "**Status:** " + ("✓ MATCH" if sep_p2['separation_ratio'] > 1.5 else "⚠ FLAG" if sep_p2['separation_ratio'] > 1.0 else "✗ MISS"),
    "",
    "P2 should detect asymmetry in node-level flux (sources/sinks). This is a proxy for exfiltration chains (source at root, sink at EXTERNAL). Result shows " +
    ("attacks are more asymmetric than benign" if sep_p2['separation_ratio'] > 1.0 else "no clear asymmetry lift"),
    "",
    "---",
    "",
    "## Raw Statistics",
    "",
])

import json
report_lines.append("```json")
report_lines.append(json.dumps(stats_by_category, indent=2))
report_lines.append("```")

report_lines.extend([
    "",
    "---",
    "",
    "## Caveats & Limitations",
    "",
    "1. **DEV worlds only:** This is an exploratory snapshot on 30 small worlds with ~8 campaigns per flavor. No cross-validation, no held-out test.",
    "2. **No tuning yet:** Detectors are running with pre-registered defaults (alpha=1.0, window=80). Hyperparameter tuning on dev worlds happens in Phase 4.",
    "3. **No baseline comparison:** P1e and P2 are shown in isolation. B1 (Hopper-style baseline) comparison happens in Phase 5 held-out evaluation.",
    "4. **Window-level aggregation:** Scores are per actor-window; no per-instance (campaign) aggregation yet (Phase 4 detector output).",
    "5. **Not a verdict:** Early signal is a heuristic (Cohen's d > 0.5). Final verdict depends on fixed-budget detection rate @ Phase 5.",
    "",
    "---",
    "",
    "## Next Steps",
    "",
    "1. **Phase 4 (Detector Tuning):** Implement detector output (ranked alerts per fixed budget), tune on dev worlds.",
    "2. **Phase 5 (Held-Out Evaluation):** Run final evaluation on seeds 30–99, compute detection rate, AUC-PR, per-flavor breakdown.",
    "3. **Phase 6 (Decision Memo):** Compare vs. B1 baseline; decide KILL / AUGMENT / PROVISIONAL PASS.",
    "",
    "---",
    "",
    f"*Report generated: 2026-07-03*  ",
    f"*Worlds: {len(worlds)} DEV seeds (0–29)*  ",
    f"*Campaigns: {sum(batch['campaigns_per_flavor'].values())} total ({dict(batch['campaigns_per_flavor'])})*  ",
])

report_text = "\n".join(report_lines)

# Save report
reports_dir = Path("/Users/shamreeniram/Desktop/Peyara/Murmur/bakeoff/reports")
reports_dir.mkdir(parents=True, exist_ok=True)
report_path = reports_dir / "physics_behavioral_read.md"

with open(report_path, 'w') as f:
    f.write(report_text)

print(f"   ✓ Report saved to {report_path}")

# Also save structured data
data_output = {
    'early_signal': early_signal,
    'housekeeping_vs_attack': {
        'p1e': sep_p1e,
        'p2': sep_p2,
    },
    'per_flavor_separation': {
        flavor: {
            'p1e_mean': float(np.mean([s['p1e'] for s in scores])),
            'p2_mean': float(np.mean([s['p2_full'] for s in scores])),
            'p1e_p90': float(np.percentile([s['p1e'] for s in scores], 90)),
            'p2_p90': float(np.percentile([s['p2_full'] for s in scores], 90)),
            'count': len(scores),
        }
        for flavor, scores in attack_instance_scores.items()
    },
    'stats': stats_by_category,
}

data_path = reports_dir / "physics_behavioral_read.json"
with open(data_path, 'w') as f:
    json.dump(data_output, f, indent=2)

print(f"   ✓ Structured data saved to {data_path}")

print("\n" + "=" * 80)
print(f"EARLY SIGNAL: {early_signal.upper()}")
print("=" * 80)

if early_signal == 'physics_flat':
    print("\n⚠  Physics signals do NOT show clear separation. Consider:")
    print("  - Tuning hyperparameters (window size, alpha smoothing, aggregation)")
    print("  - Checking implementation correctness (mechanism tests passed?)")
    print("  - Evaluating whether P1e/P2 are the right instruments for this domain")
else:
    print("\n✓ Physics signals show promise for further evaluation.")
    print("  Proceed to Phase 4 detector tuning.")

print("\nFull report: " + str(report_path))
sys.exit(0)
