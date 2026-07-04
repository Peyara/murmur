"""
Default world configuration for Phase 3 sandbox generation.

Matches SANDBOX_CONTRACT.md §4 (Fewer Actors, Longer Histories).
All parameters are frozen per the contract; changes require user sign-off.

---

Rationale (from §4):
- Fewer actors (~250–300) to concentrate transitions per actor (~1000–1500 total per horizon).
- Longer horizon (80–90 days) to allow each actor sufficient history for per-actor rolling-window physics scoring.
- Attack onset in middle third leaves pre/post-attack baseline.
- Balanced attack flavor allocation: ~40 campaigns per flavor across all worlds.
"""

from bakeoff.worldgen.model import WorldConfig, ArchetypeKind

# Default world configuration per SANDBOX_CONTRACT.md §4
DEFAULT_WORLD_CONFIG = WorldConfig(
    population_size=280,  # Mid-range of 250–300; enough for archetype diversity + hard negatives
    archetype_mixture={
        "Developer": 0.35,
        "DataAnalyst": 0.15,
        "CICDServiceAccount": 0.08,
        "ETLPipelineServiceAccount": 0.08,
        "BackupLogShippingAccount": 0.08,
        "OnCallSRE": 0.12,
        "NewHire": 0.08,
        "RoleChange": 0.04,
        "BreakGlassAdmin": 0.02,
    },
    horizon_days=85.0,  # Mid-range of 80–90 days
    event_rate_lambda=30.0,  # Poisson rate: ~30 events/day × population / activity fraction
    # Rationale: ~30 e/day × 280 actors × ~0.12 active fraction ≈ ~1000 events/day total
    # Per-actor over 85 days: ~1000 events/day ÷ 280 actors × avg activity ≈ 1200 transitions per active actor
    attack_mix={
        "CredentialTheftLateral": 0.2,
        "SlowExfiltration": 0.2,
        "SmashAndGrab": 0.2,
        "LivingOffTheLand": 0.2,
        "ServiceAccountHijack": 0.2,
    },
    attack_compromise_count=2,  # Default: 2 actors per attack world (sampled uniformly [1,3] in generator)
    attack_onset_phase=(0.33, 0.67),  # Middle third of horizon
    action_vocab=("auth", "read", "write", "invoke", "grant", "assume"),
    zone_labels=("IDENTITY", "SECRET", "DATA", "COMPUTE", "LOGGING", "EXTERNAL", "ADMIN"),
    seed=0,  # Placeholder; set by generator per world
    attack_world_ratio=0.5,  # 50% attack worlds, 50% clean (per §6.2)
)

"""
---

DEVELOPER NOTES:

1. To generate 100 deterministic worlds (50 attack, 50 clean):
   ```python
   from bakeoff.configs.world_config import DEFAULT_WORLD_CONFIG
   from bakeoff.worldgen.sandbox import generate_balanced_batch

   batch = generate_balanced_batch(
       config=DEFAULT_WORLD_CONFIG,
       total_seeds=100,
       target_campaigns_per_flavor=40,  # ~40 per flavor across all worlds
   )
   # Returns: dict with summary stats, campaigns per flavor, etc.
   ```

2. Event-rate tuning (if needed):
   The event_rate_lambda assumes ~20% of actors active per day. Adjust if real data differs.
   Monitor: mean transitions per actor should be >> 80 (P1e min) or >> 20 (P2 min).

3. Archetype mixture:
   Ensures all 9 archetypes present; minimum 3 instances of archetypes 4–9 (hard negatives).
   Total: 280 actors × 0.02 (BreakGlassAdmin) = 5.6 → ~5 instances (OK; > 3).

4. Horizon and attack onset:
   Horizon = 85 days (2040 hours).
   Attack onset: uniform in [680, 1360] hours (middle third).
   Ensures ≥680h pre-attack history and ≥680h post-attack for baselining.

---
"""
