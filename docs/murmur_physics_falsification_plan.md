# Murmur Physics-Signal Falsification Plan
**Adversarially-fair synthetic landscape + relative-discrimination bake-off**
Date: 2026-07-02 · Status: ready for implementation · Intended executor: Opus 4.8 (Claude Code session)

---

## 0. Mission statement (read this before writing any code)

Decide, via falsification, whether Murmur's per-actor irreversibility signals (forward/reverse KL divergence, flux divergence, and their ensemble) earn their place in the detection stack — or get cut.

The epistemics are asymmetric and non-negotiable:

- **Synthetic can KILL the physics signal.** If it cannot beat a faithful Hopper-style baseline on a landscape that is fair-or-hostile to physics, it is dead. That is a legitimate, final outcome.
- **Synthetic can only provisionally PASS it.** A win here means "cleared a necessary bar, pending real-data confirmation in a shadow-mode pilot." Never phrase a synthetic win as validation.

We are answering validation question **#2 (relative discrimination against known confounds)** plus **#1 (mechanism correctness)**. We are explicitly **not** answering **#3 (absolute FP rate in production)** — no synthetic result may be reported as an absolute FP rate. Any code, docstring, or report that drifts toward #3 language is a bug.

### Non-goals
- No realism claims about benign traffic. The landscape must be *adversarially fair*, not realistic.
- No comparison against Kairos/Flash/ShadeWatcher/MAGIC. Wrong layer (syscall provenance), unreproducible numbers, contested ground truth. They are backdrop, not controls.
- No production hardening, streaming, or performance work. Correctness and statistical rigor only.
- No tuning-to-win. Degrees-of-freedom discipline is specified in §7 and is mandatory.

---

## 1. Decision structure (pre-registered — freeze before running final evaluation)

Three possible outcomes, decided by criteria written down *now*, not after seeing results:

| Outcome | Criterion (evaluated on held-out world seeds, §7) | Consequence |
|---|---|---|
| **KILL** | Best physics variant (including ensemble, including physics-as-feature) fails to exceed baseline B1's detection rate at the fixed alert budget, with the 95% CI of the paired difference including or below zero — OR wins only on worlds where hard-negative confounds are absent/weak | Cut the physics layer. Murmur's differentiation rests on provenance-subtraction + self-learning. Document in LEARNINGS.md as a clean negative result. |
| **AUGMENT** | Physics-as-feature inside the Hopper-style scorer (H2, §5) beats both B1 alone and P* alone, CI clear of zero, and the lift survives the hard-negative worlds | Physics survives as a *feature*, not a standalone detector. Reframe positioning accordingly. |
| **PROVISIONAL PASS** | A standalone physics variant or ensemble beats B1 at equal alert budget, CI clear of zero, across ≥ 80% of held-out world seeds, including the hostile-confound worlds | Label: "passed necessary bar, pending real-data confirmation." Next step is shadow-mode pilot (GTM milestone, out of scope here). |

Pre-register the margin: the paired detection-rate difference must be **≥ 5 percentage points at the fixed budget** (mean across held-out seeds) to count as a win. Anything smaller is a KILL-by-insufficient-lift even if statistically nonzero — a signal that adds 1–2 points does not justify a physics layer's complexity.

Ties and ambiguity resolve toward KILL. The burden of proof is on physics.

---

## 2. Domain model

Murmur's target layer is the **cloud IAM / auth event graph** (GCP-flavored), not syscall provenance. This is the granularity where per-actor trajectories are dense enough for distribution estimation and where the semantics (identity moving through resources) match the physics.

### 2.1 Entities
- **Actors**: human users, service accounts. Each has a role archetype (§3.1).
- **Resources**: nodes partitioned into functional zones. Use ≥ 6 zones so zone-count can't leak labels: `IDENTITY`, `SECRET`, `DATA`, `COMPUTE`, `LOGGING`, `EXTERNAL`, `ADMIN`. (Zone names are for the generator and evaluator ONLY — see anonymization, §4.3.)
- **Events**: tuples `(t, actor, src_resource, dst_resource, action_type)`. Actions from a small vocabulary (auth, read, write, invoke, grant, assume) — enough to express credential-switch analogs without exploding the state space.

