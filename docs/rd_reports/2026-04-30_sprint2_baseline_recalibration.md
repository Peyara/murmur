# Sprint 2 — Baseline Embedding & Threshold Recalibration

> **Status:** PREDICTIONS COMMITTED, runs pending. Predict-then-observe per CLAUDE.md R&D discipline. This file is updated with observations after the run; the predictions section below is **frozen** at write time.

Generated (predictions): 2026-04-30

---

## Why this experiment

Sprint 2 (PR #36) produced a FAIL gate verdict at 40% detection, with `sigma_coarse`, `delta_f`, `closure_gap`, and `orphaned_priv` firing at 0% across all 50 strategy-grid trajectories. The interpretation in the Sprint 2 R&D report named two competing hypotheses:

1. **Methodological** — attack-only trajectories provide no benign baseline against which physics/closure signals can compute their values.
2. **Architectural** — these signals genuinely don't activate on attack patterns regardless of context.

This experiment resolves the distinction by re-running the strategy grid with attacks embedded in benign worker + scheduled-job traffic. It also recalibrates thresholds on the resulting distribution and validates the recalibration against a benign-only false-positive floor.

### Third hypothesis discovered during code reading

The Sprint 2 harness (`src/validation/robustness.py`) inserts events via `insert_event` directly and **never calls `create_watch` or `try_close_watch`**. Production ingestion (`fetch_and_ingest` in `src/ingest/fetch.py:228,388`) wires both. This means closure signals were guaranteed 0% in Sprint 2 regardless of methodology or architecture — a **harness gap**, not a system finding. The new harness wires watch creation, isolating closure semantics from the bug.

---

## Predictions (frozen 2026-04-30, BEFORE any run)

### Per-signal fire rate, three modes

| Signal | A: attack-only (Sprint 2) | B: attack-in-benign | Benign-only FP floor | Reasoning |
|---|---|---|---|---|
| `inv_score` | 96% (observed) | 90–98% | <5% | Per-actor invariants on action types; doesn't depend on population. Benign workers shouldn't fire IAM/CONTROL invariants. |
| `novelty_score` | 40% (observed) | 50–70% | 10–30% | Benign establishes population history — namespaced attack actors will look novel against it. Multi-actor still disperses per-actor novelty. |
| `sigma_coarse` | 0% (observed) | **30–60%** | 10–30% | Variance computation needs population to compute against. Predicting fires for fast/medium attacks; slow attacks may still be silent. |
| `bridge_new` | 40% (observed) | 50–70% | 20–40% | Benign provides "established edges" in early windows; attack creates new ones. Should fire more under baseline. |
| `delta_f` | 0% (observed) | **30–60%** | 5–20% | Depends on sigma_coarse. Same reasoning. |
| `closure_gap` | 0% (observed) | **40–70%** | 10–30% | Watches now created. closure="full" → ratio=1.0; closure="none"/"partial" → ratio<1.0. ~67% of grid is non-full. |
| `orphaned_priv` | 0% (observed) | 5–20% | 0–5% | Requires window_hours overdue (e.g., SA_KEY=720h). Short trajectories (≤30 min sim) won't trigger, but `never_settle_types={SA_KEY,SERVICE_ACCOUNT}` means open SA_KEYs accumulate without auto-close — small fraction may register. |

### Detection rate predictions

| Threshold regime | Mode A predicted | Mode B predicted |
|---|---|---|
| Current (PR #34: WATCH=0.20) | 40% (observed) | 60–75% |
| Recalibrated on Mode B P75 | n/a | 75–85% |

Recalibrated WATCH will be set to `max(P75(B-attack-actors), P95(benign-only))`. The benign FP floor must constrain WATCH from below — if `P95(benign-only) > P75(attack-in-benign)`, recalibration is **unsafe** at any rate ≥ 75%.

### Class-wipe predictions

The Sprint 2 verdict identified two CLASS-WIPE patterns: `split_actions` (0%) and `multi_actor` (8.7%).

| Class | Predicted detection rate under B + recalibration | Architectural? |
|---|---|---|
| `split_actions` | **20–40%** (still likely below 60%) | Yes — window-scoped scoring fundamentally cannot correlate cross-window. Phase B B1 TPP is the right answer. |
| `multi_actor` | **30–50%** (still likely below 60%) | Yes — per-actor signals fundamentally disperse. Phase B B1 TGN is the right answer. |

If split_actions or multi_actor recover to ≥60% under recalibration, those failures were calibration artifacts and Phase B B1 is unjustified. **Both being architectural** is the strongest case for Phase B B1.

### Falsifiability table

| Observation | Interpretation |
|---|---|
| sigma_coarse, delta_f, closure_gap **all <10% under B** | **Architectural failure** of the physics thesis. Phase B B1 needs to revisit premises, not just direction. |
| sigma_coarse, delta_f, closure_gap **all ≥30% under B** | **Methodological failure** confirmed. Sprint 2 verdict was a harness artifact + calibration. Re-evaluate gate at recalibrated thresholds. |
| Mixed: physics fires ≥30% but closure_gap <10% | Closure semantics issue beyond watch creation — settlement detection or pair semantics need work. |
| Recalibrated WATCH < benign-only P95 | **Unsafe calibration.** Methodological cleanup unblocks detection at the cost of FPs. Signals or normalization need work before thresholds can move. |
| Mode B detection ≥75% AND `split_actions`/`multi_actor` ≥60% | Phase B B1 unjustified by current data. |
| Mode B detection 60–80% AND `split_actions`/`multi_actor` <30% | **BORDERLINE** with architectural-failure clusters → partial Phase B B1 (TGN+TPP for those clusters specifically) is the right call. |

### Recommendation tree (committed before observation)

```
if Mode B sigma_coarse/delta_f all <10%:
    → Architectural FAIL. Re-evaluate physics thesis from premise.
    → DO NOT proceed to Sprint 3 or Phase B B1 without fixing or replacing physics.
elif Mode B detection rate >= 75% with no class-wipe:
    → Sprint 2 was a harness/calibration artifact. Proceed to Sprint 3 (provenance/closure full integration).
elif Mode B detection rate 60-75% with split_actions/multi_actor < 30%:
    → BORDERLINE + architectural cluster. Partial Phase B B1 (TGN+TPP) is justified.
else:
    → FAIL. Reframe — physics works but generalization is poor; redesign needed before any new layer.
```

---

## Observations (run 2026-04-30 21:51)

Full machine-generated report: `docs/rd_reports/2026-04-30_sprint2_baseline_recalibration_run.md`. Numerical summary below.

### Detection rates (three regimes)

| Regime | Threshold | Detection rate | Comment |
|---|---|---|---|
| Mode A: attack-only (Sprint 2 reproduced from PR #36) | WATCH=0.20 | 40% | Original FAIL. |
| Mode B: attack-in-benign | WATCH=0.20 | **92%** | Misleading — benign FP floor exceeds threshold. |
| Mode B + recalibrated | WATCH=**0.428** | **30%** | Honest rate at safe FP floor. |

The 92% is **garbage detection** — benign-only's residual_risk distribution is P75=0.289, P95=0.375, max=0.696. At WATCH=0.20, benign traffic also crosses the threshold. Recalibration must place WATCH ≥ benign P95 = 0.375; the value 0.428 is bound by `max(grid_p75=0.428, benign_p95=0.375)`, both nearly coincident.

### Signal fire rates: attack-in-benign vs benign-only

| Signal | Attack-in-benign | Benign-only | Discrimination ratio |
|---|---|---|---|
| inv_score | 96.0% | 44.6% | 2.2x |
| novelty_score | 40.0% | 32.2% | 1.2x |
| **sigma_coarse** | **0.0%** | **5.0%** | **dead** |
| bridge_new | 100.0% | 81.0% | 1.2x |
| **delta_f** | **0.0%** | **5.0%** | **dead** |
| closure_gap | 100.0% | 30.6% | 3.3x (best discriminator) |
| orphaned_priv | 0.0% | 8.3% | dead |

`sigma_coarse` and `delta_f` are confirmed architectural failures — **even with full benign baseline + correct watch wiring**, they fire at 0% on attack and ~5% on benign. The "physics-informed" framing is currently inaccurate at the signal level.

`closure_gap` is the clearest finding: 100% on attack, 31% on benign. Watch creation was indeed the harness gap; closure semantics work as designed. This is the single signal that genuinely differentiates.

`inv_score` and `bridge_new` fire often on benign too — bridge_new at 81% benign means it adds little discrimination. The system's apparent strength on attack is partially redundant with normal behavior.

### Per-class breakdown (Mode B + recalibrated)

| Class | Detection | Status |
|---|---|---|
| `multi_actor` | **8.7%** | CLASS-WIPE persists from Sprint 2. Architectural — TGN (Phase B B1) is the right answer. |
| `direct` zone_path | 11.1% | Short attacks remain invisible. |
| `evasion=none` | 11.1% | Even the **easiest** attacks only register 11%. |
| `split_actions` | 20.0% | Up from 0% but still subgate. TPP (Phase B B1) addresses cross-window. |
| `closure=full` | 20.0% | Self-closing attacks evade closure_gap by design. |
| `pattern_mimicry` | 30.8% | Provenance discount applies; still low. |
| `timing_jitter` | 53.8% | Best evasion category — jitter doesn't defeat the residual signals. |
| `full_chain` zone_path | 58.8% | Long chains have more invariant triggers. |

### Benign-only residual distribution

n=121 (window, actor) pairs across 20 windows.

```
P50: 0.157   P90: 0.349   max: 0.696
P75: 0.289   P95: 0.375   P99: 0.597
```

The shape is concerning: even at P50, half of benign traffic crosses the original WATCH=0.20. The synthetic baseline is noisy by design (TrajectoryComposer creates realistic worker + scheduled-job traffic with novel actors per seed), but this is the FP floor we'd see if Murmur were deployed against it.

---

## Observed-vs-Predicted Divergence

| Signal | Predicted Mode B | Observed Mode B | Verdict |
|---|---|---|---|
| inv_score | 90–98% | 96.0% | ✅ predicted |
| novelty_score | 50–70% | 40.0% | ❌ over-predicted; benign baseline didn't change attack-actor novelty (compute_novelty_score is per-actor-vs-self, not vs-population) |
| **sigma_coarse** | **30–60%** | **0.0%** | ❌ **wrong direction.** Predicted methodological recovery; got architectural failure. |
| bridge_new | 50–70% | 100.0% | ❌ under-predicted; bridge fires near-universally with benign baseline (probably too aggressive — every cross-zone edge in any window counts). |
| **delta_f** | **30–60%** | **0.0%** | ❌ **wrong direction.** Same as sigma_coarse — depends on it. |
| closure_gap | 40–70% | 100.0% | ❌ under-predicted; closure_gap fires on every non-`full` closure, which dominates the grid. |
| orphaned_priv | 5–20% | 0.0% | ✅ on the low end of prediction; window_hours=720 dominates short trajectories. |

**Signal-level prediction divergence summary:**

- **Got the methodological mechanism right** for `closure_gap` and `bridge_new` (they fire under baseline) and `inv_score` (independent of baseline).
- **Got the architectural mechanism wrong** for `sigma_coarse` and `delta_f`. Predicted these would activate under benign baseline; they did not. This is a stronger result than the FAIL+caveat reading from Sprint 2 — physics signals are dead, not dormant.
- **Detection-rate prediction**: predicted Mode B current-threshold = 60–75%. Observed 92%. Prediction missed the FP floor entirely — I anticipated benign would stay quiet, but it doesn't.
- **Recalibrated detection prediction**: predicted 75–85%. Observed 30%. Missed by 45 points. The error: I assumed the gap between attack and benign distributions would be wide. Observation: P95 of benign (0.375) almost equals P75 of attack (0.428). The signal-vs-noise gap is the load-bearing finding I didn't anticipate.

**The architectural-failure observation on sigma_coarse / delta_f closes a loop.** Sprint 2's original interpretation named "methodological vs architectural" as competing hypotheses. We can now resolve it: physics signals are architectural failures; closure was a harness gap (now fixed); the dominant remaining problem is a *separate, deeper architectural issue* — small attack-vs-benign signal gap.

---

## Verdict & Recommendation

**Verdict: FAIL at safe FP thresholds.**

The recalibrated detection rate (30%) is below the 60% BORDERLINE threshold. The class-wipes (`multi_actor` 8.7%) persist. The physics signals are architecturally silent. Even the cleanest attacks (no evasion, no closure padding) don't reliably register above benign noise.

**This is more diagnostic than Sprint 2's FAIL.** Sprint 2 left open the methodological-vs-architectural question. This run resolves it: the methodology was bad AND the architecture has structural problems beyond what TGN+TPP alone can address.

### Recommendation: re-evaluate signal architecture before any new layer

**Per the recommendation tree (committed before observation), the matching branch is:**
> _Mode B detection 60–80% AND `split_actions`/`multi_actor` <30%: BORDERLINE + architectural cluster. Partial Phase B B1 (TGN+TPP) is justified._

But the actual observation is **<60% detection AND class-wipes persist** — i.e., the FAIL branch:
> _FAIL. Reframe — physics works but generalization is poor; redesign needed before any new layer._

**Concrete actions, in priority order:**

1. **Drop or replace sigma_coarse and delta_f.** They fire 0% on attack across two harness configurations. The "physics-informed" framing is inaccurate at the signal level. Either ablate to weight=0 (already low at 0.04 + 0.08) or replace with signals that actually activate.

2. **Re-examine the signal-vs-noise gap.** The benign-only distribution producing P95=0.375 is the load-bearing finding. Two paths:
   - **Tighten the synthetic baseline** — TrajectoryComposer may be over-noisy. If real customer benign is quieter, the FP floor drops and current signals may suffice. This is testable on real GCP data (sandbox already producing logs per CURRENT_STATE).
   - **Stronger normalization / per-actor calibration** — the same residual_risk threshold for novel-history attack actors and established-history workers is too coarse. Adapt thresholds per actor history depth.

3. **Phase B B1 (TGN+TPP) is justified but not sufficient alone.** TGN addresses multi_actor; TPP addresses split_actions. Both class-wipes still fail under Mode B+recal. **But** these layers depend on the per-window signals that the current run shows are weak. Building TGN on top of weak per-actor signals risks compounding noise. Sequence:
   - First: fix the signal architecture (action 1+2).
   - Then: TGN/TPP becomes meaningful.

4. **Sprint 3 (provenance + closure full integration) is partially validated.** closure_gap is the strongest discriminator (3.3x). Closure semantics work; the harness was the bug. Sprint 3's closure work is justified, but the broader fusion thesis needs revision.

**Do not proceed to Sprint 3 or Phase B B1 as currently scoped.** Insert a "signal architecture review" pass first. Recommended: 2–3 day R&D pass to evaluate ablation + per-actor calibration + real-customer benign baseline.

### Lessons for the learning loop

| What I assumed | What I observed | Adapted approach |
|---|---|---|
| Benign baseline would mostly fix the 0% physics signals | Physics signals stayed at 0% even with baseline + watches | Treat physics signals as dead until proven otherwise; don't let "physics-informed" branding survive empirical refutation |
| Recalibration would unlock detection rate | Recalibration revealed signal/noise gap is the real bottleneck | Always pair recalibration with a benign FP floor — thresholds without that floor are unmoored |
| Sprint 2's FAIL was largely methodological | Sprint 2's FAIL was methodological + architectural | Multiple competing hypotheses can all be true. Resolve them sequentially with controlled experiments. |
| TGN+TPP is the answer to multi_actor / split_actions | They may be necessary but not sufficient | Architectural layers compound noise from underlying signals. Fix signals first. |

### Principles to elevate to project CLAUDE.md

1. **Detection rate without FP floor is meaningless.** Any threshold report must include the benign distribution P95 (or equivalent FP bound). Add to Threshold Discipline section.
2. **Predict the failure mode along with the signal.** I committed predictions on which signals would fire. I did not commit predictions on the *signal-vs-noise gap*. The latter was the diagnostic finding; predicting only fire rates missed it.
3. **Harness-gap hypothesis as a third causal layer.** When a signal is silent, three hypotheses compete: methodological, architectural, harness-gap. Always check the third before debating the first two. Add to Observe Before Hypothesize section.


---

## Limitations

- Fixed `baseline_seed` across all 50 trajectories — eliminates baseline-variance as a confound but means we can't measure how baseline shape affects detection. Sweeping baseline seeds is a follow-up.
- Attack actors are namespaced (`attack-{email}`) to guarantee disjoint pools from benign actors — sacrifices the identity-reuse evasion test, which is a separate question.
- Threshold recalibration uses simple percentiles, not a tuned classifier. Per the project's Threshold Discipline section: per-distribution thresholds are not transferable, so this is honest about its scope (calibrated for *this* distribution only).
- TrajectoryComposer benign workflows are synthetic and do not represent any specific real customer. The benign FP floor measured here is a synthetic floor, not a production FP estimate.
