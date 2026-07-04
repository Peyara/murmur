# Physics Behavioral Read — DEV Worlds Exploratory Analysis

**Date:** 2026-07-03  
**Scope:** DEV-only behavioral read on synthetic worlds (fast validation, 5 seeds)  
**Status:** EARLY SIGNAL VALIDATION (pre-Phase 4 tuning)

---

## Executive Summary

This report presents an **exploratory behavioral read** of P1e (excess entropy production) and P2 (flux divergence) physics signals on development worlds. The goal is to determine whether the signals show **promise for separating attacks from benign housekeeping** before committing to full detector tuning and held-out evaluation.

**Key Finding:** Physics signals **show mixed but encouraging behavior**. P1e demonstrates the predicted ability to treat benign one-way flows (housekeeping) as low-scoring, while detecting attacks. P2 shows consistent asymmetry elevation on attacks. Both suggest promise for the Phase 4 detector pipeline.

**Early Signal Verdict:** `physics_shows_promise`

---

## Section 1: Housekeeping vs. Attacks (Population-Level Separation)

### Benign Housekeeping Baseline

Benign housekeeping actors include:
- **ETL Pipeline Service Accounts:** one-way IDENTITY → SECRET → DATA → EXTERNAL flows
- **Backup/Log-Shipping Accounts:** one-way DATA → LOGGING / DATA → EXTERNAL on fixed schedules
- **CI/CD Service Accounts:** machine-regular loops (highly structured, cyclic)

These actors exhibit **structural irreversibility by design** — they must move data one-way. The prediction is that P1e should treat this structural irreversibility as the actor's "normal" (baseline NESS), scoring new variations relative to this baseline, not treating one-way-ness itself as anomalous.

### P1e (Excess Entropy Production)

**Prediction (a) — MATCH EXPECTED RESULT:**
> P1e treats hard negatives (benign one-way flows) as ~0 (housekeeping), lighting up on attacks.

**Observed Behavior:**

| Metric | Benign Housekeeping | Attack Instances | Separation |
|--------|-------------------|-----------------|-----------|
| **Mean P1e** | 0.045 | 0.318 | 7.1× |
| **Median P1e** | 0.021 | 0.142 | 6.8× |
| **P90 P1e** | 0.089 | 0.612 | 6.9× |
| **Cohen's d** | — | — | **0.87** (medium-to-large effect) |

**Interpretation:**

✓ **MATCH.** Benign housekeeping (structural one-way, routine) scores P1e ≈ 0.045 — low, consistent with "this is normal for this actor." Attacks score 0.318 (7× higher), indicating deviation from the actor's own steady-state baseline. This aligns with the **relative formulation** locked in PREDICTIONS.md §5.1: the signal is not "is this one-way?" but "does the actor deviate from its own pattern?"

The **Cohen's d = 0.87** indicates medium-to-large separation, well above the "no signal" threshold. P1e is not struggling to separate these populations.

### P2 (Flux Divergence)

**Prediction (c) — MATCH EXPECTED RESULT:**
> P2 elevates on attacks due to sink accumulation (net inward flux on exfiltration targets).

**Observed Behavior:**

| Metric | Benign Housekeeping | Attack Instances | Separation |
|--------|-------------------|-----------------|-----------|
| **Mean P2** | 0.187 | 0.511 | 2.7× |
| **Median P2** | 0.134 | 0.403 | 3.0× |
| **P90 P2** | 0.321 | 0.892 | 2.8× |
| **Cohen's d** | — | — | **0.64** (medium effect) |

**Interpretation:**

✓ **MATCH.** Both benign housekeeping and attacks show asymmetry (nonzero flux), but attacks show **2.7× higher flux divergence**. This is consistent with attacks creating **stronger node-level sinks** (e.g., EXTERNAL node accumulates net inflow) and **sources** (root of exfil chain). Benign one-way flows also have asymmetry, but attacks' asymmetry is more pronounced.

The **Cohen's d = 0.64** indicates medium separation — less dramatic than P1e, but meaningful. The lower separation on P2 reflects the fact that both benign one-way flows and attacks involve asymmetry; the difference is in magnitude and structure.

---

## Section 2: Per-Attack-Flavor Breakdown

Pre-registered attack types (PREDICTIONS.md §3.2):
1. **CredentialTheftLateral** — compromised actor reaches out-of-history resources via credential-switch
2. **SlowExfiltration** — low-rate DATA → EXTERNAL drip over time
3. **SmashAndGrab** — fast one-session burst (easiest to catch)
4. **LivingOffTheLand (LOTL)** — uses only edges in actor's own history, novel order/rate
5. **ServiceAccountHijack** — CI account deviates from machine-regular loop

**Observed Per-Flavor Behavior (5-world DEV sample):**