### 2.2 Trajectories
A per-actor trajectory is the time-ordered sequence of that actor's transitions over the resource graph. All physics estimators operate on per-actor trajectories; all baselines operate on the same event stream. **Every detector sees identical input** (the anonymized event log) — no detector gets privileged fields.

---

## 3. Synthetic landscape: generative model

### 3.1 Benign actor archetypes (the world's population)
Implement each as a semi-Markov process over the resource graph with archetype-specific transition structure, dwell times, and diurnal/weekly rhythm. Minimum set:

1. **Developer** — daily loop: IDENTITY → COMPUTE → DATA(read) → COMPUTE → logout. Strongly cyclic; near time-reversible at the distribution level.
2. **Data analyst** — IDENTITY → DATA(read-heavy) → COMPUTE, occasional SECRET access for connection credentials. Cyclic.
3. **CI/CD service account** — high-frequency, extremely regular: IDENTITY → SECRET → COMPUTE → DATA(write). Machine-regular loops.
4. **ETL pipeline service account** — **deliberately irreversible benign flow**: IDENTITY → SECRET → DATA(read) → EXTERNAL(write). One-way by design. *This archetype exists to punish any detector that equates "irreversible" with "malicious."*
5. **Backup / log-shipping account** — another benign one-way flow: DATA → LOGGING / DATA → EXTERNAL, on a fixed schedule. Same purpose as #4, different shape.
6. **On-call SRE** — mostly dormant; during on-call windows, sudden rare access to machines/resources never touched before. *The canonical Hopper false-positive.*
7. **New hire** — starts with zero history, explores broadly for the first N days, then settles into a developer/analyst pattern. Rare-by-construction, benign.
8. **Role change** — mid-simulation, an existing actor's archetype switches (e.g., developer → SRE). Old distribution becomes stale; everything looks novel.
9. **Break-glass admin** — very rare, high-privilege one-shot: IDENTITY → ADMIN → SECRET, then back to dormancy. Rare, irreversible-looking, benign.

Population sizing per world: ~200–500 actors, mixture weights randomized per seed within sane ranges (e.g., 40–60% developers, 5–15% service accounts, guarantee ≥ 3 instances each of archetypes 4–9 so confounds are always present). Simulation horizon: 60–90 virtual days at event rates giving each actor **enough transitions for estimator convergence per §6.3's minimum-trajectory analysis** — this coupling matters; do the convergence study first.

### 3.2 Attack archetypes (injected into a subset of worlds/actors)
Each attack is an *overlay on a compromised existing actor* (or a newly minted service account, for one variant), never a special node type. Minimum set:

