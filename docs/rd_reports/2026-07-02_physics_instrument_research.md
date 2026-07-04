# Physics Instrument — Diagnosis Correction + Deep-Research Synthesis

**Date:** 2026-07-02
**Mode:** R&D
**Branch:** `gut-renovation`
**Status:** Diagnosis verified against code + real DB data. Deep-research (103 agents) complete. Bake-off NOT yet built.
**Supersedes:** parts of `2026-07-01_physics_signal_research.md` (the "reciprocity absent across the domain" hypothesis — refuted here).

---

## 0. Why this pass exists

Continuation of the 2026-07-01 physics review. Two user challenges reshaped it:

1. *"Whatever the results, Schnakenberg is the wrong measure — so why run the free-check disaggregation on it at all?"* → Correct. Step 1 (disaggregate PR #37 sigma by attack subclass) was **struck** — inspecting a broken instrument for a niche it structurally cannot have.
2. *"Check your results — even simple arithmetic errors happen."* → Triggered a verification pass that caught one of my own errors (below) and sharpened the diagnosis.

Then a decision-grade, adversarial deep-research run (4 framings, 5 angles, 103 agents, 21 sources).

---

## 1. VERIFIED diagnosis (code + real DB, this session)

All measured on `murmur.duckdb` / `murmur_rd.duckdb` (confirmed **0 attack events** — pure synthetic benign) and read from source.

- **`sigma_coarse` is window-global, NOT attributable to an actor.** `compute_zone_flux` writes one sigma per window; `baseline_robustness.py` reads it for attack-actor windows, but the value is identical for every actor in that window. A per-actor discriminator is impossible by construction. *(Verified in `graph.py:126`, `baseline_robustness.py:142-180`.)*
- **The skip rule inverts the thesis.** `graph.py:55`: `if j_ij == 0 or j_ji == 0: continue`. A one-way edge contributes **0**. But one-way monotonic traversal (IDENTITY→SECRET→EXFIL) is *exactly* the attack, and physically it is *maximally* irreversible (σ→∞). So the estimator scores **attacks low and benign loops high** — backwards.
- **Benign is highly reciprocal — refuting the 07-01 hypothesis.** Zone-edge reciprocity 74.5% (murmur) / 83.3% (murmur_rd), and it is **real at the single-actor level** (73% of windows are single-actor; 462/462 single-actor windows with a cross-zone edge contain a same-actor round-trip). sigma is nonzero in ~92–97% of windows. So Schnakenberg is **not** "undefined across the domain" — the acyclicity is in the *attack*, and the skip rule silently zeroes it.
- **Sample floor:** transitions/window median 11, mean 17.7, vs the corrected Han floor `S²/log S = 36/ln6 ≈ 20.1` (S=6 zones). We are **at / slightly below** the floor — not 10⁴ beneath it. (07-01 error was S=actors; corrected there.)

### Error I caught in my own analysis (logged)
I first claimed the high reciprocity was "manufactured by pooling actors." **Wrong** — 73% of windows are single-actor and 100% of those with cross-zone edges have same-actor round-trips. Reciprocity is real at the actor level (very likely a synthetic-generator looping artifact — the exact thing real GCP may not reproduce).

### Net reframe
07-01 said: *instrument mismatch — reciprocity absent across the domain.*
07-02 says: **attribution failure + thesis inversion** — sigma is window-global (can't isolate the attacker) and the skip rule maps the attacker's one-way path to zero while benign loops produce high sigma. Same family (instrument is wrong), better-articulated cause. A replacement must (A) map one-way → *large*, and (B) be computed *per-actor/per-path*.

---

## 2. Deep-research synthesis (103 agents, 21 sources, 25 claims verified → 4 confirmed)

**Read the verify phase as a landscape map, not a claim adjudicator.** Concrete-paper angles (SOTA) produced confirmations; the foundational-physics angle had its *true* claims shredded (see §2.3). Only 4/25 survived; 3 sources were unreliable (0 claims); 82 extracted but 25 verified (budget).

### 2.1 Confirmed (with strength)
1. **Physics-informed irreversibility is absent from SOTA security detection** (LogSHIELD check 3-0; broader 2-1). Genuine white space. *Strong.*
2. **SOTA is in a reproducibility crisis** — 0/8 systems (Kairos, Flash, ThreatTrace, Magic, ShadeWatcher, Atlas, AirTag, NodLink) reproduce end-to-end; 92–98% AUC headlines are unverified (SRI REP-2025, peer-reviewed). *Strong. Most useful finding — the wall we'd be "behind" is shaky.*
3. **Neural scale/evasion trade-off** — in-memory embeddings → ~140GB; scale abstractions → evadable. Orthogonal opening if a physics signal is cheap. *Strong.*
4. **No head-to-head exists** between irreversibility detection and any baseline. *Medium — negative/inferred, weakest.*

### 2.2 Two high-value findings buried in fetch logs (NOT in the confirmed 4)
- **Hopper (USENIX Sec'21, arXiv:2105.13442):** naive "flag rare directed edges" **fails on false positives** (on-call rotations, new users, role changes are rare-but-benign). Hopper reaches 94.5% detection at <9 alerts/day via **causal-path context**, not physics. → **The control the physics signal must beat is Hopper-style (rare edge + causal path to sensitive zone), NOT naive rarity and NOT Schnakenberg.**
- **Irreversibility-measure ensemble (PMC8622570):** "no single metric is strictly better"; ensembles ~97% vs 50–x% individual. Non-security domain (caveat), but argues **against betting on one instrument.**

### 2.3 Where the verifier was WRONG (noisy kill-list)
The most decision-relevant physics claim — *"Schnakenberg entropy production is tied to cycles; acyclic paths yield zero/undefined"* — was voted **0-3 refuted**. It is **true physics and matches our verified `graph.py:55` finding.** Skeptics default to refute-when-uncertain and the source didn't frame it as a security limitation. **Our own code is the confirmation the verifier couldn't credit.** (Report's own caveat #2 resurrects it.)

---

## 3. Predict-then-observe (R&D discipline log)

- **Predicted:** research would surface prior art validating (or refuting) an irreversibility instrument for security → pick the winner.
- **Observed:** the space is *empty* — no prior art, no comparison. The "pick the instrument" framing is unanswerable from literature; the question is **empirical**, only the bake-off can settle it. **Logged as a framing miss** — should have predicted white space given 07-01 already found "zero published applications."
- **Bonus observation:** the simple baseline (rare-edge) is *also* not a free win (Hopper's FP problem). So neither "physics is obviously right" nor "simple is obviously enough" holds — genuinely open.

---

## 4. REFRAMED bake-off design (resume here)

The only way to answer *"does a physics signal earn its place?"* is a head-to-head, now sharpened:

**Contenders (per-actor / per-path, windowed):**
- `KL_irrev`: regularized forward/reverse KL — `Σ P(i→j)·ln[(P(i→j)+ε)/(P(j→i)+ε)]` on the *actor's own* edge set. Maps one-way → large finite (fixes A + B).
- `flux_div`: node-level flux divergence / source-sink signature (attacks terminate → sink; benign loops → divergence-free). Well-defined for acyclic.
- *(optional)* ensemble of the two (per PMC8622570).

**Controls (must beat these, not Schnakenberg):**
- **Hopper-style baseline:** rare directed transition + causal path to a sensitive zone. *This is the real bar.*
- Naive rare-directed-edge (to show the FP failure Hopper documents, on our data).
- Existing `closure_gap` + `inv_score` (the signals already carrying the system).

**Metrics:** per-attack-subclass detection at a fixed benign-FP budget (not aggregate AUC — SOTA's AUCs are unverified anyway). Report distance-from-threshold + P75/P90/P95 per distribution (Threshold Discipline). Ablation: does `KL_irrev` add independent lift over the Hopper-style control, or is it redundant?

**Kill criterion (make it falsifiable up front):** if `KL_irrev` + `flux_div` do not beat the Hopper-style control at equal FP on ≥1 attack subclass, **cut the physics layer.** Murmur's differentiation then rests on provenance-subtraction + self-learning, not physics. That is an acceptable `gut-renovation` outcome.

**Data caveat (load-bearing):** benign reciprocity here is likely a synthetic looping artifact. Before trusting any result, either (a) get real GCP benign traffic, or (b) explicitly generate benign with realistic non-looping paths. Otherwise the bake-off inherits the sandbox's confirmation-bias risk.

---

## 5. Open questions

1. Why is attack sigma *exactly* 0.000 across all 50 grid trajectories? (window-composition trace — attack windows disjoint from dense benign, or benign-sparse there.) Cheap; still owed.
2. Does `KL_irrev` per-actor beat the Hopper-style causal-path control at equal FP — on any subclass? (the bake-off)
3. Does the reciprocity finding survive on *real* GCP benign, or is it a synthetic artifact?
4. If physics adds no independent lift, is the honest move to cut it (gut-renovation) rather than replace it?

---

## 6. Artifacts

- Deep-research raw output: `tasks/wjpebb0c5.output` (2526 lines, session scratch — may be cleaned). Run ID `wf_08e9ca88-23b`.
- Key sources: SRI REP-2025 (reproducibility crisis), arXiv:2105.13442 (Hopper), PMC8622570 (irreversibility ensembles), arXiv:2410.21936 (LogSHIELD), cond-mat/0512254 (Schnakenberg foundational).
- Code ground truth: `src/world/graph.py:33-69` (schnakenberg_entropy + skip rule), `src/validation/baseline_robustness.py:110-210` (attack-in-benign harness).
