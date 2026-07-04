# Worldgen Contract — Phase 2 Design (FROZEN)

**Date:** 2026-07-03  
**Status:** Frozen design; awaiting Phase 2 implementation  
**Implementer:** downstream Claude Code session

---

## 0. Mission & Epistemic Frame

This document specifies the **frozen contracts** (data types, function signatures, guarantees) for Phase 2 of the Murmur physics-signal falsification plan.

**Key principle:** Design ≠ implementation. This document defines *what* the worldgen system must produce (contracts, guarantees, test criteria). It does NOT specify *how* to implement it (algorithm choice, optimization, etc. are deferred to Phase 2 implementer).

**Locked decisions (non-negotiable):**
1. **ROLLING-WINDOW SCORING:** Physics is scored over per-actor rolling windows of the last N ≥ 80 transitions, NOT fixed 15-min clock windows (PREDICTIONS.md Correction 2). Therefore, **simulation horizon MUST give each actor >> 80 transitions** — aim for several hundred per active actor so a rolling window of 80 is always fillable.
2. **FAIRNESS-GATE STRATIFICATION:** The §4.3 "cheat detector at chance" requirement is STRICT for subtle attacks (living-off-the-land, slow exfil, service_account_hijack), but the easy anchor (smash_and_grab) is EXEMPT.

---

## 1. Data Contracts (Types & Guarantees)

### 1.1 Generator-Side Contracts (Labeled, with Zones & Archetypes)

#### RawEvent (immutable frozen dataclass)
```python
@dataclass(frozen=True)
class RawEvent:
    t: float                     # timestamp (seconds, monotonic)
    actor_id: str               # unhashed actor ID (generator-side)
    src_resource: str           # unhashed resource ID (generator-side)
    dst_resource: str           # unhashed resource ID (generator-side)
    action_type: str            # semantic action (auth, read, write, invoke, grant, assume)
    zone_src: str               # source zone (GENERATOR ONLY)
    zone_dst: str               # destination zone (GENERATOR ONLY)
    archetype: str              # actor's archetype name (GENERATOR ONLY)
    is_attack: bool             # attack marker (GENERATOR ONLY)
    attack_type: Optional[str]  # attack type name if is_attack, None otherwise (GENERATOR ONLY)
```

**Invariants:**
- `t` strictly increasing across events (time-ordered)
- `action_type` ∈ `config.action_vocab`
- `zone_src`, `zone_dst` ∈ `config.zone_labels` (minimum 6 zones)
- `archetype` ∈ ArchetypeKind enum values
- `is_attack` ⟹ `attack_type` is AttackType enum value; ¬`is_attack` ⟹ `attack_type` is None
- **NEVER shown to detectors; only generator and evaluator see RawEvent**

#### Actor (immutable frozen dataclass)
```python
@dataclass(frozen=True)
class Actor:
    id: str                             # unhashed actor ID (generator-side)
    archetype: ArchetypeKind           # one of nine benign archetypes
    role_change_time: Optional[float]  # time of archetype switch (if applicable)
    metadata: Dict[str, any]           # archetype-specific properties
```

**Invariants:**
- `archetype` is one of: Developer, DataAnalyst, CICDServiceAccount, ETLPipelineServiceAccount, BackupLogShippingAccount, OnCallSRE, NewHire, RoleChange, BreakGlassAdmin
- If `archetype == RoleChange`, `role_change_time` is non-None
- Metadata is archetype-specific (e.g., zone affinity, shift patterns)

#### GroundTruthLabel (immutable frozen dataclass)
```python
@dataclass(frozen=True)
class GroundTruthLabel:
    actor_hash: str         # hashed actor ID (as appears in AnonymizedEvent)
    t_window_start: float   # window start (seconds)
    t_window_end: float     # window end (seconds)
    attack_type: str        # AttackType enum value
```

**Invariants:**
- `actor_hash` is opaque (deterministic hash, stable per seed)
- `t_window_start < t_window_end`
- `attack_type` ∈ AttackType enum values (CredentialTheftLateral, SlowExfiltration, SmashAndGrab, LivingOffTheLand, ServiceAccountHijack)

#### GroundTruth (mutable, for building; frozen at World creation)
```python
@dataclass
class GroundTruth:
    labels: FrozenSet[GroundTruthLabel]
    schema_version: str  # "rolling_window" (locked decision §0)

    def add_label(actor_hash, t_start, t_end, attack_type) -> None:
        """Mutate during world generation; lock after."""
```