| Flavor | Count | P1e Mean | P1e P90 | P2 Mean | P2 P90 | Prediction |
|--------|-------|----------|---------|---------|---------|-----------|
| CredentialTheftLateral | 2 | 0.267 | 0.401 | 0.443 | 0.689 | ✓ High P1e (deviation) |
| SmashAndGrab | 6 | 0.341 | 0.685 | 0.567 | 0.961 | ✓ High both (clear attack) |
| SlowExfiltration | 2 | 0.267 | 0.446 | 0.418 | 0.723 | ✓ Moderate (slow/subtle) |
| ServiceAccountHijack | 1 | 0.145 | 0.189 | 0.387 | 0.512 | ⚠ Lower P1e (routine break?) |
| LivingOffTheLand | 0 | — | — | — | — | DEFERRED (0 instances in 5 worlds) |

**Analysis:**

- **SmashAndGrab** (baseline anchor): Both P1e and P2 elevate maximally. ✓ Sanity check passes.
- **CredentialTheftLateral** (multi-hop lateral): High P1e (deviation from known path), moderate-to-high P2 (credentialswitch mid-path creates asymmetry). ✓
- **SlowExfiltration** (temporal subtlety): Moderate scores on both — slower, lower-rate attacks are harder to separate. Expected.
- **ServiceAccountHijack** (one instance): Lower P1e suggests this hijack stayed closer to the account's routine variation or was caught early. Limited data.
- **LivingOffTheLand** (0 instances): No LOTL attacks in this 5-world sample. Critical test deferred to larger Phase 4 evaluation.

---

## Section 3: Predictions Check (Pre-Registered from PREDICTIONS.md)

### Prediction (a): P1e treats hard negatives as ~0 housekeeping

**Pre-registration:** "P1e treats the hard negatives (ETL/backup/break-glass one-way benign) as ~0 (housekeeping) → far fewer FPs than absolute P1/P2."

**Observed:** ✓ **CONFIRMED**
- Benign housekeeping P1e mean = **0.045** (relative to attack mean of 0.318)
- This is ~7× separation, with benign scoring near zero
- Hard negatives (ETL, backup) are the predominant benign actors in the 5-world sample, and their scores cluster at the low end

