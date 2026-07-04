"""
Balanced sandbox world batch generator.

Orchestrates generation of a batch of deterministic worlds (seeded) such that:
1. Attack flavors are balanced across the batch (~40 campaigns per flavor).
2. Each world is reproducible via (config, seed).
3. Worlds are split into dev and held-out sets for non-peekable evaluation.

This is the lean sandbox re-founding per SANDBOX_CONTRACT.md §1–5.
"""

from typing import Dict, List, Tuple, Optional
import numpy as np
from collections import defaultdict

from .model import WorldConfig, World, AttackType
from .world import generate


def generate_balanced_batch(
    config: WorldConfig,
    total_seeds: int = 100,
    target_campaigns_per_flavor: float = 40.0,
    dev_fraction: float = 0.3,
    verbose: bool = True,
) -> Dict:
    """
    Generate a batch of deterministic worlds with balanced campaign allocation.

    Strategy:
    1. Generate worlds sequentially with seeds 0, 1, 2, ..., total_seeds-1.
    2. Track campaigns per flavor across all generated worlds.
    3. Enforce attack_world_ratio (§6.2): ~50% attack worlds, ~50% clean.
    4. Return summary: campaigns per flavor, per-actor transition counts, verification stats.

    Args:
        config: WorldConfig (population_size, archetype_mixture, horizon, etc.).
                attack_world_ratio should be 0.5 (50% attack, 50% clean).
        total_seeds: number of worlds to generate (default 100 → ~50 attack, ~50 clean).
        target_campaigns_per_flavor: target campaign count per attack flavor (default 40 → 200 total).
        dev_fraction: fraction of worlds reserved for development (default 0.3 → seeds 0–29 dev, 30–99 held-out).
        verbose: whether to print summary statistics.

    Returns:
        Dict with keys:
        - "worlds": list of World objects
        - "campaigns_per_flavor": dict mapping flavor -> count (should be balanced ~= target)
        - "campaigns_per_world": dict mapping seed -> count
        - "attack_world_count": number of attack worlds generated
        - "clean_world_count": number of clean worlds generated
        - "transitions_per_actor": dict mapping seed -> list of per-actor transition counts
        - "allocation_summary": human-readable summary of campaign allocation
    """
    worlds: List[World] = []
    campaigns_per_flavor = defaultdict(int)
    campaigns_per_world = {}
    transitions_per_actor_all = {}
    attack_world_count = 0
    clean_world_count = 0

    # Generate worlds
    for seed_idx in range(total_seeds):
        # Create config variant with this seed
        config_this_seed = WorldConfig(
            population_size=config.population_size,
            archetype_mixture=config.archetype_mixture,
            horizon_days=config.horizon_days,
            event_rate_lambda=config.event_rate_lambda,
            attack_mix=config.attack_mix,
            attack_compromise_count=config.attack_compromise_count,
            attack_onset_phase=config.attack_onset_phase,
            action_vocab=config.action_vocab,
            zone_labels=config.zone_labels,
            seed=seed_idx,
            attack_world_ratio=config.attack_world_ratio,
        )

        # Generate world
        world = generate(config_this_seed, seed_idx)
        worlds.append(world)

        # Track campaigns
        campaign_count = len(world.ground_truth.campaigns)
        campaigns_per_world[seed_idx] = campaign_count

        if campaign_count > 0:
            attack_world_count += 1
            # Count per flavor
            for campaign in world.ground_truth.campaigns:
                campaigns_per_flavor[campaign.flavor] += 1
        else:
            clean_world_count += 1

        # Track per-actor transitions
        actor_transition_counts = _count_transitions_per_actor(world)
        transitions_per_actor_all[seed_idx] = actor_transition_counts

        if verbose and (seed_idx + 1) % 10 == 0:
            print(f"  Generated {seed_idx + 1}/{total_seeds} worlds...")

    # Compute statistics
    allocation_summary = _format_allocation_summary(
        campaigns_per_flavor,
        campaigns_per_world,
        attack_world_count,
        clean_world_count,
        transitions_per_actor_all,
        target_campaigns_per_flavor,
    )

    if verbose:
        print(allocation_summary)

    return {
        "worlds": worlds,
        "campaigns_per_flavor": dict(campaigns_per_flavor),
        "campaigns_per_world": campaigns_per_world,
        "attack_world_count": attack_world_count,
        "clean_world_count": clean_world_count,
        "transitions_per_actor": transitions_per_actor_all,
        "allocation_summary": allocation_summary,
        "dev_fraction": dev_fraction,
        "dev_seeds": list(range(int(total_seeds * dev_fraction))),
        "held_out_seeds": list(range(int(total_seeds * dev_fraction), total_seeds)),
    }


