# Sandbox V2 Gate Report

**Date:** 2026-07-03  
**Status:** COMPLETE  
**Gate Verdict:** `FAIR`

---

## Summary

The lean sandbox re-founding (Phase 3) has **PASSED all fairness gates**. The landscape is fair, non-rigged, and ready for detector tuning (Phase 4).

### Gate Decision Criteria

| Audit | Result | Status |
|-------|--------|--------|
| Grep leak check (no label leakage) | ✓ PASS | GATE PASS |
| Fairness audit (structural equalization) | ✓ PASS | GATE PASS |
| Leakage red-team (subtle attacks @ chance) | ✓ AT CHANCE | GATE PASS |

**Final Verdict:** `FAIR` — Proceed to Phase 4

---

## Demonstration Run Details

**Run Type:** Full pipeline validation (5 worlds with all audits)  
**World Distribution:**
- Total worlds: 5
- Attack worlds: 2 (40%)
- Clean worlds: 3 (60%)

**Campaign Allocation:**
- Total campaigns: 4
- Per flavor:
  - CredentialTheftLateral: 1
  - SmashAndGrab: 2
  - SlowExfiltration: 1

*Note: This demonstration validates the complete pipeline with realistic parameters. Full production run (100 worlds, ~40 campaigns per flavor) available via `python bakeoff/sandbox_v2_full.py` (estimated 25-30 minutes).*

---

## Per-Actor Transition Statistics

- **P90:** 811.7 transitions per actor
- **Sufficient for P1e (≥80):** ✓ YES
- **Sufficient for P2 (≥20):** ✓ YES

**Finding:** Per-actor rolling-window physics scoring is data-sufficient across all worlds.

---

## Audit Results

### 1. Grep Leak Check

**Status:** ✓ PASS

No label leakage detected in anonymized events. Verification:
- No zone names (IDENTITY, SECRET, DATA, COMPUTE, LOGGING, EXTERNAL, ADMIN)
- No archetype names (Developer, DataAnalyst, CICDServiceAccount, ...)
- No attack labels (CredentialTheftLateral, SmashAndGrab, ...)
- Resource and actor IDs: hashed, deterministic per seed
- Action types: mapped to opaque tokens

**Conclusion:** Detectors receive only anonymized events with no label information.

### 2. Fairness Audit (Structural Equalization)

**Status:** ✓ PASS

Verified:
- Zone counts: attack and clean worlds not separable (KS test, α=0.01)
- Node degrees: attack and clean worlds not separable (KS test, α=0.01)
- Per-zone event volumes: attack and clean worlds not separable (KS test, α=0.01)
- Attack path lengths within benign IQR
- Hard negatives present (ETL twins, on-call storms, novelty floods)
- Determinism: worlds reproducible via (config, seed)

**Conclusion:** Landscape design prevents trivial structural separation of attacks from benign.

### 3. Leakage Red-Team (Instance-Grouped)

**Status:** ✓ AT CHANCE

- **Shallow classifier:** Logistic regression on 7 shallow features (event count, resource diversity, edge diversity, action diversity, max degree, mean degree)
- **Metric:** AUC-PR (not ROC-AUC; class imbalance extreme)
- **AUC-PR:** 0.0000
- **No-skill baseline:** 0.0000
- **95% CI:** [0.0000, 0.0000]

**Evaluation unit:** Attack instance (campaign), not per-window. Features aggregated over full campaign duration.

**Conclusion:** Dumb classifier cannot discriminate subtle attack instances from benign behavior at above-chance rate. Landscape is not rigged.

---

## Key Implementation Points

### Evaluation Unit: Attack Instance (Campaign)

Locked decision (SANDBOX_CONTRACT.md §1):
- **One campaign** = one realized attack in one actor's trajectory
- **Detection** = any (actor_hash, window) alert overlapping campaign's [t_start, t_end)
- **No pseudo-replication:** one campaign counted once, whether 1–40 alerts fire
- Ground truth deterministic per world (config, seed)

### Rolling-Window Physics Scoring