**Invariants:**
- `schema_version == "rolling_window"` (per locked decision)
- All labels have consistent schema (all using rolling windows, not fixed clock)

### 1.2 Detector-Visible Contract (Anonymized, No Labels)

#### AnonymizedEvent (immutable frozen dataclass)
```python
@dataclass(frozen=True)
class AnonymizedEvent:
    t: float      # jittered timestamp (deterministic per seed)
    actor: str    # hashed actor ID (opaque, stable per seed)
    src: str      # hashed resource ID (opaque, stable per seed)
    dst: str      # hashed resource ID (opaque, stable per seed)
    action: str   # opaque action token (T001, T002, ...; deterministic per seed)
```

**Critical invariants:**
- **NO zone field; zone_src, zone_dst STRIPPED**
- **NO archetype field; archetype STRIPPED**
- **NO is_attack field; attack labels STRIPPED**
- **NO attack_type field; attack type STRIPPED**
- All string fields opaque (hashed or token-mapped)
- Can be converted to `(t, actor, src, dst, action)` tuple for `Trajectory.Transition` compatibility

**Compatibility with Trajectory:**
AnonymizedEvent must parse cleanly into `bakeoff/common/trajectory.py::Trajectory` via:
```python
transition = Transition(t=e.t, actor=e.actor, src=e.src, dst=e.dst, action=e.action)
trajectory = Trajectory(transitions=[...])
```

### 1.3 Configuration Contract

#### WorldConfig (immutable frozen dataclass)
```python
@dataclass(frozen=True)
class WorldConfig:
    population_size: int                       # [200, 500]
    archetype_mixture: Dict[str, float]       # ArchetypeKind.value -> weight, sums to 1.0
    horizon_days: float                       # [60, 90] virtual days
    event_rate_lambda: float                  # Poisson rate (events/day)
    attack_mix: Dict[str, float]              # AttackType.value -> weight (sums to 1.0 or 0)
    attack_compromise_count: int              # [1, 3] actors to compromise
    attack_onset_phase: Tuple[float, float]   # (t_min_frac, t_max_frac) in [0.33, 0.67]
    action_vocab: Tuple[str, ...]             # frozen tuple, >= 6 actions
    zone_labels: Tuple[str, ...]              # frozen tuple, >= 6 zones
    seed: int                                 # random seed for determinism
```

**Invariants:**
- `population_size` ∈ [200, 500]
- `archetype_mixture` sums to 1.0 and includes ≥ 3 instances of archetypes 4–9 (given `population_size`)
- `horizon_days` ∈ [60, 90]
- `event_rate_lambda` tuned so **each actor accumulates >> 80 transitions** (per locked decision §0)
- `attack_mix` sums to 1.0 or 0 (0 ⟹ clean world; 1.0 ⟹ attack probability distribution)
- `attack_onset_phase` ⊂ [0.33, 0.67] (middle third of horizon)
- `action_vocab` ⊇ {auth, read, write, invoke, grant, assume} (at least 6)
- `zone_labels` ⊇ {IDENTITY, SECRET, DATA, COMPUTE, LOGGING, EXTERNAL, ADMIN} (at least 6)
- **All hashes/tokens/zone mappings NEVER serialized to detector (passed to evaluator-side only)**

### 1.4 World Contract

#### World (complete snapshot)
```python
@dataclass
class World:
    config: WorldConfig
    seed: int
    actors: List[Actor]                    # generator-side
    raw_events: List[RawEvent]             # generator-side, full log with labels
    ground_truth: GroundTruth              # evaluator-side
    anonymized_events: List[AnonymizedEvent]  # detector-visible
    anonymized_mapping: AnonymizedMapping  # evaluator-side (salt, hashes, tokens)
```

**Invariants:**
- `len(anonymized_events) == len(raw_events)` (1:1 correspondence)
- `raw_events` time-ordered, no gaps (some may be contiguous)
- `anonymized_events` time-ordered (jitter may reorder; re-sort if needed)
- All actor IDs in events correspond to an Actor in `actors`
- **raw_events, anonymized_mapping NEVER serialized or shown to detectors**
- `seed` fully determines world (full reproducibility)