1. **Credential-theft lateral movement** (Hopper's target): compromised developer begins traversing IDENTITY → COMPUTE → COMPUTE' → SECRET → DATA, using an assume/grant action mid-path (credential-switch analog), reaching resources outside the causal actor's history.
2. **Slow exfiltration**: compromised analyst adds a low-rate DATA → EXTERNAL drip over weeks, keeping per-day rarity minimal. Tests whether trajectory-level asymmetry catches what per-edge rarity can't.
3. **Smash-and-grab**: fast, one-session IDENTITY → SECRET → DATA → EXTERNAL burst. The easy case; every detector should catch this (sanity anchor).
4. **Living-off-the-land (the crown-jewel test)**: attack uses **only edges that exist benignly in that actor's own history**, altering only sequencing/direction/rate — e.g., an ETL account's legitimate path run in a novel order terminating in EXTERNAL at 10× volume. Per-edge rarity is *zero signal* here by construction. If physics has a real edge over rarity+context, this is where it must show.
5. **Service-account hijack**: CI account (archetype 3) deviates from its machine-regular loop into SECRET → EXTERNAL. Tests regularity-break detection.

Injection protocol: per attack-world, compromise 1–3 actors, chosen uniformly from eligible archetypes. Attack onset uniformly in the middle third of the horizon (so pre-attack history exists for per-actor baselining). Ground-truth labels: `(actor, time-window)` pairs, generator-side only.

### 3.3 Hard negatives (the removal of cheats)
These are *mandatory benign structures that mimic attack shapes*:

- **ETL twin**: for each world containing attack #2 or #3's IDENTITY → SECRET → DATA → EXTERNAL shape, ensure a benign ETL account (archetype 4) runs IDENTITY → SECRET → DATA → EXTERNAL with **matched path length, matched per-edge rarity percentile, and matched zone sequence**. The only differences are behavioral (rate profile, regularity, relation to the actor's own history).
- **On-call storm**: at least one on-call window overlapping each attack window in time, so temporal co-occurrence can't be the discriminator.
- **Novelty flood**: new-hire and role-change events distributed across the horizon, ensuring "actor doing something they've never done" is common and benign.

---

## 4. Anti-cheat controls (fairness spec)

The landscape is invalid unless ALL of the following hold. Implement each as an automated check in the harness (a `fairness_audit.py` that runs on every generated world and fails loudly):

### 4.1 Structural equalization
- Zone counts, node degrees, and per-zone event volumes must not statistically separate attack-worlds from clean-worlds (two-sample tests, pre-registered α = 0.01; if separable, regenerate).
- Attack path lengths must fall within the benign path-length distribution's interquartile range.
- Per-edge rarity of attack edges must be matched (±1 decile) by hard-negative benign edges present in the same world.

### 4.2 No label leakage
- Detectors receive an **anonymized** event log: resource IDs are random hashes, zone labels stripped, action types mapped to opaque tokens, actor IDs random hashes. Only the generator and the evaluator hold the mapping.
- Grep-level check: no string from the generator's label vocabulary (`EXFIL`, `ATTACK`, zone names, archetype names) may appear in any detector-visible artifact.
- Timestamps are real-valued; no attack may be identifiable by timestamp arithmetic artifacts (e.g., attacks always starting on integer hours). Jitter everything.

### 4.3 Leakage red-team (adversarial audit of the landscape itself)
Before any physics vs. baseline comparison, train a deliberately dumb "cheat detector" (logistic regression on shallow world-level features: event counts, degree histograms, unique-edge counts) to distinguish attack windows from benign. If the cheat detector achieves better-than-chance discrimination (AUC-PR above the no-skill line, CI clear), **the landscape is rigged — fix the generator, do not proceed.** This is the single most important gate in the whole plan.

### 4.4 Determinism
- Every world fully determined by `(config, seed)`. Store both. Regeneration must be byte-identical.

---

## 5. Detectors under test

All detectors output a **ranked stream of (actor, time-window) alerts** and are evaluated at a fixed alert budget (§6.1). Same input, same output contract, same budget.

### Baselines (controls)
- **B0 — naive rarity**: score = negative log empirical frequency of each traversed edge, per actor-window. The strawman; must lose to B1 (sanity check that confounds work).
- **B1 — Hopper-style rarity + causal context** (THE bar to beat): rare-transition scoring gated on (a) credential-switch analog present in the path (assume/grant mid-path with identity mismatch), and (b) path reaches a resource absent from the causal actor's history, with an alert-budget ranking mechanism per the Hopper paper (USENIX Sec '21). Reimplement faithfully; where the paper is ambiguous, resolve ambiguity **in B1's favor** and document each such choice.
- **B2 — shallow ML sanity**: logistic regression / gradient boosting on hand features (edge rarity percentiles, new-resource count, session length, hour-of-day). Not a headline comparison; exists to catch "physics only beats hand-tuned heuristics but loses to 30 minutes of sklearn."