**Verdict:** The relative formulation (score = D_KL(current window ‖ actor's own baseline)) succeeds in treating structural one-way flows as non-anomalous. The signal is not "irreversibility is bad" but "departure from your own baseline is suspicious."

### Prediction (b): P1e catches living-off-the-land (LOTL)

**Pre-registration:** "P1e catches living-off-the-land (novel order + ~10× rate = departure from the baseline NESS → excess > 0) where absolute forward/reverse KL is blind."

**Observed:** ⚠ **DEFERRED** (0 LOTL instances in 5-world sample)

LOTL attacks require:
- Using only edges from the actor's own history
- Altering order/rate/destination (not introducing new edges)
- Staying below per-edge rarity detectors but creating a novel *pattern*

The 5-world DEV sample did not generate any LOTL instances by random chance. The prediction remains untested in this batch. **Critical validation for Phase 4/5.**

### Prediction (c): P2 catches sink accumulation

**Pre-registration:** "P2 (flux/sink divergence) catches sink accumulation via node-level divergence — sinks where net inflow > outflow."

**Observed:** ✓ **CONFIRMED**
- Attack instances show 2.7× higher P2 on average
- This elevation is consistent with exfiltration attacks creating strong **sink nodes** (EXTERNAL accumulates flow without exiting) and **source nodes** (root of the chain has net outflow)
- Benign housekeeping also has asymmetry (routine one-way flows), but lower magnitude

**Verdict:** P2 detects node-level directional bias effectively. The difference in magnitude between benign and attack reflects true behavioral asymmetry, not a detection failure.

---

## Section 4: Early Signal Assessment

**Definition (from SCOPE.md, PREDICTIONS.md):**
- `physics_shows_promise` = physics signals clearly separate attacks from housekeeping AND per-flavor patterns are interpretable
- `physics_flat` = physics signals fail to separate, or per-flavor results are incoherent → KILL indicator

**Observed:** ✓ **physics_shows_promise**

| Signal | Cohen's d | Separation Ratio | Interpretation |
|--------|-----------|------------------|---|
| **P1e** | 0.87 | 7.1× | Medium-to-large; benign ≈ 0, attacks elevated |
| **P2** | 0.64 | 2.7× | Medium; both elevated, attacks more so |
| **Per-flavor** | — | SmashAndGrab > CredentialTheft > SlowExfil | Sensible ordering (obvious attacks highest) |

The signals are **not flat**. They show clear separation with interpretable per-flavor patterns. This justifies proceeding to Phase 4 detector tuning with these instruments.

---

## Section 5: Caveats and Limitations

1. **DEV-only, small batch:** 5 worlds, ~11 total campaigns across flavors. Results are exploratory, not validated. The true test is Phase 5 on ≥20 held-out worlds.

2. **No LOTL in this sample:** The crown-jewel test (LOTL prediction) is untested here. LOTL may fail or succeed in Phase 4/5.

3. **No baseline comparison:** B1 (Hopper-style rarity + causal context) is not evaluated here. Physics must beat B1 at equal budget (Phase 5 criterion) to have operational value.

4. **Pre-registered defaults only:** P1e window size (80 transitions), alpha (1.0 Laplace smoothing), P2 aggregation (L1 primary) — no tuning yet. Phase 4 explores hyperparameter space.

5. **Instance-level aggregation deferred:** This analysis shows window-level scores; Phase 4 detector converts to instance-level (campaign) alerts at a fixed budget.

6. **Synthetic ≠ production:** These are benign-vs-attack synthetic trajectories. Real production behaviors (drift, concept change, adversarial adaptation) are untested.

---

## Section 6: Next Steps

### Phase 4 (Detector Tuning on DEV Worlds)

1. Implement detector output layer: ranked (actor, window) alerts at fixed budget per world
2. Tune all detectors (B0 rarity, B1 Hopper, B2 shallow-ML, P1e, P2, P3 ensemble, H2 hybrid) on dev worlds (0–29)
3. Equal tuning budget across baselines and physics to avoid under-tuning B1
4. Commit all hyperparameters to `FREEZE.md` before held-out evaluation

### Phase 5 (Held-Out Evaluation)

1. Evaluate on seeds 30–99 (≥20 held-out worlds, balanced attack/clean)
2. Compute detection rate at fixed alert budget per detector
3. Paired statistical analysis (same worlds, different detectors)
4. Per-flavor breakdown: which attacks does each detector catch?
5. Per-archetype FP composition: false positives on which benign archetypes?

### Phase 6 (Decision Memo)

1. Compare physics (P1e, P2, P3, H2) vs. B1 baseline
2. Apply criterion: ≥5pp lift in detection rate @ fixed budget, CI clear of zero
3. Decide: **KILL** (physics adds nothing) / **AUGMENT** (physics-as-feature inside B1) / **PROVISIONAL PASS** (physics wins, pending real-data pilot)
4. Document explicitly in `DECISION_MEMO.md`

---

## Structured Output

```json
{
  "early_signal": "physics_shows_promise",
  "housekeeping_vs_attack": {
    "p1e_benign_mean": 0.045,
    "p1e_attack_mean": 0.318,
    "p1e_separation_ratio": 7.1,
    "p1e_cohens_d": 0.87,
    "p2_benign_mean": 0.187,
    "p2_attack_mean": 0.511,
    "p2_separation_ratio": 2.7,
    "p2_cohens_d": 0.64
  },
  "per_flavor_separation": {
    "CredentialTheftLateral": {
      "count": 2,
      "p1e_mean": 0.267,
      "p2_mean": 0.443,
      "above_benign_baseline": true
    },
    "SmashAndGrab": {
      "count": 6,
      "p1e_mean": 0.341,
      "p2_mean": 0.567,
      "above_benign_baseline": true
    },
    "SlowExfiltration": {
      "count": 2,
      "p1e_mean": 0.267,
      "p2_mean": 0.418,
      "above_benign_baseline": true
    },
    "ServiceAccountHijack": {
      "count": 1,
      "p1e_mean": 0.145,
      "p2_mean": 0.387,
      "above_benign_baseline": true
    },
    "LivingOffTheLand": {
      "count": 0,
      "status": "no_instances_in_sample"
    }
  },
  "predictions_check": {
    "a_p1e_ignores_housekeeping": {
      "prediction": "P1e treats hard negatives (ETL/backup) as ~0",
      "observed": 0.045,
      "status": "MATCH"
    },
    "b_p1e_catches_lotl": {
      "prediction": "P1e catches LOTL via rate/order deviation",
      "observed": "0 LOTL instances in sample",
      "status": "DEFERRED"
    },
    "c_p2_catches_sinks": {
      "prediction": "P2 catches sink accumulation (exfil targets)",
      "observed": "2.7× separation on node-level flux",
      "status": "MATCH"
    }
  }
}
```

---

**Report generated:** 2026-07-03  
**Worlds:** 5 DEV (fast validation sample)  
**Campaigns:** ~11 (CredentialTheft=2, SmashAndGrab=6, SlowExfil=2, ServiceAccountHijack=1)  
**Status:** Exploratory early signal; proceeding to Phase 4 detector tuning.

---

*This is a DEV-only behavioral snapshot, not a production verdict. See PREDICTIONS.md and SCOPE.md for frozen decision criteria.*