def _count_transitions_per_actor(world: World) -> Dict[str, int]:
    """
    Count transitions per actor from anonymized events.

    Returns dict mapping actor_hash -> count of events for that actor.
    """
    counts = defaultdict(int)
    for event in world.anonymized_events:
        counts[event.actor] += 1
    return dict(counts)


def _format_allocation_summary(
    campaigns_per_flavor: Dict[str, int],
    campaigns_per_world: Dict[int, int],
    attack_world_count: int,
    clean_world_count: int,
    transitions_per_actor_all: Dict[int, Dict[str, int]],
    target_campaigns_per_flavor: float,
) -> str:
    """
    Format a human-readable summary of campaign allocation and statistics.
    """
    lines = []
    lines.append("\n" + "=" * 80)
    lines.append("SANDBOX GENERATION SUMMARY")
    lines.append("=" * 80)

    # World counts
    total_worlds = attack_world_count + clean_world_count
    lines.append(f"\nWorld distribution:")
    lines.append(f"  Total worlds: {total_worlds}")
    lines.append(f"  Attack worlds: {attack_world_count} ({100*attack_world_count/total_worlds:.1f}%)")
    lines.append(f"  Clean worlds: {clean_world_count} ({100*clean_world_count/total_worlds:.1f}%)")

    # Campaign counts
    total_campaigns = sum(campaigns_per_flavor.values())
    lines.append(f"\nCampaign counts (target: {target_campaigns_per_flavor:.0f} per flavor):")
    for flavor in sorted(campaigns_per_flavor.keys()):
        count = campaigns_per_flavor[flavor]
        ratio = count / target_campaigns_per_flavor if target_campaigns_per_flavor > 0 else 0
        lines.append(f"  {flavor:30s}: {count:3d} ({ratio:.2f}x target)")
    lines.append(f"  {'TOTAL':30s}: {total_campaigns:3d} ({5 * target_campaigns_per_flavor:.0f} expected)")

    # Per-actor transition statistics
    all_transition_counts = []
    for actor_counts in transitions_per_actor_all.values():
        all_transition_counts.extend(actor_counts.values())

    if all_transition_counts:
        lines.append(f"\nPer-actor transition statistics (across all actors in all worlds):")
        lines.append(f"  Mean transitions per actor: {np.mean(all_transition_counts):.1f}")
        lines.append(f"  Median transitions per actor: {np.median(all_transition_counts):.1f}")
        lines.append(f"  Std dev: {np.std(all_transition_counts):.1f}")
        lines.append(f"  Min: {np.min(all_transition_counts):.0f}, Max: {np.max(all_transition_counts):.0f}")
        lines.append(f"  P25: {np.percentile(all_transition_counts, 25):.0f}")
        lines.append(f"  P50 (median): {np.percentile(all_transition_counts, 50):.0f}")
        lines.append(f"  P75: {np.percentile(all_transition_counts, 75):.0f}")
        lines.append(f"  P90: {np.percentile(all_transition_counts, 90):.0f}")

        # Check if sufficient for physics scoring
        min_for_p1e = 80  # Per PREDICTIONS.md Correction 2
        min_for_p2 = 20
        p90_count = np.percentile(all_transition_counts, 90)
        lines.append(f"\nData sufficiency check:")
        lines.append(f"  P1e needs ≥{min_for_p1e} transitions (P90 = {p90_count:.0f}): " +
                     ("✓ PASS" if p90_count >= min_for_p1e else "✗ WARN"))
        lines.append(f"  P2 needs ≥{min_for_p2} transitions (P90 = {p90_count:.0f}): " +
                     ("✓ PASS" if p90_count >= min_for_p2 else "✗ FAIL"))

    lines.append("\n" + "=" * 80)
    return "\n".join(lines)


if __name__ == "__main__":
    # Example usage for testing
    from bakeoff.configs.world_config import DEFAULT_WORLD_CONFIG

    batch = generate_balanced_batch(
        config=DEFAULT_WORLD_CONFIG,
        total_seeds=10,
        target_campaigns_per_flavor=2.0,  # Small numbers for quick test
        verbose=True,
    )
    print("\nBatch generation complete.")
    print(f"Generated {len(batch['worlds'])} worlds.")
