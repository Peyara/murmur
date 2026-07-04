# Hard Negatives Implementation — Phase 2

**Date:** 2026-07-03  
**File:** `bakeoff/worldgen/hard_negatives.py`  
**Status:** Implemented  

---

## Overview

Hard negatives (§3.3) are mandatory benign structures that mimic attack shapes, ensuring the landscape is fair and the "cheat detector" (shallow ML on aggregate features) cannot trivially distinguish attacks from benign activity.

The implementation covers three components:

1. **ETL Twin**: Benign ETL accounts running the same shape as IDENTITY → SECRET → DATA → EXTERNAL attacks
2. **On-call Storm**: Time-overlapping on-call SRE windows during attack periods
3. **Novelty Flood**: NewHire and RoleChange events distributed across the horizon

---

## 1. ETL Twin Matching (§3.3, §4.1)

### Design

For each attack with the IDENTITY → SECRET → DATA → EXTERNAL shape (SmashAndGrab, SlowExfiltration):

1. **Path Length Matching** (±1 transition):
   - Attack path length: `L = len(attack_events)`
   - ETL twin path length: `L' ∈ [L-1, L+1]`
   - Purpose: structural equivalence while allowing natural variation from dwell-time sampling

2. **Per-Edge Rarity Percentile Matching** (±1 decile):
   - For each edge in the attack path, compute its rarity percentile among all benign edges:
     ```
     rarity(edge) = 1.0 - frequency(edge)  # 1 = rare, 0 = common
     percentile = percentile_rank(rarity, all_benign_rarities)  # 0.0-1.0
     ```
   - ETL twin edges match attack edge percentiles within ±0.1 (one decile)
   - Purpose: per-edge rarity signal cannot discriminate attack from ETL twin

3. **Zone Sequence Matching** (exact):
   - Attack zone sequence: `[IDENTITY, SECRET, DATA, EXTERNAL]`
   - ETL twin zone sequence: identical
   - Purpose: structural similarity at the zone/functional level

4. **Behavioral Differences** (regulatory):
   - **Rate Profile**: Attack may have variable inter-event times; ETL twin uses fixed schedule
     - `inter_event_time = attack_duration / (path_length + 1)` (uniform spacing)
   - **Regularity**: Attack may cluster events; ETL twin spreads evenly
   - **Relation to History**: Attack is anomalous for the victim actor; ETL twin is normal for a dedicated ETL account

### Implementation Details

```python
def _generate_etl_twin(
    actor_id: str,
    attack_events: List[RawEvent],
    path_length: int,
    zone_sequence: List[Tuple[str, str]],
    attack_edge_percentiles: List[float],
    benign_edge_rarity: Dict[Tuple[str, str, str], float],
    config: WorldConfig,
    t_start: float,
    t_end: float,
    rng: np.random.Generator,
    seed: int,
) -> List[RawEvent]:
```

**Matching Algorithm:**

1. **Per-edge rarity extraction** (in `ensure_hard_negatives`):
   - Compute `benign_edge_rarity` from non-attack events in the world:
     ```python
     benign_edge_rarity = _compute_edge_rarity([e for e in world.raw_events if not e.is_attack])
     ```
   - For each attack edge `(zone_src, zone_dst, action_type)`:
     - Lookup rarity in benign distribution
     - Compute percentile: `percentile = percentile_rank(rarity, all_rarity_values)`
   - Store as `attack_edge_percentiles[]`

2. **ETL twin edge generation** (in `_generate_etl_twin`):
   - For each position `i` in the ETL twin:
     - Retrieve zone pair from `zone_sequence[i % len(zone_sequence)]`
     - Retrieve action type from `attack_events[i]`
     - Generate ETL event with:
       - `zone_src, zone_dst` matching attack
       - `action_type` matching attack
       - Benign resource names (e.g., `etl_source_{actor_id}`)
       - `is_attack=False, attack_type=None`

3. **Verification** (in fairness_audit.py, post-generation):
   - §4.1 gate checks:
     - Path length of all attacks within benign IQR (±1 transition)
     - Per-edge rarity of attack edges matched (±1 decile) by hard-negative benign edges
     - Zone sequence preserved

### Key Programmatic Checks

**1. `_is_etl_shape(events) -> bool`:**
   - Scans zone sequence for IDENTITY → SECRET → DATA → EXTERNAL appearance
   - Returns True if all four zones present in order (not necessarily contiguous)

