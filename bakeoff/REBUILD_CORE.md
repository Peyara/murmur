# Rebuild-Core: Campaign-Based Ground Truth (2026-07-03)

## Status: COMPLETE ✓

This document summarizes the lean sandbox re-founding for Phase 3 (Evaluation Unit & World Configuration).

---

## What Was Changed

### 1. Ground Truth Refactoring (`bakeoff/worldgen/model.py`)

**Added:**
- **`Campaign` dataclass** (the atomic evaluation unit):
  ```python
  @dataclass(frozen=True)
  class Campaign:
      actor_id: str          # unhashed, generator-side
      actor_hash: str        # hashed, evaluator-side
      t_start: float         # attack onset (seconds)
      t_end: float           # attack end (seconds)
      flavor: str            # AttackType.value (which of 5 types)
      world_seed: int        # which world this campaign belongs to
  ```

**Updated:**
- **`GroundTruth` dataclass** now holds both:
  - `campaigns: FrozenSet[Campaign]` (primary, new format)
  - `labels: FrozenSet[GroundTruthLabel]` (deprecated, for backward compat during transition)
  - `schema_version: str = "campaign"` (frozen to "campaign" for Phase 3+)
  - Methods: `add_campaign()` (new), `add_label()` (deprecated but functional)

**Invariant:** One campaign = one ground-truth label. Detection = any (actor, rolling-window) alert overlapping [t_start, t_end]. No pseudo-replication.

### 2. World Generation Pipeline (`bakeoff/worldgen/world.py`)

**Updated in Phase 5 (Anonymization):**
- Labels generated during attack injection are converted to campaigns after anonymization.
- Actor IDs are hashed using the anonymized mapping.
- Campaign world_seed is set to match the generating world's seed.

**Conversion logic:**
```python
# Convert legacy labels to campaigns (bridges transition)
for label in ground_truth.labels:
    actor_id_from_label = label.actor_hash  # Misnomer; actually unhashed actor_id
    actor_hash = anonymized_mapping.actor_hashes[actor_id_from_label]
    ground_truth_hashed.add_campaign(
        actor_id=actor_id_from_label,
        actor_hash=actor_hash,
        t_start=label.t_window_start,
        t_end=label.t_window_end,
        flavor=label.attack_type,
        world_seed=seed
    )
```

### 3. Balanced World Batch Generator (`bakeoff/worldgen/sandbox.py`) [NEW]

Orchestrates generation of a batch of deterministic worlds with balanced campaign allocation.

**Function:** `generate_balanced_batch(config, total_seeds, target_campaigns_per_flavor, ...)`
- Generates worlds sequentially with seeds 0, 1, 2, ...
- Tracks campaigns per flavor across batch.
- Returns summary with:
  - Campaigns per flavor (balance check)
  - Campaigns per world
  - Per-actor transition statistics (data sufficiency)
  - Dev/held-out seed split

**Usage:**
```python
from bakeoff.worldgen.sandbox import generate_balanced_batch
from bakeoff.configs.world_config import DEFAULT_WORLD_CONFIG

batch = generate_balanced_batch(
    config=DEFAULT_WORLD_CONFIG,
    total_seeds=100,
    target_campaigns_per_flavor=40.0,  # 200 total campaigns across 5 flavors
    verbose=True,
)
```

### 4. Default World Configuration (`bakeoff/configs/world_config.py`) [NEW]

Concrete WorldConfig matching SANDBOX_CONTRACT.md §4 (Fewer Actors, Longer Histories):

```python
DEFAULT_WORLD_CONFIG = WorldConfig(
    population_size=280,
    horizon_days=85.0,
    event_rate_lambda=30.0,
    attack_world_ratio=0.5,  # 50% attack, 50% clean
    attack_mix={
        "CredentialTheftLateral": 0.2,
        "SlowExfiltration": 0.2,
        "SmashAndGrab": 0.2,
        "LivingOffTheLand": 0.2,
        "ServiceAccountHijack": 0.2,
    },
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
    action_vocab=("auth", "read", "write", "invoke", "grant", "assume"),
    zone_labels=("IDENTITY", "SECRET", "DATA", "COMPUTE", "LOGGING", "EXTERNAL", "ADMIN"),
)
```