**Methods:**
```python
to_detector_visible_dict() -> Dict
    # Returns ONLY: {config, anonymized_events}
    # No raw_events, ground_truth, or anonymized_mapping

to_evaluator_visible_dict() -> Dict
    # Returns: {config, ground_truth, anonymized_events}
    # For use in harness, fairness audits, metric computation
```

---

## 2. Benign Archetype Archetypes (§3.1)

### Archetype Definitions & Semantics

| # | Name | Typical Role | Zone Flow | Reversibility | Key Property |
|---|------|--------------|-----------|--------------|--------------|
| 1 | Developer | Human user | IDENTITY → COMPUTE → DATA(read) → COMPUTE → logout | Near-reversible at distribution | Cyclic daily loop |
| 2 | DataAnalyst | Human analyst | IDENTITY → DATA(read-heavy) → COMPUTE; occasional SECRET | Cyclic | Heavy DATA, rare SECRET |
| 3 | CICDServiceAccount | Build automation | IDENTITY → SECRET → COMPUTE → DATA(write) | Regular loop | Extremely regular, machine-like |
| 4 | ETLPipelineServiceAccount | Data pipeline | IDENTITY → SECRET → DATA(read) → EXTERNAL(write) | **Deliberately one-way (benign)** | Tests "irreversible ≠ malicious" |
| 5 | BackupLogShippingAccount | Backup automation | DATA → LOGGING(write) / DATA → EXTERNAL(write) | **Deliberately one-way (benign)** | Fixed schedule, no IDENTITY |
| 6 | OnCallSRE | On-call engineer | Dormant 95%; during shifts: sudden rare access to never-touched resources | Jumpy, context-breaking | Canonical Hopper false-positive |
| 7 | NewHire | New employee | Days 0–5: exploratory (high zone/resource novelty); then settle into Dev/Analyst pattern | Transitional | Starts with zero history |
| 8 | RoleChange | Career transition | First half: one archetype pattern; mid-horizon switch; second half: different pattern | Structural shift | Tests distribution staleness |
| 9 | BreakGlassAdmin | Emergency admin | Dormant 95%; one rare burst: IDENTITY → ADMIN → SECRET → EXTERNAL, then dormant | Rare, one-way-looking | Benign one-shot access |

**Hard Negatives (Mandatory):**
- Archetypes 4 & 5 must be present in EVERY world (even clean worlds) to punish detectors that equate irreversibility with malice.
- Archetypes 6–9 must have ≥ 3 instances per world to serve as hard negatives.

### Implementation Requirements

**For each archetype, `build_archetype(kind, actor_id, config, seed)` must return:**
- List of RawEvent in time order
- All events span [0, `config.horizon_days * 86400`] seconds
- Each event has `is_attack=False`, `attack_type=None`
- Archetype-specific inter-event distributions (log-normal for humans; Poisson for machines; scheduled for batch jobs)
- Zone sequences match archetype definition
- **Each actor must accumulate >> 80 transitions** (per locked decision §0)

**Determinism:** Given same (kind, actor_id, config, seed), output must be byte-identical.

---

## 3. Attack Archetypes (§3.2)

### Attack Type Definitions

| # | Name | Target Archetype | Path | Duration | Difficulty | Fairness Gate |
|---|------|------------------|------|----------|-----------|---------------|
| 1 | CredentialTheftLateral | Developer, Analyst | IDENTITY → COMPUTE → COMPUTE' → SECRET → DATA | 2–5h | Medium | Has credential-switch analog (grant/assume) |
| 2 | SlowExfiltration | DataAnalyst | DATA(read) → EXTERNAL(write), low rate | 3–6 weeks | Hard | Per-day rarity matches ETL twin |
| 3 | SmashAndGrab | Any | IDENTITY → SECRET → DATA → EXTERNAL | 30–60s | Easy (sanity anchor) | **EXEMPT from cheat-detector fairness (aggregate-visible)** |
| 4 | LivingOffTheLand | ETL, Backup accounts | Reuse actor's own benign edges, different sequence/rate | 2–4 weeks | Hardest (crown-jewel test) | Per-edge rarity zero by construction; tests relative asymmetry |
| 5 | ServiceAccountHijack | CICDServiceAccount | Deviation from machine loop: SECRET → EXTERNAL | 1–3h | Medium | Breaks regularity |