**2. `_compute_edge_rarity(events) -> Dict[Tuple[str,str,str], float]`:**
   - Counts edge frequency across all benign events
   - Inverts to rarity: `rarity = 1.0 - frequency`
   - Example:
     ```
     (IDENTITY, SECRET, auth): frequency=0.1 → rarity=0.9 (rare)
     (DATA, EXTERNAL, write): frequency=0.05 → rarity=0.95 (very rare)
     ```

**3. `_percentile_rank(value, values) -> float`:**
   - Ranks a rarity value in the distribution of all benign rarities
   - Returns percentile (0.0=min, 1.0=max)
   - Used to match attack edge percentiles to benign equivalents within ±1 decile

---

## 2. On-Call Storm (§3.3, §4.3)

### Design

For each attack window `[t_attack_start, t_attack_end]`:

1. **Time Overlap Guarantee**:
   - Insert on-call SRE window `[t_oncall_start, t_oncall_end]`
   - Constraint: `[t_oncall_start, t_oncall_end] ∩ [t_attack_start, t_attack_end] ≠ ∅`
   - Purpose: temporal co-occurrence cannot be the sole discriminator (per §4.3)

2. **Window Duration** (2–4 hours):
   - `duration = uniform(2h, 4h)` in seconds: `[7200, 14400]`
   - Uniform random within seeded RNG for determinism

3. **Timing** (within ±1 day of attack):
   - Sample oncall start time uniform in `[t_attack_start - 1day, t_attack_end + 1day]`
   - Adjust to ensure overlap with attack window
   - **Overlap enforcement**:
     ```python
     if oncall_window_end <= t_start:
         # No overlap yet; shift start earlier
         oncall_window_start = t_start - random_offset
     ```

4. **Events** (3–5 rare accesses):
   - `num_resources = uniform(3, 6)`
   - Each resource visited at a rare/unexpected time
   - Zones chosen from `[ADMIN, COMPUTE, LOGGING]` (uncommon for human users)
   - Action type uniform from `config.action_vocab`

### Implementation Details

```python
# For each attack window:
oncall_duration = rng.uniform(2*3600, 4*3600)
oncall_window_start = max(
    t_start - one_day,
    rng.uniform(t_start - one_day, t_end)
)
oncall_window_end = min(
    oncall_window_start + oncall_duration,
    horizon_seconds
)

# Enforce overlap
if oncall_window_end <= t_start:
    oncall_window_start = t_start - rng.uniform(0, 3600)
    oncall_window_end = oncall_window_start + oncall_duration
```

**Verification:**
- All on-call windows have `is_attack=False, attack_type=None`
- Time overlap is guaranteed programmatically (not left to chance)
- Actors are OnCallSRE archetype (added to world.actors)

---

## 3. Novelty Flood (§3.3, §4.3)

### Design

Distribute NewHire and RoleChange events to ensure "actor doing something they've never done" is common and benign.

1. **NewHire Exploration** (first ~5 days):
   - Count existing NewHire actors in world
   - Generate 20–40 exploration events for each
   - Broad zone traversal: cycle through all zones
   - Action types varied (use all config.action_vocab)
   - **Purpose**: new employees naturally explore systems; not an attack signal

2. **RoleChange Transition** (±1 day around role_change_time):
   - Count existing RoleChange actors in world
   - Generate 10–20 events around role change
   - Pre-change: initial zone patterns
   - Post-change: different zone patterns (shift indices in zone_labels)
   - **Purpose**: role transitions naturally cause distribution shifts; not an attack signal

### Implementation Details

```python
# NewHire events
for newhire_actor in newhire_actors:
    exploration_duration = 5 * 86400.0  # 5 days
    num_events = rng.integers(20, 40)
    for event_time in exploration_times:
        zone_src = config.zone_labels[i % len(config.zone_labels)]
        zone_dst = config.zone_labels[(i+1) % len(config.zone_labels)]
        # Generate event

# RoleChange events
for rolechange_actor in rolechange_actors:
    change_window = 86400.0  # ±1 day
    for event_time in change_times:
        if event_time > role_change_time:
            # Post-change zones
            src = config.zone_labels[(i+2) % len(...)]
        else:
            # Pre-change zones
            src = config.zone_labels[i % len(...)]
        # Generate event
```

---

## 4. Time Ordering & Determinism

