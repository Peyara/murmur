# Detection Signal Theory — Current Understanding

**Date:** 2026-07-04 · **Status:** Living synthesis. Supersedes (in practice) the Schnakenberg thesis in
`physics_foundations.md` — see §7. Confidence is tagged: **[established]** (verified in code/data),
**[current best]** (reasoned, partially evidenced), **[contested/open]** (unresolved).

> Salient view of where the physics-signal thinking actually stands, plus the shaky parts. Evidence
> lives in `bakeoff/DECISION_MEMO.md`, `bakeoff/PREDICTIONS.md`, and `docs/rd_reports/2026-07-0{1,2}_*`.

---

## 1. The detection problem, stated physically

An actor's activity over the cloud-IAM / auth resource graph is a trajectory of directed transitions.
**Benign automation is a non-equilibrium steady state (NESS):** it sustains large, *persistent* directed
currents (a CI job looping IDENTITY→SECRET→COMPUTE→DATA; an ETL pipeline flowing one-way to EXTERNAL).
These currents are **housekeeping** — structural to the actor's role, high but stationary.

The single most important consequence, and the one that invalidated the original thesis:

> **[established] Irreversibility is not anomaly.** Benign automation is *maximally* irreversible
> (one-way pipelines, directed cycles). Any measure of *absolute* irreversibility (entropy production,
> flux magnitude) fires on benign automation as hard as — or harder than — on attacks.

An attack is not "more irreversibility." It is a **departure from the actor's own steady state** — in
stochastic-thermodynamics terms, **excess (non-adiabatic) entropy production** (Hatano–Sasa), the part
of the entropy production attributable to driving the system off its maintained NESS, as opposed to the
housekeeping part that merely sustains it.

---

## 2. What we now understand [established, verified this arc]

1. **Schnakenberg entropy production is the wrong instrument.** It is defined on *cycle* currents and
   requires reciprocal transitions; its estimator (`graph.py`) skips any one-way edge (`if N_ij==0 or
   N_ji==0: continue`), mapping the *most* irreversible flow (a one-way attack path) to **zero**. It
   inverts the thesis. (Confirmed in code; benign traffic measured 74–83% reciprocal, so the estimator is
   non-zero on benign and zero on the acyclic attack — backwards.)

2. **Excess EP dissolves the "benign is irreversible" confound — and only that.** Scoring
   `D_KL(current-window transition distribution ‖ the actor's own trailing-baseline distribution)`
   correctly sends benign housekeeping (ETL/backup one-way NESS) to **~0**. This is real and it is the
   right physics for the confound. **But solving the confound revealed the signal has little left to
   catch** (see §3), rather than uncovering a hidden niche.

3. **Absolute flux (source/sink divergence) does not discriminate.** Benign one-way automation has
   maximal net flux; attacks do not exceed it. A flux-magnitude signal fires most on benign housekeeping.

4. **Evaluation must be at the attack-instance (campaign) grain, not the window.** Counting a slow attack
   as N overlapping windows is pseudo-replication and biases toward long-duration attacks. Detection =
   *did any in-budget alert overlap the campaign span* (per-incident, à la Hopper), which is
   duration-agnostic. Fairness must use an **instance-grouped** leakage red-team; a detector "win" that
   coincides with a landscape leak (a dumb shallow-feature cheat also catching it) is not real signal.

---

## 3. The central architectural limit [established] — distribution-preserving attacks

> **A distribution-comparison detector is structurally blind to any attack that preserves the transition
> distribution.**

**Living-off-the-land (LOTL)** is exactly this: the attacker reuses *only the actor's own edges*,
altering **order, rate, and destination** but not the *set* of transitions. Then the window's empirical
transition distribution ≈ the actor's baseline distribution, so
`excess-EP = D_KL(window ‖ baseline) ≈ 0`. Measured: P1e scores LOTL at ~×0.01 of benign — invisible.

This is not a tuning failure; it is a property of the functional. Excess-EP (a KL between edge-frequency
distributions) throws away temporal *ordering* and is only weakly sensitive to *rate*. LOTL lives
precisely in the discarded degrees of freedom.

