# SANDBOX_CONTRACT.md — Phase 2/3 Evaluation Unit and World Configuration

**Date:** 2026-07-03  
**Status:** FROZEN — binding contract for Phases 2–5  
**Scope:** attack-instance as evaluation unit, detection metric, world configuration, dev/held-out split

---

## 1. Fundamental Evaluation Unit: Attack Instance (Campaign)

### Concept: AttackInstance (Campaign)

An **attack instance** (hereafter "campaign") is the atomic unit of evaluation. One campaign = one realized attack injected into one actor's trajectory during a single simulation world.

```
AttackInstance (dataclass):
  - actor_id: str          # unhashed, generator-side
  - actor_hash: str        # hashed, evaluator-side
  - t_start: float         # attack onset (seconds in virtual time)
  - t_end: float           # attack end (seconds in virtual time)
  - flavor: AttackType     # which of the 5 attack types (enum)
  - world_seed: int        # which world this campaign belongs to
```

**Key invariant:** One campaign spans one contiguous time interval in one actor's trajectory. The campaign is the unit of ground truth. Exactly one ground-truth label per campaign.

**Detection criterion:** A detector detects this campaign if ANY alert issued by the detector overlaps the campaign's (actor_hash, [t_start, t_end]) interval in time. No pseudo-replication: one campaign counted once, whether it triggers 1 alert or 40 in the budget.

---

## 2. Detection Metric: Per-Campaign Detection @ Fixed Alert Budget

### Primary Metric

**Detection Rate @ K Alerts/Day**

- **K:** fixed alert budget, pre-registered per frozen PREDICTIONS.md Phase 4.  
  Suggestion: K ≈ 9 alerts/day (scaled from Hopper), adjusted to world size.  
  Concrete: if baseline Hopper outputs ~9/day on ~20 typical IAM actors, and our worlds have ~300 actors, then K = 9 × (300/20) = 135 alerts/day. Per detector, per world. (Adjust if needed; lock in FREEZE.md.)

- **Metric:** For each detector, rank all emitted (actor, time_window) alerts by score descending. Select the top K×horizon_days alerts. Compute:
  ```
  detection_rate = (# of campaigns whose [t_start, t_end] overlaps ≥1 alert in top-K) / (total campaigns in world)
  ```
  Averaged over all campaign instances across all held-out worlds.

### Secondary Metrics

- **AUC-PR** (never ROC-AUC; extreme class imbalance makes ROC flattering).
- **Per-flavor breakdown** (detection rate per attack type — did the detector fail systematically on LOTL or smash-and-grab?).
- **Time-to-first-detection** (latency between t_start and first alert overlap).
- **False-positive archetype composition** (which benign archetypes generate FPs — on-call SRE? new hire? uncontrolled FP means leakage).

---

## 3. Attack Flavors and Campaign Count

### Five Attack Flavors (Frozen, §3.2)

Each flavor is a distinct attack type from the closed set:

1. **CredentialTheftLateral** — compromised actor assumes/grants credentials, reaches out-of-history resources.
2. **SlowExfiltration** — low-rate DATA → EXTERNAL drip over weeks; rarity-blind test.
3. **SmashAndGrab** — fast burst IDENTITY → SECRET → DATA → EXTERNAL; sanity anchor (should catch universally).
4. **LivingOffTheLand** — attacks ONLY edges in own history, altering rate/order; per-edge rarity zero signal (physics crown-jewel test).
5. **ServiceAccountHijack** — CI account breaks regularity into SECRET → EXTERNAL.

### Campaign Count and Allocation

- **Target: ~40 campaigns per flavor (200 total campaigns across all worlds).**
  - 40 per flavor × 5 flavors = 200 campaigns.
  - Split: ~30 campaigns per flavor in dev worlds, ~10 per flavor in held-out worlds.
  - (Rationale: enough for per-flavor statistical power in held-out; no overfitting in dev.)

### Campaign Distribution Across Worlds

- **Attack worlds vs. clean worlds:** 50% of all worlds contain attacks; 50% are clean (benign only, for FP characterization).
- **Within attack worlds:** 1–3 actors compromised per attack world (uniform random). Attack flavors chosen by attack_mix distribution (equal weight = 0.2 per flavor).
- **Campaign ground truth:** Each campaign generates exactly one GroundTruthLabel: (actor_hash, t_start, t_end, flavor_name).

---

## 4. World Configuration: Fewer Actors, Longer Histories

### Rationale