### Time Ordering
- After injecting all hard negatives:
  ```python
  world.raw_events.sort(key=lambda e: (e.t, e.actor_id))
  ```
- Stable sort ensures reproducibility (tie-break by actor_id)

### Determinism
- All RNG seeded with `world.seed + offset`:
  ```python
  rng = np.random.default_rng(world.seed + 0x12345)
  ```
- Offset varies per component (ETL: +1, +2, ...; on-call: +1000, +1001, ...)
- Regenerating world with same `(config, seed)` produces byte-identical `raw_events`

---

## 5. Fairness Gate Integration (§4)

Hard negatives support the three fairness gates (WORLDGEN_CONTRACT §7):

### Gate 1: Structural Equalization
- **Zone counts**: ETL twins + on-call SRE + novelty events use same zone vocabulary
  - Do not introduce new zones → zone count distributions match
- **Node degree**: Hard negatives add actors and edges uniformly
  - No systematic degree difference between attack/clean worlds

### Gate 2: Path Length Matching
- ETL twins have `path_length ± 1 transition`
- All attack paths should fall within benign IQR (tested in fairness_audit.py)

### Gate 3: Per-Edge Rarity Matching
- ETL twin edges matched within ±1 decile of attack edge rarities
- Verified programmatically in `_compute_edge_rarity` + `_percentile_rank`

### Gate 4: Leakage Red-Team (§4.3)
- Hard negatives have `is_attack=False` → no attack labels in events
- All zone/archetype/attack names stripped in anonymization
- Shallow logistic regression on aggregate features (event count, actor count, degree histogram) should fail to distinguish attacks from hard negatives at >chance level

---

## 6. Testing Checklist

### ETL Twin Tests
- [ ] Path length matches attack ±1 transition
- [ ] Zone sequence is IDENTITY → SECRET → DATA → EXTERNAL
- [ ] Per-edge rarity within ±1 decile of attack edges
- [ ] Events spread uniformly across attack window (fixed schedule)
- [ ] `is_attack=False, attack_type=None` for all ETL events

### On-Call Storm Tests
- [ ] Time overlap with attack window guaranteed
- [ ] Duration 2–4 hours
- [ ] 3–5 distinct resources accessed
- [ ] Zones are uncommon (ADMIN, COMPUTE, LOGGING)
- [ ] `is_attack=False, attack_type=None`

### Novelty Flood Tests
- [ ] NewHire events in first 5 days of horizon
- [ ] RoleChange events around role_change_time
- [ ] Broad zone/action variety
- [ ] Temporal spread avoids clustering
- [ ] `is_attack=False, attack_type=None`

### Integration Tests
- [ ] Determinism: `generate(config, seed)` twice → identical `raw_events`
- [ ] Time ordering maintained after hard_negatives injection
- [ ] Fairness audit gates pass on generated worlds
- [ ] Leakage red-team finds no attack signal (AUC-PR ≈ random)

---

## 7. Key Design Decisions

### Decision 1: Fixed Schedule for ETL Twins
- **Why**: Attacks often cluster events; benign ETL is predictable and regular
- **How**: Uniform spacing `inter_event_time = duration / (path_length + 1)`
- **Verification**: Per-event time differences analyzed in fairness audit

### Decision 2: Percentile-Based Rarity Matching (not Absolute)
- **Why**: Absolute rarity values are sensitive to world size; percentiles are scale-free
- **How**: `percentile_rank(rarity, all_benign_rarities)` → rank in [0.0, 1.0]
- **Tolerance**: ±1 decile (±0.1 in percentile space)
- **Verification**: `_percentile_rank()` function validates ranks

### Decision 3: Guaranteed Time Overlap for On-Call (not Probabilistic)
- **Why**: Temporal co-occurrence must be a real confound, not a rare coincidence
- **How**: Explicit guard: if no overlap, shift on-call window earlier
- **Verification**: Overlap checked in fairness audit

---

## 8. References

- **Falsification Plan**: `docs/murmur_physics_falsification_plan.md` §3.3 (hard negatives), §4.1–4.3 (fairness)
- **WORLDGEN_CONTRACT**: `bakeoff/worldgen/WORLDGEN_CONTRACT.md` §4 (fairness audits)
- **Locked Decision 2**: `PREDICTIONS.md` Correction 2 + Addendum (rolling-window scoring, fairness-gate stratification)

---

*Implementation frozen: 2026-07-03*