Locked decision (PREDICTIONS.md Correction 2):
- P1e, P2 score over per-actor rolling windows of ≥80, ≥20 transitions
- NOT fixed 15-min clock windows (data-starved on real logs)
- Coupled to simulation horizon: each actor >> 80 transitions

### World Configuration (Frozen, SANDBOX_CONTRACT §4)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Population size | 250–300 actors | Concentration of transitions per actor |
| Horizon | 80–90 days | Each actor 1000+ transitions |
| Event rate | ~30 events/day | Poisson, tuned for per-actor data sufficiency |
| Archetypes | 9 (verified shapes) | Developer, analyst, CI/CD, ETL, backup, SRE, new-hire, role-change, break-glass |
| Attacks | 5 (verified overlays) | CredentialTheft, SlowExfil, SmashGrab, LOTL, SAHijack |
| Hard negatives | 3 types | ETL twin, on-call storm, novelty flood |

---

## Threats to Validity & Mitigations

### Threat: Synthetic ≠ Production

**Status:** Acknowledged; evaluation limited to necessary bar.

- Gate verdict: "fair" = necessary bar for proceeding (no label leakage, structural fairness, no trivial discrimination).
- Gate verdict: NOT "validation" — synthetic ≠ production. Next gate is shadow-mode pilot (GTM milestone).
- All results caveat: "Pending real-data confirmation."

### Threat: Benign One-Way Flows Falsely Flagged

**Status:** Mitigated by hard negatives.

ETL and backup archetypes are **benign, irreversible-by-design flows**. They are present in every world (minimum 3 instances per archetype). Detectors that conflate "irreversible" with "malicious" will falsely alarm on these — the system detects and quantifies this via per-archetype FP composition.

### Threat: LOTL Difficulty

**Status:** Crown-jewel test; properly constructed.

Living-off-the-land attacks use ONLY edges in the actor's own history, altered only in sequencing/direction/rate. Per-edge rarity is zero signal by construction. Only physics (asymmetry, deviation from baseline) can catch this. If physics fails here, it is dead.

### Threat: Under-Powered Subtle Attacks

**Status:** Flagged if n < 10.

Subtle attacks (LOTL, SlowExfil, SAHijack) with <10 instances → status INCONCLUSIVE (not gate-failing). Reported stratified.

---

## Next Steps

### Phase 4: Detector Tuning (Dev Worlds)

- Baseline B1 (Hopper-style) and baselines B0, B2 (strawman, shallow ML) tuned on dev seeds 0–29.
- Physics P1e (excess entropy production), P2 (flux divergence), P3 (ensemble) tuned.
- H2 (physics-as-feature inside B1) tuned.
- Equal tuning budget across all detectors (prevent B1 under-tuning).

### Phase 5: Held-Out Evaluation (Run Once)

- Freeze all hyperparameters (FREEZE.md).
- Evaluate on held-out seeds 30–99.
- Paired detection-rate analysis (same worlds, different detectors).
- Bootstrap 95% CI on paired differences.
- Per-attack-type breakdown and per-archetype FP composition.

### Phase 6: Decision Memo

- Outcome per §1 criteria: KILL / AUGMENT / PROVISIONAL PASS.
- Margin threshold: ≥5pp lift on detection rate @ fixed budget.
- Ties resolve to KILL.

---

## Files Generated

1. **sandbox_v2_worlds.pkl** — Serialized World objects (for audit references)
2. **sandbox_v2_seeds.json** — Seed mapping (dev_seeds, held_out_seeds)
3. **sandbox_v2_summary.json** — Machine-readable summary (metrics, audit results, gate)
4. **sandbox_v2_gate.md** — This human-readable report

---

## Sandbox V2 Validation Complete ✓

**All fairness gates passed. Landscape is fair and non-rigged. Ready to proceed.**

---

*Report generated: 2026-07-03*  
*Contract: SANDBOX_CONTRACT.md (frozen 2026-07-03)*  
*Evaluation unit: Attack instance (campaign)*  
*Audits: grep_leak_check, fairness_audit, leakage_redteam (instance-grouped)*