**Onset Timing:** All attacks start uniformly in [0.33 × horizon, 0.67 × horizon] (middle third).

### Implementation Requirements

**For each attack, `inject_attack(attack_type, victim_actor, world_events, config, seed)` must:**
- Insert attack events into `world_events` in time order
- Return ground-truth labels as `(actor_id_unhashed, t_start, t_end, attack_type_str)`
- All injected events: `is_attack=True`, `attack_type=AttackType.value`
- Use only `config.action_vocab` and `config.zone_labels`
- Respect archetype eligibility (validate victim_actor is eligible for this attack type)

**Determinism:** Given same (attack_type, victim_actor, world_events, config, seed), output deterministic.

---

## 4. Hard Negatives (§3.3)

### Hard Negative Types

**ETL Twin:**
- For each SmashAndGrab or SlowExfiltration attack with IDENTITY → SECRET → DATA → EXTERNAL:
  * Create benign ETL account with:
    - Same path length (±1 transition)
    - Same per-edge rarity percentile (±1 decile, per §4.1)
    - Same zone sequence (IDENTITY, SECRET, DATA, EXTERNAL)
  * But different behavioral profile: fixed schedule, steady regularity, legitimate ETL purpose

**On-call Storm:**
- For each attack window [t_attack_start, t_attack_end]:
  * Inject on-call SRE window [t_oncall_start, t_oncall_end] with time overlap
  * Duration: 2–4 hours
  * Events: rare access to 3–5 never-before-touched resources
  * Purpose: ensure temporal co-occurrence cannot be sole discriminator

**Novelty Flood:**
- Distribute NewHire and RoleChange events across horizon (≥ 1 per week or 10% of horizon)
- Initial exploration: broad zone traversal, high per-zone novelty (first ~5 days for NewHire)
- Purpose: ensure "novel access" is common and benign

### Implementation Requirements

**For `ensure_hard_negatives(world)` must:**
- Modify `world.raw_events` in-place, inserting hard-negative events
- May add new Actor objects to `world.actors` (e.g., ETL twins)
- All hard-negative events: `is_attack=False`, `attack_type=None`
- Maintain time ordering
- **Do NOT add labels to `world.ground_truth`** (hard negatives are benign)

**Determinism:** Seeded and deterministic per `world.seed`.

---

## 5. Anonymization Contract (§4.2)

### Anonymization Guarantee

**Input:** List[RawEvent] (with labels, zones, archetypes, unhashed IDs)  
**Output:** Tuple[List[AnonymizedEvent], AnonymizedMapping]

**Transformation:**
1. Hash actor IDs using salted HMAC-SHA256 (salt derived from seed)
2. Hash resource IDs (src_resource, dst_resource) using same salt
3. Map action_type to opaque tokens (T001, T002, ...; deterministic per seed)
4. Jitter timestamps uniformly [t - jitter_window, t + jitter_window] (deterministic per seed)
5. Strip zone_src, zone_dst, archetype, is_attack, attack_type

**AnonymizedMapping (evaluator-side only):**
```python
@dataclass
class AnonymizedMapping:
    salt: str                              # HMAC key
    actor_hashes: Dict[str, str]          # actor_id -> hash
    resource_hashes: Dict[str, str]       # resource_id -> hash
    action_tokens: Dict[str, str]         # action_type -> token
    jitter_amounts: Dict[float, float]    # t -> jitter applied
```

**Invariants:**
- All detectors see ONLY AnonymizedEvent (never AnonymizedMapping or RawEvent)
- No zone name appears in detector-visible artifacts (verified by grep_leak_check)
- No archetype name appears in detector-visible artifacts
- No attack markers in detector-visible artifacts
- Hashes/tokens are opaque and stable per seed (but vary per seed)
- Jitter is deterministic per event (not random per execution)

**Determinism:** `anonymize(raw_events, seed)` called twice with same inputs produces identical output.

---

## 6. Worldgen Pipeline

### Orchestration (world.py)

**`generate(config, seed) -> World`** orchestrates:
1. **Validate config:** population, archetype mixture, horizon, event rate, zones, actions
2. **Initialize actors:** sample archetypes per config.archetype_mixture, verify ≥3 of archetypes 4–9
3. **Generate benign events:** for each actor, call `benign.build_archetype()`; collect raw_events
4. **Decide attack/clean:** random 50/50 (or configurable)
5. **Inject attacks (if attack_world):** for 1–3 compromised actors, call `attacks.inject_attack()`; collect ground_truth labels
6. **Inject hard negatives:** call `hard_negatives.ensure_hard_negatives()`
7. **Anonymize:** call `anonymize.anonymize(raw_events, seed)`
8. **Return World:** fully initialized with config, actors, raw_events, ground_truth, anonymized_events, anonymized_mapping