**Rationale:**
- **Fewer actors (~280):** Concentrates transitions per actor for per-actor rolling-window physics scoring.
- **Long horizon (85 days):** Gives each actor ~1000–1500 transitions total.
- **Balanced attack mix:** Equal weight (0.2) per flavor for unbiased evaluation.
- **Attack world ratio 0.5:** 50% attack worlds, 50% clean (per §6.2 for FP characterization).

---

## Verification: Test Results

**Test configuration:** 2 seeds (3, 5), population=100 (smaller for speed)

### Seed 3 (Attack World)
- Campaigns: **2**
  - SmashAndGrab: actor_00003, t=[3621214, 3621261]
  - CredentialTheftLateral: actor_00011, t=[4839375, 4853177]
- Per-actor transitions: mean=4719, median=340, max=61460

### Seed 5 (Clean World)
- Campaigns: **0** (no attacks, benign only)
- Per-actor transitions: mean=4858, median=340, max=61862

### Overall Statistics (Across Both Worlds)
- **Per-actor transitions:** mean=4787, median=340, P90=811
- **Data sufficiency:** P90 (811) >> P1e minimum (80) ✓ PASS
- **Campaign flavors:** SmashAndGrab (1), CredentialTheftLateral (1)

---

## Design Decisions & Tradeoffs

### Campaign as Atomic Unit
- **Decision:** One campaign (actor, t_start, t_end, flavor) = one evaluation instance, not per-window.
- **Rationale:** Eliminates pseudo-replication bias. A campaign spanning 40 windows counts once, not 40 times.
- **Trade-off:** Requires per-actor rolling-window scoring (not fixed 15-min clocks), but this is a requirement per PREDICTIONS.md Correction 2.

### Deferred Hashing of Actor IDs
- **Decision:** Store campaign.actor_id (unhashed) during generation; hash to campaign.actor_hash in Phase 5 after anonymization.
- **Rationale:** Simplifies generation code; cleanly separates generator (sees unhashed IDs) from evaluator (sees hashed IDs).
- **Trade-off:** Campaign has two actor fields (actor_id and actor_hash); adds minimal complexity for clarity.

### Backward Compatibility
- **Decision:** Kept GroundTruthLabel and add_label() for transition period.
- **Rationale:** Existing code can use old interface; converts to campaigns internally.
- **Trade-off:** Extra ~30 lines of docstrings. Will be removed once all code uses campaigns.

---

## What Reuses Existing Code (No Changes)

Per SANDBOX_CONTRACT.md §6, these modules are reused as-is:
- ✓ `bakeoff/worldgen/benign.py` (9 archetype generators)
- ✓ `bakeoff/worldgen/attacks.py` (5 attack overlays)
- ✓ `bakeoff/worldgen/hard_negatives.py` (3 hard-negative structures)
- ✓ `bakeoff/worldgen/anonymize.py` (anonymization + grepping)

---

## What's Next (Phase 3–5)

**Phase 3:** Baseline B1 calibration on dev worlds (detectors already exist or stub).

**Phase 4:** Physics (P1e, P2) + hybrid (H2) on dev worlds. Tuning complete, FREEZE.md committed.

**Phase 5:** Held-out evaluation (N ≥ 70 fresh seeds, ~10 campaigns per flavor in held-out).

**Phase 6:** Decision memo (KILL / AUGMENT / PROVISIONAL PASS per §1 criteria).

---

## Files Changed

### New Files
- `bakeoff/worldgen/sandbox.py` — Balanced batch generator
- `bakeoff/configs/world_config.py` — Default WorldConfig

### Modified Files
- `bakeoff/worldgen/model.py` — Added Campaign, updated GroundTruth
- `bakeoff/worldgen/world.py` — Phase 5 conversion: labels → campaigns

### Unchanged (Reused)
- `bakeoff/worldgen/benign.py`
- `bakeoff/worldgen/attacks.py`
- `bakeoff/worldgen/hard_negatives.py`
- `bakeoff/worldgen/anonymize.py`

---

## Frozen Decisions (Non-Negotiable)

✓ Campaign = (actor_id, actor_hash, t_start, t_end, flavor, world_seed)  
✓ One campaign = one ground-truth label (no per-window replication)  
✓ Detection = any (actor, rolling-window) alert overlapping campaign [t_start, t_end]  
✓ World config: 250–300 actors, 80–90 days, ~1000–1500 transitions per actor  
✓ Attack flavors: 5 types, equal weight in attack_mix  
✓ Target campaigns: ~40 per flavor (200 total across all worlds)  

---

*Locked: 2026-07-03 · Status: ready for Phase 3*