**Corollary [current best]:** catching the hardest attacks requires **order/rate/sequence-sensitive**
statistics, not distributional ones. The distributional signal (excess-EP) is at best a partial,
complementary feature — never a standalone detector.

---

## 4. Where a physics signal *could* still contribute [current best / open]

Excess-EP has one regime where it is strong: **actors whose baseline NESS is very tight** (machine
service accounts with near-deterministic loops). There, any deviation is a large excess. Human actors
have noisy baselines → the signal drowns. So excess-EP is a *narrow*, actor-type-conditional feature.

The physically-motivated instruments that respect §3's corollary (ordering/rate sensitivity), none yet
built or validated here:

- **Transfer entropy / directed information** between resources — directional, temporal; but data-hungry.
- **Large-deviation / fluctuation-theorem scoring** — an attack as a rare *current fluctuation* under the
  benign NESS rate function. Principled, hardest to estimate.
- **Rate/burst and sequence-surprisal** measures — cheapest; overlaps with what a good rarity+context
  baseline already does.

The open empirical question (§5) is whether any of these beats a strong rarity+causal-context baseline.

---

## 5. Shaky areas & open questions

1. **[open, decisive] Does any physics instrument beat a rarity+causal-context baseline (Hopper-core, B1)
   by ≥5pp at a fixed alert budget?** Untested — B1 not yet built. Current *prediction*: no (KILL). This
   is the gate; everything else is secondary until it's run.

2. **[open] Is excess-EP's service-account niche real or a landscape artifact?** Its one strong flavor
   (SA-hijack) coincided with a fairness-gate leak a dumb cheat also exploited. Needs a **de-rigged
   landscape** (equalize degree/edge-diversity between attacks and hard-negative twins) before the niche
   can be trusted.

3. **[open, external validity — biggest risk] Does "housekeeping → 0" survive real data?** The clean
   `excess-EP ≈ 0` for benign depends on benign actors having *stable, low-entropy* NESS baselines. Real
   GCP actors (especially humans, on-call, role changes) may have much noisier baselines → inflated
   benign excess-EP → separation collapses. Only a real-data shadow pilot resolves this. All synthetic
   results are **necessary-bar, not sufficient**.

4. **[open] Estimator data requirements at realistic state-space size.** Convergence (~80 transitions/
   window) was measured on a toy 3-state chain. By the sample-complexity floor (n ~ S²/log S), a
   realistic 6–7-zone (and larger, per-resource) graph needs *more*. The rolling window may be too short;
   fast/few-transition attacks (smash-and-grab) are un-scorable from cold regardless.

5. **[open] Statistical power.** Per-flavor detection CIs need ~40+ independent campaigns/flavor. Not yet
   run at full held-out scale; LOTL fairness was inconclusive at dev scale (few instances).

6. **[contested] Does the physics framing add anything orthogonal, or is it dominated?** Even the
   `AUGMENT` outcome (physics as a feature inside a context-gated scorer, H2) is unproven. It's plausible
   excess-EP contributes a little on machine SAs on top of rarity+context — but that must clear the same
   ≥5pp lift bar, and LOTL-blindness caps its ceiling.

---

## 6. What would change the conclusion

- **Toward keep/augment:** a de-rigged landscape where excess-EP (or an ordering/rate measure) beats B1
  by ≥5pp on ≥1 honest flavor at equal FP, *and* the effect survives on real benign traffic.
- **Toward kill (current lean):** B1 matches/beats physics on its only niche (SA-hijack ≈ rare directed
  edge), physics stays dead on LOTL, and benign baselines are noisier on real data than synthetic.

---

## 7. Relationship to `physics_foundations.md`

That document argues the *original* thesis: sanctioned automation creates persistent asymmetric flux,
attackers add irreversible net current → detectable as an entropy-production spike, estimated via
Schnakenberg. **This arc refuted the operational core of that thesis** (§2.1, §1): irreversibility is not
anomaly, and Schnakenberg is structurally wrong for acyclic attack flows. The *spirit* survives only in
the much narrower excess-EP reframing — which is itself LOTL-blind (§3). Treat `physics_foundations.md`
as historical; this doc is the current view.