Per §3.1 and PREDICTIONS.md Correction 2:
- Physics estimators (P1e, P2) need per-actor rolling windows of ≥80 transitions (P1e) or ≥20 transitions (P2) for stable estimates.
- Real IAM audit logs show median ~8–12 transitions per actor per 15-min window — **data-starved** at fixed-clock granularity.
- **Solution:** Score physics over per-actor rolling windows (N ≥ 80 transitions) instead of fixed 15-min clocks.
- **World design consequence:** Fewer actors per world, longer simulation horizon, each actor accrues many transitions (~1000+).

### Concrete WorldConfig Parameters

```
population_size: 250–300 actors
  (fewer than realistic GCP org ~1000s; concentrates data per actor;
   still enough to exercise archetype diversity and hard negatives)

horizon_days: 80–90 days (virtual)
  (long enough for each actor to accumulate ~1000+ transitions;
   attack onset in middle third leaves pre/post-attack baseline)

event_rate_lambda: tuned so mean transitions per actor ≈ 1000–1500 / horizon
  (suggest: lambda = 30 events/day × population / avg_active_fraction ≈ 1000 events/day total)
  (per-actor activity irregular — some dormant, some chatty; baseline 20% active per day)

archetype_mixture: {
  "Developer": 0.35,
  "DataAnalyst": 0.15,
  "CICDServiceAccount": 0.08,
  "ETLPipelineServiceAccount": 0.08,
  "BackupLogShippingAccount": 0.08,
  "OnCallSRE": 0.12,
  "NewHire": 0.08,
  "RoleChange": 0.04,
  "BreakGlassAdmin": 0.02,
}
  (all > 0; minimum 3 instances per flavor of archetype 4–9 for hard negatives)

action_vocab: ['auth', 'read', 'write', 'invoke', 'grant', 'assume']
  (six action types; rich enough for credential-switch semantics)

zone_labels: ['IDENTITY', 'SECRET', 'DATA', 'COMPUTE', 'LOGGING', 'EXTERNAL', 'ADMIN']
  (seven zones; >= 6 per §2.1; zone-count cannot leak labels)

attack_world_ratio: 0.5
  (50% of all generated worlds contain attacks; 50% clean)

attack_mix: { 
  "CredentialTheftLateral": 0.2,
  "SlowExfiltration": 0.2,
  "SmashAndGrab": 0.2,
  "LivingOffTheLand": 0.2,
  "ServiceAccountHijack": 0.2,
}
  (equal weight; no bias toward any flavor)

attack_compromise_count: random uniform in [1, 3]
  (per attack world, compromise 1–3 actors)

attack_onset_phase: (0.33, 0.67)
  (attacks start uniformly in middle third of horizon; ensures pre/post baseline)
```

---

## 5. Development vs. Held-Out Seed Split

### Strategy: Seed-Based Deterministic Split

All worlds are generated with deterministic seeds. The split is **seed-based** and locked before phase 4:

```
Total world seeds: 100 (generates 100 distinct worlds per config)
  50 attack worlds, 50 clean worlds.

Dev worlds: seeds 0–29 (30 worlds total, ~15 attack + 15 clean)
Held-out worlds: seeds 30–99 (70 worlds total, ~35 attack + 35 clean)
  (or: first 30% dev, last 70% held-out)

Campaign allocation:
  ~30 campaigns per flavor in dev (~6 per flavor in 15 attack worlds = 5 per world avg)
  ~10 campaigns per flavor in held-out (~2 per flavor in 35 attack worlds = ~2.8 per world avg)
```

### Non-Peekable Structure

- **Dev set:** detectors + baselines tuned freely on dev worlds (hyperparameter selection, smoothing, window size, ensemble weights).
- **Held-out set:** loaded ONLY by evaluator module. Detector code paths must have zero access to held-out ground truth (enforce via module imports + test).
- **FREEZE.md:** before first held-out evaluation, write FREEZE.md with all hyperparameters locked. Any post-freeze change invalidates held-out seeds; regenerate with new seed range.

---

## 6. Reuse List (Verified Shapes, No New Components)

All world generation reuses existing, verified implementations from Phase 1/2:

### Reusable Code (No Changes)

- **`bakeoff/worldgen/benign.py`:**  
  ✓ Nine archetype generators (Developer, DataAnalyst, CICDServiceAccount, ETLPipelineServiceAccount, BackupLogShippingAccount, OnCallSRE, NewHire, RoleChange, BreakGlassAdmin).  
  ✓ Tested shapes (semi-Markov, time-reversibility properties, dwell-time distributions).  
  ✓ Reuse as-is; no new archetypes.

- **`bakeoff/worldgen/attacks.py`:**  
  ✓ Five attack overlays (CredentialTheftLateral, SlowExfiltration, SmashAndGrab, LivingOffTheLand, ServiceAccountHijack).  
  ✓ Injection protocol (onset time sampling, event insertion, ground-truth labeling).  
  ✓ Reuse as-is; no new attack types.

