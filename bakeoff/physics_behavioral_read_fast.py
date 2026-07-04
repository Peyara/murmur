#!/usr/bin/env python3
"""
Physics Behavioral Read — FAST VERSION (5 DEV worlds only).

Quick sanity check of P1e/P2 separation on benign housekeeping vs attacks.
Trades smaller dataset for speed (~2-3 minutes).

Output: reports/physics_behavioral_read.md with observed-vs-predicted analysis.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
import numpy as np
import warnings
warnings.filterwarnings('ignore')

print("\n" + "=" * 80)
print("PHYSICS BEHAVIORAL READ — FAST DEV CHECK (5 worlds)")
print("=" * 80)

# 1. Generate small batch of DEV worlds
print("\n[STEP 1] Generating 5 DEV worlds (seeds 0–4)...", flush=True)

from bakeoff.configs.world_config import DEFAULT_WORLD_CONFIG
from bakeoff.worldgen.model import WorldConfig
from bakeoff.worldgen.world import generate

worlds = []
for seed_idx in range(5):
    # Create a new config with this seed (config is frozen, so we need to make a new one)
    config_this_seed = WorldConfig(
        population_size=DEFAULT_WORLD_CONFIG.population_size,
        archetype_mixture=DEFAULT_WORLD_CONFIG.archetype_mixture,
        horizon_days=DEFAULT_WORLD_CONFIG.horizon_days,
        event_rate_lambda=DEFAULT_WORLD_CONFIG.event_rate_lambda,
        attack_mix=DEFAULT_WORLD_CONFIG.attack_mix,
        attack_compromise_count=DEFAULT_WORLD_CONFIG.attack_compromise_count,
        attack_onset_phase=DEFAULT_WORLD_CONFIG.attack_onset_phase,
        action_vocab=DEFAULT_WORLD_CONFIG.action_vocab,
        zone_labels=DEFAULT_WORLD_CONFIG.zone_labels,
        seed=seed_idx,
        attack_world_ratio=DEFAULT_WORLD_CONFIG.attack_world_ratio,
    )
    world = generate(config_this_seed, seed_idx)
    worlds.append(world)
    print(f"   Seed {seed_idx}: {len(world.anonymized_events)} events, {len(world.ground_truth.campaigns)} campaigns")

print(f"   ✓ Generated {len(worlds)} DEV worlds")

# 2. Extract actor trajectories and score
print("\n[STEP 2] Computing P1e and P2 scores per actor...", flush=True)

from bakeoff.detectors import p1e_excess, p2_flux
from bakeoff.common.trajectory import Trajectory, Transition
from collections import defaultdict

world_actor_scores = {}
for seed_idx, world in enumerate(worlds):
    actor_events = defaultdict(list)

    # Extract events per actor
    for event in world.anonymized_events:
        actor_hash = event.actor
        actor_events[actor_hash].append({
            't': event.t,
            'src': event.src,
            'dst': event.dst,
            'action': event.action,
        })

    # Score each actor
    actor_scores = {}
    for actor, events in actor_events.items():
        if len(events) >= 80:  # Only score if sufficient data
            events_sorted = sorted(events, key=lambda e: e['t'])
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
            traj = Trajectory(transitions)

            try:
                # P1e scores
                p1e_scores = p1e_excess.rolling_scorer_stream(traj, window_size=80, alpha=1.0)

                # P2 score (full trajectory)
                p2_full = p2_flux.score(traj, aggregation='l1')

                # Combine
                for window_time, p1e in p1e_scores:
                    actor_scores[actor] = {
                        'p1e': p1e,
                        'p2': p2_full,
                    }
            except Exception as e:
                pass

    world_actor_scores[seed_idx] = actor_scores

print(f"   ✓ Scored {sum(len(s) for s in world_actor_scores.values())} actors")

# 3. Map actors to archetypes and identify benign housekeeping
print("\n[STEP 3] Identifying benign housekeeping vs attacks...", flush=True)

actor_hash_to_archetype = {}
for world in worlds:
    for event in world.raw_events:
        actor_id = event.actor_id
        for actor in world.actors:
            if actor.id == actor_id:
                if hasattr(world, 'anonymized_mapping') and hasattr(world.anonymized_mapping, 'actor_id_to_hash'):
                    actor_hash = world.anonymized_mapping.actor_id_to_hash.get(actor_id)
                    if actor_hash:
                        actor_hash_to_archetype[actor_hash] = actor.archetype.value
                break

def is_benign_housekeeping(archetype_name: str) -> bool:
    housekeeping = {
        'ETLPipelineServiceAccount',
        'BackupLogShippingAccount',
        'CICDServiceAccount',
    }
    return archetype_name in housekeeping

benign_housekeeping_scores = defaultdict(list)
attack_instance_scores = defaultdict(list)

for seed_idx, world in enumerate(worlds):
    attack_campaigns = world.ground_truth.campaigns
    attack_intervals = {
        (c.actor_hash, (c.t_start, c.t_end)): c.flavor
        for c in attack_campaigns
    }

    actor_scores = world_actor_scores.get(seed_idx, {})

    for actor, score_dict in actor_scores.items():
        archetype = actor_hash_to_archetype.get(actor, 'Unknown')

        # Check if this actor has an attack
        is_attack_actor = any(
            actor == atk_actor
            for atk_actor, _ in attack_intervals.keys()
        )

        if is_attack_actor:
            # This actor has attacks
            flavor = None
            for (atk_actor, (t_start, t_end)), f in attack_intervals.items():
                if atk_actor == actor:
                    flavor = f
                    break
            if flavor:
                attack_instance_scores[flavor].append(score_dict)
        else:
            # Benign actor
            if is_benign_housekeeping(archetype):
                benign_housekeeping_scores['housekeeping'].append(score_dict)
            else:
                benign_housekeeping_scores['other_benign'].append(score_dict)

print(f"   Benign housekeeping: {len(benign_housekeeping_scores.get('housekeeping', []))} windows")
print(f"   Attack instances by flavor:")
for flavor, scores in sorted(attack_instance_scores.items()):
    print(f"     {flavor}: {len(scores)} windows")

# 4. Compute statistics
print("\n[STEP 4] Computing distribution statistics...", flush=True)

def compute_stats(scores_list, field):
    if not scores_list:
        return None
    values = [s[field] for s in scores_list]
    return {
        'count': len(values),
        'mean': float(np.mean(values)),
        'std': float(np.std(values)) if len(values) > 1 else 0.0,
        'min': float(np.min(values)),
        'p25': float(np.percentile(values, 25)),
        'p50': float(np.percentile(values, 50)),
        'p75': float(np.percentile(values, 75)),
        'p90': float(np.percentile(values, 90)),
        'max': float(np.max(values)),
    }

# Analyze separation
housekeeping_p1e = [s['p1e'] for s in benign_housekeeping_scores.get('housekeeping', [])]
housekeeping_p2 = [s['p2'] for s in benign_housekeeping_scores.get('housekeeping', [])]

attack_p1e_all = []
attack_p2_all = []
for scores in attack_instance_scores.values():
    attack_p1e_all.extend([s['p1e'] for s in scores])
    attack_p2_all.extend([s['p2'] for s in scores])

def compute_separation(benign_vals, attack_vals, signal_name):
    if not benign_vals or not attack_vals:
        return None
    benign_mean = np.mean(benign_vals)
    attack_mean = np.mean(attack_vals)
    benign_std = np.std(benign_vals) if len(benign_vals) > 1 else 0.1
    attack_std = np.std(attack_vals) if len(attack_vals) > 1 else 0.1

    pooled_std = np.sqrt((benign_std**2 + attack_std**2) / 2) if benign_std or attack_std else 0.1
    cohens_d = (attack_mean - benign_mean) / pooled_std if pooled_std > 0 else 0.0

    ratio = attack_mean / benign_mean if benign_mean > 0 else (float('inf') if attack_mean > 0 else 1.0)

    return {
        'signal': signal_name,
        'benign_mean': float(benign_mean),
        'attack_mean': float(attack_mean),
        'cohens_d': float(cohens_d),
        'separation_ratio': float(ratio),
    }

sep_p1e = compute_separation(housekeeping_p1e, attack_p1e_all, 'P1e') if housekeeping_p1e and attack_p1e_all else None
sep_p2 = compute_separation(housekeeping_p2, attack_p2_all, 'P2') if housekeeping_p2 and attack_p2_all else None

if sep_p1e:
    print(f"   P1e: benign={sep_p1e['benign_mean']:.4f}, attack={sep_p1e['attack_mean']:.4f}, d={sep_p1e['cohens_d']:.3f}")
if sep_p2:
    print(f"   P2:  benign={sep_p2['benign_mean']:.4f}, attack={sep_p2['attack_mean']:.4f}, d={sep_p2['cohens_d']:.3f}")

# Determine early signal
early_signal = 'physics_flat'
if (sep_p1e and sep_p1e['cohens_d'] > 0.5) or (sep_p2 and sep_p2['cohens_d'] > 0.5):
    early_signal = 'physics_shows_promise'

print(f"\n   ⚡ EARLY SIGNAL: {early_signal}")

# 5. Write report
print("\n[STEP 5] Writing report...", flush=True)

report_lines = [
    "# Physics Behavioral Read — FAST DEV Check",
    "",
    "**Date:** 2026-07-03  ",
    "**Scope:** FAST validation (5 DEV worlds, seeds 0–4)  ",
    "**Status:** EARLY SIGNAL CHECK",
    "",
    "---",
    "",
    "## Summary",
    "",
    f"**Early Signal:** `{early_signal}`",
    "",
    "Quick sanity check of P1e and P2 on a small batch of development worlds. The goal is to assess whether physics signals show any promise in separating attacks from benign housekeeping **before** full tuning and evaluation.",
    "",
    "---",
    "",
    "## Results",
    "",
]

if sep_p1e:
    report_lines.extend([
        "### P1e (Excess Entropy Production)",
        "",
        f"- **Benign housekeeping mean:** {sep_p1e['benign_mean']:.4f}",
        f"- **Attack instances mean:** {sep_p1e['attack_mean']:.4f}",
        f"- **Cohen's d:** {sep_p1e['cohens_d']:.3f}",
        f"- **Separation ratio:** {sep_p1e['separation_ratio']:.2f}×",
        "",
    ])

if sep_p2:
    report_lines.extend([
        "### P2 (Flux Divergence)",
        "",
        f"- **Benign housekeeping mean:** {sep_p2['benign_mean']:.4f}",
        f"- **Attack instances mean:** {sep_p2['attack_mean']:.4f}",
        f"- **Cohen's d:** {sep_p2['cohens_d']:.3f}",
        f"- **Separation ratio:** {sep_p2['separation_ratio']:.2f}×",
        "",
    ])

report_lines.extend([
    "### Per-Attack-Flavor",
    "",
])

for flavor in sorted(attack_instance_scores.keys()):
    scores = attack_instance_scores[flavor]
    p1e_vals = [s['p1e'] for s in scores]
    p2_vals = [s['p2'] for s in scores]

    report_lines.extend([
        f"**{flavor}**",
        f"- Count: {len(scores)}",
        f"- P1e: mean={np.mean(p1e_vals):.4f}, p90={np.percentile(p1e_vals, 90):.4f}" if p1e_vals else f"- P1e: no data",
        f"- P2:  mean={np.mean(p2_vals):.4f}, p90={np.percentile(p2_vals, 90):.4f}" if p2_vals else f"- P2: no data",
        "",
    ])

report_lines.extend([
    "---",
    "",
    "## Predictions Check (Pre-Registered)",
    "",
    "### Prediction (a): P1e ≈ 0 on hard negatives (ETL/backup/break-glass)",
    "",
])

if sep_p1e:
    report_lines.append(f"**Observed:** {sep_p1e['benign_mean']:.4f}")
    report_lines.append("")
    status_a = "✓ MATCH" if sep_p1e['benign_mean'] < 0.05 else "⚠ FLAG" if sep_p1e['benign_mean'] < 0.1 else "✗ MISS"
    report_lines.append(f"**Status:** {status_a}")
else:
    report_lines.append("**Observed:** Insufficient benign housekeeping data")

report_lines.extend([
    "",
    "### Prediction (b): P1e catches LOTL attacks",
    "",
    "**Status:** DEFERRED (requires post-hoc LOTL labeling)",
    "",
    "### Prediction (c): P2 ≥ 1.5× higher on attacks than benign",
    "",
])

if sep_p2:
    report_lines.append(f"**Observed:** {sep_p2['separation_ratio']:.2f}×")
    report_lines.append("")
    status_c = "✓ MATCH" if sep_p2['separation_ratio'] > 1.5 else "⚠ FLAG" if sep_p2['separation_ratio'] > 1.0 else "✗ MISS"
    report_lines.append(f"**Status:** {status_c}")
else:
    report_lines.append("**Observed:** Insufficient data")

report_lines.extend([
    "",
    "---",
    "",
    "## Caveats",
    "",
    "- **FAST version, 5 worlds only** — results exploratory, not validated",
    "- **No tuning yet** — pre-registered defaults only",
    "- **No baseline comparison** — B1 (Hopper) evaluated in Phase 5",
    "- **Window-level aggregation** — Phase 4 detector converts to instance-level scores",
    "",
    "---",
    "",
    f"*Report generated: 2026-07-03*  ",
    f"*Worlds: 5 fast DEV (seeds 0–4)*  ",
])

report_text = "\n".join(report_lines)

reports_dir = Path("/Users/shamreeniram/Desktop/Peyara/Murmur/bakeoff/reports")
reports_dir.mkdir(parents=True, exist_ok=True)
report_path = reports_dir / "physics_behavioral_read.md"

with open(report_path, 'w') as f:
    f.write(report_text)

print(f"   ✓ Report saved to {report_path}")

# Save structured data
data_output = {
    'early_signal': early_signal,
    'housekeeping_vs_attack': {
        'p1e': sep_p1e,
        'p2': sep_p2,
    },
}

data_path = reports_dir / "physics_behavioral_read.json"
with open(data_path, 'w') as f:
    json.dump(data_output, f, indent=2)

print(f"   ✓ Structured data saved to {data_path}")

print("\n" + "=" * 80)
print(f"EARLY SIGNAL: {early_signal.upper()}")
print("=" * 80)
print(f"\nFull report: {report_path}\n")

sys.exit(0)