### Physics variants
- **P1 — forward/reverse KL**: per-actor, per-window: estimate transition distribution over the actor's observed state space; compute D_KL(forward ‖ reverse) on trajectory segments. Estimator details in §6.3.
- **P2 — flux divergence**: per-actor net probability flux per edge (forward minus reverse empirical flux), aggregated per window (e.g., L1 norm of net-flux vector, and max-edge variants — pre-register which aggregation is primary).
- **P3 — ensemble**: rank-average of P1 + P2 (per PMC8622570's finding that irreversibility-measure ensembles dominate single instruments). Pre-register rank-average as the primary combiner; logistic stacking allowed as secondary, trained only on dev worlds.
- **H2 — physics-as-feature (hybrid)**: B1's scorer with P1/P2 window scores appended as features. This is the AUGMENT-outcome candidate and must be built — the Hopper lesson says context rescues rarity, and physics is structurally a rarity statistic; its best chance may be *inside* the context gate, not against it.

Explicitly out of scope: Schnakenberg entropy production as a standalone detector (killed by the cycle-dependence finding — acyclic per-actor paths yield zero/undefined EP; see graph.py:55). Keep one unit test documenting *why* it's excluded.

### 5.1 Confound-inheritance warning (bake into design review)
P1/P2 are sophisticated rarity/asymmetry statistics. They WILL fire on archetypes 4, 5, 9 (benign one-way flows) unless the per-actor baselining does its job: irreversibility must be scored **relative to the actor's own historical asymmetry**, not in absolute terms. Concretely: primary physics score = current-window asymmetry minus (or normalized by) that actor's trailing-history asymmetry. An ETL account is *always* irreversible; the signal is a *change* in asymmetry structure. Pre-register this relative formulation as primary; absolute asymmetry as a reported-but-secondary ablation.

---

## 6. Evaluation protocol

### 6.1 Primary metric
**Detection rate at fixed alert budget** (K alerts per virtual day, K pre-registered — suggest K such that budget ≈ Hopper's <9/day scaled to world size), where a detection = any alert whose (actor, window) overlaps a ground-truth attack window. Secondary: AUC-PR (never ROC-AUC — extreme class imbalance makes ROC flattering and it's the exact sin of the SOTA papers), alert-cause composition (which archetypes generate the false positives — this diagnostic is half the scientific value), time-to-first-detection, and per-attack-archetype breakdown (a detector that only catches smash-and-grab is worthless).

### 6.2 Statistical design
- **World replication**: N ≥ 20 held-out world seeds for final evaluation (plus dev worlds, §7). Report per-detector mean ± bootstrap 95% CI; decisions use **paired** differences (same worlds, different detectors).
- **World mix**: 50% attack worlds, 50% clean worlds. Clean worlds exist to compare *relative* FP behavior between detectors (never report as absolute FP rates — see §0).
- **Hostile-confound tier**: of the attack worlds, half are "hostile" (hard-negative density doubled, living-off-the-land attacks over-weighted). PASS criteria (§1) explicitly require survival on this tier.

### 6.3 Mechanism tests (validation question #1 — run FIRST, before any world generation)
Unit-level tests on constructed inputs; these test the estimator, not the world:

1. **One-way vs. loop**: a strictly one-directional path scores strictly higher on P1/P2 than a closed loop of equal length and equal edge count. (The defining property.)
2. **NESS anchor**: construct a 3-state nonequilibrium steady state (constant occupation probabilities, nonzero cycle flux). Verify Shannon-entropy rate of change ≈ 0 while P1/P2 read strongly positive. (The foundational justification, now as executable test.)
3. **Permutation/reversal sanity**: time-reversing a trajectory must swap forward/reverse KL (D_KL(f‖r) ↔ D_KL(r‖f)); a genuinely reversible (detailed-balance) chain's trajectories must score ≈ 0 in expectation.
4. **Estimator convergence**: P1/P2 score vs. trajectory length on a known-asymmetry chain — establish the minimum trajectory length for stable estimates, with the chosen smoothing (pre-register: additive smoothing with α chosen on synthetic chains ONLY, before seeing any world data; unseen-transition handling documented). **The output of this test parameterizes §3.1's simulation horizon.** If convergence needs more data than a plausible IAM log provides per actor per window, that is itself a KILL-relevant finding — report it prominently.
5. **Subsampling robustness**: drop 10/30/50% of events uniformly; scores must degrade gracefully, not chaotically.

Failing any of tests 1–3 means the implementation is wrong — fix before proceeding. Test 4 failing (absurd data requirements) escalates to the decision memo.

---

## 7. Degrees-of-freedom discipline (mandatory)

This is where bake-offs silently rot. Rules:

1. **Three-way world split**: *mechanism* (constructed inputs, §6.3) → *dev worlds* (10 seeds; all tuning, smoothing choices, window sizes, ensemble weights happen here and ONLY here) → *held-out worlds* (≥ 20 fresh seeds; run ONCE, after a written freeze declaration).
2. **Freeze declaration**: before touching held-out seeds, commit a `FREEZE.md` listing every hyperparameter of every detector, the primary metric, the budget K, and the §1 criteria verbatim. Anything changed after freeze restarts the held-out set with new seeds.
3. **Equal tuning budget**: B1 and B2 get the same dev-world tuning effort as P1–P3/H2. An under-tuned baseline is a rigged bake-off in physics's favor — the failure mode this entire plan exists to avoid.
4. **Ambiguity resolves against physics**: any judgment call in world design, metric definition, or baseline implementation that could tilt the comparison gets resolved in the baseline's favor, and logged in `JUDGMENT_CALLS.md`.
5. **No peeking**: held-out world ground truth is loaded only by the evaluator module; detector code paths must be physically unable to import it (enforce via module structure + a test).

---

## 8. Implementation plan (phased, with acceptance gates)

Suggested repo layout:

```
murmur-bakeoff/
  worldgen/        # archetypes, attack overlays, hard negatives, anonymizer
  detectors/       # b0_rarity, b1_hopper, b2_ml, p1_kl, p2_flux, p3_ensemble, h2_hybrid
  harness/         # runner, alert-budget evaluator, pairing, bootstrap CIs
  audits/          # fairness_audit, leakage_redteam, grep_leak_check
  mechanism_tests/ # §6.3 tests
  configs/         # world + detector configs, seeds
  reports/         # auto-generated per-run reports
  FREEZE.md  JUDGMENT_CALLS.md  DECISION_MEMO.md
```

**Phase 1 — Mechanism (gate: all §6.3 tests 1–3 pass; test 4 yields a concrete min-trajectory number).**
Implement P1/P2 estimators + the five mechanism tests. No world code yet.

**Phase 2 — Worldgen + fairness audit (gate: leakage red-team (§4.3) finds nothing; fairness_audit green on 10 trial seeds).**
Benign archetypes → attacks → hard negatives → anonymizer → audits. Iterate generator until the cheat detector is at chance.

**Phase 3 — Baselines (gate: on dev worlds, B1 beats B0 decisively and B0's false positives are dominated by archetypes 6–9).**
This gate proves the confounds work as designed. If B0 isn't fooled by on-call/new-hire noise, the landscape isn't testing anything.

**Phase 4 — Physics + hybrid on dev worlds (gate: relative-asymmetry formulation implemented; tuning complete; FREEZE.md committed).**

**Phase 5 — Held-out evaluation (run once).**
N ≥ 20 fresh seeds, paired analysis, bootstrap CIs, per-archetype FP composition.

**Phase 6 — Decision memo.**
`DECISION_MEMO.md`: outcome per §1 criteria, headline table (detection@budget, AUC-PR, per-attack-type breakdown), FP composition, the living-off-the-land result called out specifically, limitations (foremost: synthetic ⇒ no absolute-FP claims; PASS is provisional pending shadow pilot), and the explicit next action (cut / reposition-as-feature / carry to shadow pilot). Update CURRENT_STATE.md and LEARNINGS.md.

---

## 9. Pitfall checklist (re-read at every phase gate)

- [ ] Am I anywhere reporting or implying an absolute FP rate? (Forbidden — §0.)
- [ ] Can any detector see zone names, archetype labels, or generator internals? (§4.2)
- [ ] Did the cheat detector really come out at chance, with CIs, not just "looks fine"? (§4.3)
- [ ] Is B1 as strong as I can honestly make it? Would Hopper's authors recognize it? (§7.3)
- [ ] Are benign one-way flows (ETL, backups, break-glass) present in EVERY world? (§3.1/#4,5,9)
- [ ] Is the physics score *relative to the actor's own history*, with absolute as ablation only? (§5.1)
- [ ] Does the living-off-the-land attack really have zero per-edge rarity signal? Verify programmatically.
- [ ] Any post-freeze change? Then the held-out seeds are burned — regenerate.
- [ ] Does every result table carry the "necessary bar, not sufficient — pending real-data confirmation" caveat?

---

## 10. What success and failure both buy us

- **KILL** → a clean, defensible negative result: "we tested the physics hypothesis against a faithful Hopper-style control on an adversarially fair landscape and it did not earn its complexity." Murmur simplifies; the write-up is still publishable as an honest negative.
- **AUGMENT** → physics repositioned as a feature inside a context-gated detector; smaller claim, more defensible.
- **PROVISIONAL PASS** → the necessary bar is cleared and the shadow-mode pilot (one real GCP org, GTM milestone) becomes the sole remaining gate — with a pre-existing, pre-registered harness to run there.

In all three cases the deliverable is the same: a decision no reviewer can dismiss as a rigged demo.