- **`bakeoff/worldgen/hard_negatives.py`:**  
  ✓ Three hard-negative structures (ETL twin, on-call storm, novelty flood).  
  ✓ Fairness guarantees (path length, per-edge rarity, zone sequence matching).  
  ✓ Reuse as-is; no new hard negatives.

- **`bakeoff/worldgen/anonymize.py`:**  
  ✓ Anonymization (grepping, salting, deterministic per-seed hashing of actor/resource IDs, opaque action-type tokens, timestamp jitter).  
  ✓ No zone names, archetype names, attack labels in detector-visible artifacts.  
  ✓ Reuse as-is.

- **`bakeoff/worldgen/model.py`:**  
  ✓ Data contracts (RawEvent, AnonymizedEvent, GroundTruth, WorldConfig, World).  
  ✓ Frozen (Correction 2 added rolling-window decision); extend only if new ground-truth schema is needed.

### New Code (Minimum — Phase 3)

- **`bakeoff/worldgen/generator.py`:**  
  orchestrate world generation given (config, seed) → World  
  (compose benign archetypes + attack injection + hard negatives + anonymization)

- **`bakeoff/configs/world_config.py`:**  
  concrete WorldConfig instances matching §4 (one default config, or a small set for Phases 4–5 ablations).

---

## 7. Statistical Framing and Hypothesis Test

### Pre-Registered Decision Criteria

From murmur_physics_falsification_plan.md §1 (verbatim):

| Outcome | Criterion (evaluated on held-out seeds, §7) | Consequence |
|---|---|---|
| **KILL** | Best physics variant fails to exceed baseline B1's detection rate at fixed budget, with 95% CI of paired difference including/below zero — OR wins only on worlds without hard-negative confounds | Cut physics layer. |
| **AUGMENT** | Physics-as-feature inside B1 (H2) beats both B1 alone and P* alone, CI clear of zero, lift survives hard-negative worlds | Physics as feature, not standalone detector. |
| **PROVISIONAL PASS** | Standalone physics variant beats B1 at equal budget, CI clear of zero, across ≥80% of held-out seeds, including hostile-confound worlds | Label: "necessary bar cleared, pending real-data confirmation." |

**Margin threshold:** Paired detection-rate difference ≥ **5 percentage points** at fixed budget (mean across held-out seeds). Smaller lift → KILL (even if statistically nonzero).

**Ties and ambiguity resolve toward KILL.** Burden of proof is on physics.

---

## 8. Phase Sequence and Gating (Reference)

This contract enables the following phase gate structure:

| Phase | What | Gate | Readiness |
|-------|------|------|-----------|
| 1 | Mechanism tests (P1e, P2 estimators) | Tests 1–3 pass; Test 4 yields L_min; Test 5 robust | ✓ LOCKED (PREDICTIONS.md) |
| 2 | Worldgen + fairness audit | Leakage red-team at chance; fairness_audit green on 10 trial seeds | In progress |
| 3 | Baseline B1 calibration on dev worlds | B1 beats B0; B0 FPs dominated by archs 6–9 | Next |
| 4 | Physics + hybrid on dev worlds | Relative-asymmetry formulation locked; tuning complete; FREEZE.md committed | Next |
| 5 | Held-out evaluation (run once) | N ≥ 70 held-out seeds; paired analysis; bootstrap CIs; per-flavor breakdown | Next |
| 6 | Decision memo | Outcome per §7; headline table; FP composition; limitations caveat | Next |

---

## 9. Summary: What This Contract Locks

✓ **Evaluation unit:** Attack instance (actor, t_start, t_end, flavor) — one campaign = one detection label.  
✓ **Detection metric:** Per-campaign detection @ fixed K alerts/day.  
✓ **Attack flavors:** 5 types, ~40 campaigns per flavor (200 total).  
✓ **World config:** 250–300 actors, 80–90 days, ~1000–1500 transitions per actor.  
✓ **Seed split:** Dev = seeds 0–29 (30 worlds), Held-out = seeds 30–99 (70 worlds).  
✓ **Reuse list:** benign.py, attacks.py, hard_negatives.py, anonymize.py, model.py (frozen).  
✓ **Campaign concept:** (actor_id, actor_hash, t_start, t_end, flavor, world_seed).  
✓ **Hypothesis test:** ≥5pp margin; B1 as control; ties→KILL.  

**This contract is the foundation for Phases 3–5. No changes to evaluation unit, metric definition, attack set, or world config without explicit user sign-off.**

---

*Frozen: 2026-07-03*
