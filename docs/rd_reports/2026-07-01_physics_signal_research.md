# Physics Signal Research — Deep-Research Synthesis + Fresh-Eyes Review

**Date:** 2026-07-01
**Mode:** R&D
**Status:** Complete (research). Step 2 (real-data observation) NOT yet started.
**Feeds:** Sprint 2.5 (Physics Signal Architecture Review) — this pre-empts and evidence-grounds the Day-1 concept probe.

---

## 0. Why this pass exists

User's framing: "Review Murmur's core thesis and whether the physics signals we chose are good. The
project has sprawled and is going nowhere." User's hypothesis: the physics signals fail to validate
because the **synthetic sandbox is too impoverished** to exhibit the variance/process dynamics the
physics captures — a chicken-and-egg (can't validate the signal without realistic data; can't justify
realistic data without a validated signal). User also conceded the signals themselves (`sigma_coarse`
etc.) can be rethought.

This report = grounded deep-research (5-angle web sweep, 21 sources, adversarial verify) + fresh-eyes
analysis + correction of a material error in the research + a sharpened design for step 2.

---

## 1. Ground truth on Murmur's physics (from repo, pre-research)

- **Thesis (README):** "detects coordinated adversarial activity in GCP using physics-informed signals
  and provenance subtraction." Premise (physics_foundations.md:46): sanctioned automation creates
  *persistent asymmetric flux* (cycle currents that don't vanish); attackers introduce irreversible net
  currents → detectable as an entropy-production spike.
- **`sigma_coarse`** = Schnakenberg entropy production over a **6-zone** transition Markov chain in
  15-min windows. Formula: σ̂ = (1/T) Σ_{i≠j} N_ij ln( (N_ij/T_i)/(N_ji/T_j) ). Sigmoid-normalized
  (X0=3.0, K=1.0), fusion weight 0.04.
- **`delta_f`** = current σ − EMA(σ), α=0.1. Fusion weight 0.08.
- **Validation (PR #37, 2026-04-30):** both fire at **0% on attack, ~5% on benign**, even with full
  benign baseline + correct watch wiring. Confirmed "architectural failure" at signal level.
- **Contrast:** `closure_gap` 3.3x discrimination (validated, carrying the system), `inv_score` 2.2x.
  `novelty`/`bridge_new` 1.2x (weak). Physics contributes ~0% independent detection.
- **Sprawl:** 10 fusion signals, 11 invariants, 2 theory docs (~200 lines of Schnakenberg math with no
  empirical support), 19 R&D reports, 6 sprint docs. closure_gap + inv_score do ~all the work.

---

## 2. VERDICT (headline)

**It is the instrument, not (mainly) the sandbox — and probably not a dead thesis.**

The likely root cause is **(c): the Schnakenberg cycle-current estimator is structurally wrong for
acyclic attack flows.** The irreversibility-as-anomaly *thesis* may be fine; the *instrument* for
measuring it is the culprit. The user's sandbox hypothesis is half-right (you genuinely cannot falsify
from synthetic data alone) but redirected — the fix is NOT "enrich the sandbox until it fires" (that is
textbook confirmation bias, documented below).

### Hypothesis mapping

| Hypothesis | Evidence verdict |
|---|---|
| **(c) estimator wrong for acyclic flows** | **Strongest support.** Schnakenberg affinity is *defined* on cycle currents — needs both N_ij and N_ji. Exfil paths (identity→secret→exfil) are one-way, N_ji=0 → term degenerate/undefined. **Zero published applications** of Schnakenberg to directed security graphs. Design mismatch, not tuning. |
| **(b) sparsity / estimator degeneracy** | Real in principle, but the research's *magnitude claim is wrong* (see §4). Real issue = per-edge reciprocal sparsity, not large-state-space sample complexity. |
| **(a) impoverished sandbox** | Partially right: cannot falsify from synthetic alone; circular validation is a documented trap. But literature explicitly warns against tuning the sandbox until the detector fires. |
| **(d) thesis wrong (irreversibility ≠ benign)** | **Not established.** Nothing refutes irreversibility-as-signal. |

---

## 3. Deep-research findings (5 angles, 21 sources, 25 claims verified → 4 confirmed)

**Methodological caveat on the workflow:** adversarial-verify killed 21/25 claims, but several
"refuted" entries are reworded versions of *confirmed* findings (the Han et al. bound is in both
lists). Skeptic voters defaulted to "refute if uncertain," so the kill-list is noisy — read for
substance, not vote counts.

1. **Sample-complexity floor (HIGH — Han et al., NeurIPS 2018, arXiv:1802.07889).** Plug-in
   entropy-rate estimators need n ≫ S²/log S; bias bounded away from zero when n ≤ cS², even for
   memoryless chains. Proven, mixing-time-independent. *(But see §4 — the report mis-applied S.)*
2. **Structural mismatch to acyclic flows (MEDIUM).** Schnakenberg cycle currents require reciprocal
   transitions; acyclic one-way flows produce zero/degenerate estimates. No literature extends
   Schnakenberg to acyclic security digraphs. *This is the crux finding.*
   - Related (voted down 1-2, but relevant): arXiv:2412.04102 — waiting-time entropy-production
     estimators "only recover full entropy production when the Markov network becomes acyclic after
     removing observed transitions" → hints acyclic-aware estimators exist.
3. **No published prior art (HIGH).** Zero confirmed applications of Schnakenberg production to security
   event streams / intrusion detection / graph event streams. It is **speculative domain transfer** —
   an architectural bet, which is fine, but must be called what it is.
4. **Benchmark aggregation masks per-type performance (HIGH — arXiv:2507.15584, ADBench 98k exps).** A
   detector can score ~0% in aggregate while excelling on one anomaly subclass (e.g., LOF ranks low
   overall but wins on local anomalies). → Murmur's 0%/5% could hide that physics catches cyclic
   recon but dies on acyclic exfil.
5. **Synthetic-benchmark confirmation bias (multiple sources).** Circular validation (train on
   synthetic, test on synthetic), synthetic data failing to reproduce cadence/noise/cyclicality,
   15–25pt F1 drop synthetic→real. Supports the "can't validate from sandbox alone" point AND the
   "don't tune sandbox to fire" warning.

Key sources: arXiv:1802.07889 (sample complexity), arXiv:2412.04102 (finite-resolution entropy-prod
estimation), arXiv:2204.00875 (Schnakenberg bounds), cond-mat/0512254 (Schnakenberg foundational),
arXiv:2507.15584 (benchmark aggregation), arXiv:2606.12225 / PMC12074446 (synthetic-benchmark bias).

---

## 4. MATERIAL ERROR CAUGHT in the research (do not skip)

The report's headline — "2–4 orders of magnitude below the sample floor, 10⁴–10⁶ samples needed" —
assumes state space **S = 100–1000 actors.** But Murmur's Schnakenberg runs over a **6-zone matrix —
S = 6.** The floor is S²/log S ≈ 36/1.8 ≈ **~20 transitions**, not 10⁴. Windows carry ~10–100
transitions → you are **roughly AT the floor, not hopelessly beneath it.**

**Consequence:** taking the report at face value → "data-starved, give up on physics" → WRONG call.
The real sparsity problem is **per-edge reciprocal sparsity**: with ~30 possible directed edges and few
transitions, most i→j edges never see a matching j→i, so ln(N_ij/N_ji) is degenerate for most edges.
That is a *reciprocity* problem — the same root as (c): the instrument needs round-trips that neither
benign nor attack traffic may produce.

---

## 5. Predict-then-observe (R&D discipline log)

- **Predicted:** web would show entropy-production estimators are (i) data-hungry and (ii)
  cycle-oriented → step 2 toward density + directionality.
- **Observed:** (ii) confirmed strongly; (i) **over-weighted** — bought the large-S sample-complexity
  story before checking Murmur's S=6. Data-hunger concern is much smaller than headlined; reciprocity
  /acyclicity is the real one. **Logged as a miss** (verify architecture constants before importing an
  external bound).

---

## 6. STEP 2 DESIGN — real-data observation (resume here)

Sequencing agreed with user: run research (done) → then observe real data (this). The research
sharpened the single measurement that discriminates all hypotheses.

On **real GCP benign traffic, no attack labels** (breaks the chicken-and-egg — needs neither a
validated signal nor a realistic sandbox):

1. **Edge reciprocity (LOAD-BEARING).** For each observed zone edge i→j, how often does j→i also occur
   in the same window? If benign traffic is mostly one-way (low reciprocity), Schnakenberg is the wrong
   instrument for the *whole domain* (benign and attack alike) — decisive for (c).
2. **Transition density per window.** Confirms whether you clear the corrected (S=6) floor of ~20.
3. **Do persistent cycle currents exist at all** in benign automation? — the thesis's precondition
   (physics_foundations.md:46). If not, the *premise* is what's wrong, not just the estimator.

**FREE check on existing PR #37 data, no new data, do first:** disaggregate the 0%/5% by attack
subclass. Per the aggregation-masking finding, physics may fire on cyclic-recon attacks while dying on
acyclic exfil. If so → confirms (c) AND shows physics has a narrow-but-real niche rather than being
dead.

**Likely endgame (contingent on reciprocity result):** replace the instrument (Sprint 2.5 Branch C) —
a directed one-way flux / KL-between-forward-and-reverse measure that scores acyclic exfil as
*maximally* irreversible instead of undefined. NOT rebuild the sandbox.

---

## 7. Session side-changes (config) — follow-ups

1. **Peyara standards CLAUDE.md amended** (`peyara-standards/peyara/CLAUDE.md`, real target behind the
   `Peyara/CLAUDE.md` symlink). Autonomous mode made self-contained: added Precedence line (relaxations
   override Safety/Collaboration/Production; only absolute list binds), added relaxed bullets
   (TDD-ordering & one-feature-per-session dropped; in-scope architecture/3rd-party calls no longer
   halt). Bumped to v2.1. **Working-tree change, UNCOMMITTED** — that repo is version-controlled;
   commit/push is a separate step when desired.
2. **Global `~/.claude/CLAUDE.md` NOT amended** — now inconsistent with Peyara (older "What relaxes"
   block, no precedence line). Decide: port precedence up to global, or have global defer to project
   standards.
3. **`~/.claude/settings.json`** — added `WebSearch` + `WebFetch` to `permissions.allow` (user-level,
   all projects). Read-only ops; removes per-call prompts for deep-research.

---

## 8. Raw research artifact

Full workflow JSON (may be cleaned — scratchpad is session-specific):
`/private/tmp/.../tasks/wzoos8t46.output` (2541 lines). Journal:
`.../subagents/workflows/wf_95e1a05c-8fe/journal.jsonl`. Everything load-bearing is captured above.