**Determinism:** `generate(config, seed)` called twice produces byte-identical World (modulo object identity in-memory).

---

## 7. Fairness Audits (§4)

### Audit 1: Structural Equalization (fairness_audit.py)

**Gates:**
1. **Zone count:** K-S test between attack and clean worlds, α=0.01. Must not separate.
2. **Node degree:** K-S test on degree distribution, α=0.01. Must not separate.
3. **Per-zone volumes:** K-S test on event counts per zone, α=0.01. Must not separate.
4. **Attack path length:** All attack paths within benign IQR [Q1, Q3] (±1 transition tolerance).
5. **Per-edge rarity:** Each attack edge matched (±1 decile) by hard-negative benign edge.
6. **Determinism:** Regenerate each world with same (config, seed); verify byte-identical raw_events and ground_truth.

**Pass Criterion:** All gates green. If any fails, world is rigged; discard and regenerate.

### Audit 2: Leakage Red-Team (leakage_redteam.py)

**Test:** Train shallow logistic regression to distinguish attack from benign windows using only world-level features (event count, unique actors, unique resources, degree histogram).

**Pass Criterion:** AUC-PR ≤ no-skill baseline (positive ratio) with 95% CI. If CI clearly above no-skill, landscape is rigged.

**Interpretation:** If a dumb detector cannot distinguish, neither can subtle label-leakage attacks.

### Audit 3: Grep Leak Check (grep_leak_check.py)

**Test:** Scan detector-visible artifacts for strings matching generator vocabulary:
- Zone names (IDENTITY, SECRET, DATA, COMPUTE, LOGGING, EXTERNAL, ADMIN)
- Archetype names (Developer, DataAnalyst, ...)
- Attack names (CredentialTheftLateral, SmashAndGrab, ...)
- Attack markers (is_attack, attack_type, EXFIL, ATTACK, ANOMALY)

**Pass Criterion:** No matches. If found, anonymize.py is broken.

---

## 8. Testing & Verification Checklist

### Per-Archetype Tests
- [ ] Developer: cyclic daily loop, ~80+ transitions over horizon
- [ ] DataAnalyst: DATA-heavy, occasional SECRET, ~80+ transitions
- [ ] CICDServiceAccount: machine-regular (tight inter-event distribution), ~80+ transitions
- [ ] ETLPipelineServiceAccount: benign one-way IDENTITY → SECRET → DATA → EXTERNAL, no reverse, ~80+ transitions
- [ ] BackupLogShippingAccount: benign one-way DATA → LOGGING/EXTERNAL, fixed schedule, ~80+ transitions
- [ ] OnCallSRE: mostly dormant, 2–4 on-call bursts with sudden rare access
- [ ] NewHire: exploratory first 5 days, then settle, ~80+ transitions
- [ ] RoleChange: archetype switch mid-horizon, old distribution stale
- [ ] BreakGlassAdmin: mostly dormant, one rare burst per horizon, ~80+ transitions

### Per-Attack Tests
- [ ] CredentialTheftLateral: reaches out-of-history resource, credential-switch analog
- [ ] SlowExfiltration: per-day rarity matches ETL twin ±1 decile
- [ ] SmashAndGrab: fast single-session, aggregate-visible
- [ ] LivingOffTheLand: all edges exist benignly; only sequence/rate differ; per-edge rarity zero
- [ ] ServiceAccountHijack: breaks machine regularity, compact (3–8 events)

### Per-World Tests
- [ ] Determinism: regenerate with (config, seed), get byte-identical raw_events and ground_truth
- [ ] Transition count: each actor ≥ 80 transitions (per locked decision §0); aim for several hundred
- [ ] Time ordering: all raw_events and anonymized_events time-ordered
- [ ] Anonymization: no zone/archetype/attack labels in anonymized_events; all IDs opaque
- [ ] Fairness gates: structural equalization, leakage at chance, no grep leaks

### Integration Tests
- [ ] Full pipeline: generate(config, seed) produces valid World
- [ ] Audit pipeline: fairness_audit, leakage_redteam, grep_leak_check all pass
- [ ] Reproducibility: call generate() twice, all audits produce identical results

---

## 9. Dependencies Decision

**Added:** scikit-learn (for audits: sklearn.linear_model.LogisticRegression, sklearn.metrics)

**Rationale:** Audits (Phase 2) require ML for:
- Fairness audit: statistical tests (K-S test from scipy)
- Leakage red-team: logistic regression + AUC-PR computation
- These are evaluation/validation tools (not product code), so sklearn justification is clear.

**NOT added to worldgen/generator itself:** Generator uses numpy only (deterministic, lightweight).

---

## 10. Locked Decisions (Recap)

### Decision 1: Rolling-Window Physics Scoring
**§8, POST-RUN ADDENDUM (Correction 2):** Physics is scored over per-actor rolling windows of the last N ≥ 80 transitions, NOT fixed 15-min clock windows. This decouples physics scoring from the 15-min granularity mismatch that caused Correction 2 (P1 needs 80; real IAM median 8–12 per window).

**Implication:** Simulation horizon and event rate MUST be tuned so **each actor accumulates >> 80 transitions** (aim for 200–500 per active actor). This is verified in fairness_audit.

### Decision 2: Fairness-Gate Stratification
**§4.3 + §1 Outcome definition:** The requirement "cheat detector at chance" (§4.3) is STRICT for subtle attacks (living-off-the-land, slow exfil, service_account_hijack) but EXEMPT for easy anchor (smash_and_grab). SmashAndGrab is allowed to be aggregate-visible and is not subject to the strictest fairness constraint.

---

## 11. What Phase 2 Implementer Receives

✅ **Frozen:** All contracts (model.py), function signatures (benign.py, attacks.py, hard_negatives.py, anonymize.py, world.py, audits/*.py), invariants, locked decisions, test checklists.

❌ **NOT frozen:** Algorithm details, smoothing choices, parameter tuning, optimization. Implementer has autonomy to choose:
- How to sample archetype dwell times (log-normal, gamma, exponential; with what parameters?)
- How to structure the graph (scale-free vs. random vs. lattice?)
- How to compute per-edge rarity (frequency vs. percentile?)
- How to match hard negatives structurally (greedy algorithm? ILP?)

---

## 12. Hand-Off Checklist

By end of Phase 2, implementer must deliver:

- [ ] worldgen/model.py: all frozen contracts, immutable & hashable, fully typed
- [ ] worldgen/benign.py: nine archetype generators, tested on unit inputs
- [ ] worldgen/attacks.py: five attack overlays, validated against spec
- [ ] worldgen/hard_negatives.py: three hard-negative injectors, structure verified
- [ ] worldgen/anonymize.py: deterministic hash/jitter pipeline, symmetry checks pass
- [ ] worldgen/world.py: full orchestration, end-to-end integration tests pass
- [ ] audits/fairness_audit.py: all six gates (zone count, degree, volumes, path length, rarity, determinism)
- [ ] audits/leakage_redteam.py: shallow detector + AUC-PR + bootstrap CI
- [ ] audits/grep_leak_check.py: forbidden vocabulary scan
- [ ] 10 trial worlds generated, all audits green
- [ ] Per-actor transition count diagnostic (min/mean/max)
- [ ] Determinism test: generate(config, seed) twice, verify bit-identical
- [ ] PREDICTIONS.md Correction 2 verified: each actor >> 80 transitions
- [ ] Code review: leverage existing Phase 1 codebase (Trajectory, P1/P2 estimators)

---

## 13. References

- **Falsification Plan:** `/Users/shamreeniram/Desktop/Peyara/Murmur/docs/murmur_physics_falsification_plan.md`
- **Phase 1 Predictions:** `/Users/shamreeniram/Desktop/Peyara/Murmur/bakeoff/PREDICTIONS.md`
- **Trajectory Contract:** `/Users/shamreeniram/Desktop/Peyara/Murmur/bakeoff/common/trajectory.py`
- **Phase 1 Tests:** `/Users/shamreeniram/Desktop/Peyara/Murmur/bakeoff/mechanism_tests/test_mechanism.py`

---

*Frozen: 2026-07-03 — Design complete, awaiting Phase 2 implementation*
