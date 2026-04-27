# Phase B: Holistic MVP with Learned Representation Layer

**Status:** Augmentation to the MVP strategy. Picks up from the end of Sprint 2 (`Are signals robust across varied attack strategies?`). Does not modify Sprints 0, 1, or 2. Sprint 4 (Dashboard) continues in parallel as originally scoped.

**Pivot condition:** Phase B is conditional on Sprint 2's hypothesis passing — i.e., physics-informed signals on hand-engineered features achieving >80% detection rate across the parameterized attack grid. If Sprint 2 fails, Phase B is moot; the system has a different problem.

**Why Phase B exists:** The signals validated in Sprints 0-2 are computed on hand-engineered features (zone-flux matrix, count-based σ_coarse, hard-rule invariants). Two operational problems are not well-served by hand-engineered features: soft variation in legitimate workflows, and auto-discovery of unregistered patterns. Phase B addresses both by adding a learned representation layer in which the same physics-informed signals can be re-expressed, with the rate matrix learned from data rather than estimated by counting. This is the same theoretical framework — Markov jump processes, Schnakenberg entropy production — applied to a learned rather than hand-engineered state space.

The learned layer does not replace the hand-engineered layer. They run in parallel, and fusion combines their signals. The existing Sprint 3 work (provenance + closure) is folded into Phase B because the closure signals interact with the learned representation in ways worth designing jointly.

---

## Phase B Thesis

The hand-engineered layer (Sprints 0-2) demonstrates that physics-informed signals computed on a coarse-grained state space detect adversarial cloud-agent activity. Phase B asks: does a learned, continuous-time, graph-structured representation of the same activity, regularized to respect the same physics, improve detection — particularly on the operational regimes the hand-engineered layer struggles with (soft variation, unregistered patterns, pattern-registration transients)?

The build, again, is the experiment. Each Sprint B-N validates a hypothesis that builds on the previous. Failure is information.

---

## Architecture After Phase B

The presentation, policy, and ingestion layers are unchanged. The world model, scoring, and provenance layers acquire a parallel learned-representation pathway.

```
+==========================================================================+
|                         PRESENTATION LAYER                                |
|  (unchanged from MVP)                                                     |
+--------------------------------------------------------------------------+
|                         POLICY LAYER                                      |
|  (unchanged from MVP)                                                     |
+--------------------------------------------------------------------------+
|                         SCORING LAYER                                     |
|  [Hand-engineered: σ_coarse, invariants, novelty, ...]   (Sprints 0-2)  |
|  [Learned: TPP-likelihood score, latent anomaly score]    (Sprint B1)   |
|  [Physics-informed regularizers shape the learned scores] (Sprint B2)   |
|  [Closure: closure_ratio, orphaned_privilege]             (Sprint B3)   |
|  [Fusion: hand-engineered + learned -> residual_risk]                   |
+--------------------------------------------------------------------------+
|                         PROVENANCE LAYER                                  |
|  (Sprint 1 scaffold + Sprint B3 full integration)                        |
+--------------------------------------------------------------------------+
|                         WORLD MODEL LAYER                                 |
|  [15-min Windowing, Zone Flux 6x6, Actor Windows]      (Sprints 0-2)   |
|  [Event-relation graphs per actor-window]               (Sprint B1)     |
|  [TGN-style continuous-time graph encoder]              (Sprint B1)     |
+--------------------------------------------------------------------------+
|                         INGESTION LAYER                                   |
|  (unchanged from MVP)                                                     |
+--------------------------------------------------------------------------+
|                         INFRASTRUCTURE                                    |
|  (unchanged from MVP)                                                     |
+==========================================================================+
```

### Data Flow Addition

The existing flow from raw audit logs through ingestion → windowing → zone-flux → hand-engineered scoring is unchanged. After windowing, a parallel branch builds event-relation graphs and feeds them to the learned encoder:

```
[15-min Windowing]
        |
        +---> (existing) zone_flux_windows -> hand-engineered scoring
        |
        +---> (new B1) per-window event-relation graph
                       |
                       v
                 [TGN encoder] -> per-actor latent z_t
                       |
                       v
                 [Intensity head] -> λ(t, m | z_t)
                       |
                       v
                 [TPP likelihood] -> learned anomaly score
                       |
                       v
                 [Fusion (existing): combines hand-engineered + learned]
```

---

## Causal Validation Chain (Phase B)

```
Sprint 2 Complete: hand-engineered signals validated on real data
    |
    v
Sprint B1: Does a learned representation improve detection on its own?
    |
    +-- TPP-likelihood score improves AUC vs. hand-engineered baseline?
    |     YES --> learned representation has signal independent of hand-engineered
    |     NO ---> the hand-engineered layer is sufficient; defer Phase B
    v
Sprint B2: Does physics-informed regularization improve generalization?
    |
    +-- Detection on parameterized grid improves under regularization?
    |     YES --> physics priors are useful for the learned layer
    |     NO ---> regularization is over-constraining or mis-specified
    v
Sprint B3: Does the integrated system reduce false-positive rate
              during pattern-registration transients?
    |
    +-- FP-rate-during-transient drops with the learned layer?
    |     YES --> full Phase B thesis validated
    |     NO ---> hand-engineered + provenance subtraction is sufficient
    v
[Phase B complete: holistic MVP shipping]
```

---

## Sprint B1: Learned Representation Layer

**Hypothesis:** A continuous-time graph-structured representation of actor-window activity, trained with TPP likelihood, produces an anomaly score (negative log-likelihood of observed events) that adds detection value beyond the hand-engineered signals.

**What gets built:**

1. **Per-actor event-relation graph construction.** For each actor-window, build a heterogeneous graph: nodes are events typed by action, edges encode same-actor (trivially), same-resource, trigger-chain, and temporal-proximity (within configurable threshold). Implementation extends `world/graph.py` with a new `event_relation_graph.py` module. Graph construction must be deterministic and idempotent for testability.

2. **TGN-style continuous-time encoder.** Per-node memory updated by each event, message passing on the relation graph at event times, continuous-time positional encoding (Time2Vec or Hawkes-kernel based) for inter-event intervals. Output: per-actor latent state z_t at the end of each window. Implementation: new module `world/temporal_graph.py`. Standard reference implementations (TGN, JODIE) are a starting point; expect 2-3 weeks to adapt to the heterogeneous event-graph setting.

3. **Intensity-function head.** MLP that consumes z_t and outputs parameters of a marked-Hawkes-style intensity function over event types. Numerical integration of the intensity uses a thinning algorithm. New module `score/tpp.py`.

4. **TPP likelihood loss.** Negative log-likelihood of observed window events under the predicted intensity. Standard formulation; care needed in handling very bursty windows where intensities span many orders of magnitude.

5. **Anomaly score:** per-window negative log-likelihood, normalized to be comparable across actor activity levels.

6. **Integration into fusion.** Add the learned anomaly score to `score/fusion.py` as one signal alongside the existing hand-engineered ones. Initial weight is small; tune empirically based on benchmark performance.

**What does not get built in B1:**

- Physics regularization (deferred to B2)
- Provenance integration with the learned layer (deferred to B3)
- The CD adaptation machinery (post-MVP, see post_mvp_roadmap.md)

**Dataset and training:**

- Train on legitimate-only windows from the hydration data accumulated through Sprints 0-2.
- Validate anomaly score on the parameterized attack grid from Sprint 2.
- Standard temporal split (train on earlier windows, evaluate on later) to avoid leakage.

**Decision gate:**

- AUC of TPP-NLL anomaly score vs. labels on the benchmark corpus.
- Improvement in fused detection (hand-engineered + learned) over hand-engineered alone, on the parameterized attack grid.
- If both show improvement: proceed to Sprint B2. If neither: the hand-engineered layer is sufficient and Phase B is deferred or abandoned.

**Estimated effort:** 4-6 weeks. The TGN component is the longest pole.

**Risks:**

- TGN training is more finicky than transformer training. Budget for hyperparameter tuning.
- Heavy-tailed intensities can cause numerical instability in likelihood computation. Plan for log-space implementations and gradient clipping.
- Small training data volumes early in MVP deployment may limit what the encoder can learn. Mitigation: pretrain on synthetic traffic from the parameterized generator.

---

## Sprint B2: Physics-Informed Regularization

**Hypothesis:** Adding non-equilibrium thermodynamic constraints as auxiliary losses on the TPP intensity function shapes the learned representation toward physically meaningful structure and improves generalization to attack patterns not seen at training time.

**What gets built:**

1. **Flux-conservation loss (local).** A differentiable penalty on intensity-function predictions that violate node-level flux conservation at non-source/sink nodes in the zone graph. The flux at a node is the sum of integrated intensities over outgoing edges minus incoming; for legitimate workflows with closed causal chains, this should be near-zero. Implementation: new term in `score/tpp.py` loss.

2. **Schnakenberg consistency loss (global).** A penalty on the discrepancy between σ_coarse computed from the model's predicted intensities (analytically, via the cycle decomposition in `theory/schnakenberg_formalization.md`) and σ_coarse computed from raw event counts (the existing hand-engineered signal). This is a self-consistency constraint: the learned rate matrix should imply the same entropy production as the empirical rate matrix.

3. **Detailed-balance-aware prediction (temporal).** An augmented prediction objective that penalizes intensity predictions violating detailed balance for windows matched to sanctioned patterns, while leaving the prediction unconstrained for unmatched windows. Sanctioned activity should sit near detailed balance; unsanctioned activity is allowed to be far from it.

4. **Ablation harness.** A test setup that trains four models — TPP-only, TPP + flux conservation, TPP + Schnakenberg, TPP + all three — and evaluates each on the parameterized attack grid. The deliverable is the ablation table.

**Theoretical anchor:** `docs/theory/schnakenberg_formalization.md` Sections 3 and 5. The flux-conservation loss formalizes the closure intuition. The Schnakenberg loss formalizes the connection between learned and hand-engineered signal layers. The detailed-balance loss formalizes the difference between sanctioned and unsanctioned activity in non-equilibrium-thermodynamic terms.

**Decision gate:**

- Does the regularized model improve generalization to unseen attack patterns (out-of-grid) more than the unregularized model?
- Does the regularized latent show better alignment with physical observables (zone occupations, flux magnitudes) than the unregularized one?
- If yes: integrate the regularized model into fusion. If no: the regularization is mis-specified or over-constraining; iterate or revert to TPP-only.

**Estimated effort:** 4-6 weeks. Most of the time is in the Schnakenberg consistency loss, which requires careful numerical work to differentiate the cycle decomposition.

**Risks:**

- Physics constraints can over-bias a model that needs flexibility. Catch this in the ablation: if every regularized variant underperforms TPP-only, the constraints are too tight.
- The cycle decomposition is not differentiable in general (cycle basis selection is combinatorial). Use a fixed cycle basis derived from the zone graph at MVP build time; the basis can be re-derived if the zone graph changes.

---

## Sprint B3: Provenance Integration and Closure

**Hypothesis:** Sanctioned-pattern provenance subtraction has a clean expression in the learned representation as a decomposition of the rate matrix into sanctioned and residual components, and this composes more cleanly with the closure signals than the hand-engineered version does.

This sprint takes over the work originally scoped for the existing Sprint 3 (provenance + closure) and integrates it with the learned layer. The hand-engineered residual_risk computation is not replaced; the new computation runs in parallel and feeds fusion.

**What gets built:**

1. **Sanctioned-pattern rate-matrix contribution.** For each registered sanctioned pattern, compute its analytic contribution to the rate matrix (which zones it touches, in what order, at what rate). Implementation: extend `provenance/patterns.py` with a `pattern_to_rate_contribution()` function.

2. **Residual rate matrix.** Subtract sanctioned contributions from the learned rate matrix to get a residual rate matrix that represents unattributed activity. Schnakenberg entropy production computed on the residual rate matrix is the learned-layer analog of `compute_residual_risk`.

3. **Closure signals on the learned layer.** Reformulate `closure_ratio` and `orphaned_privilege` as flux-imbalance measurements on the learned rate matrix. The hand-engineered versions still ship; the learned versions are additional signals in fusion.

4. **Trigger chain resolution unchanged.** Trigger chain resolution is a deterministic graph operation on event metadata, not a learned operation, and is implemented as in the original Sprint 3.

5. **Pattern-registration transient evaluation.** A specific test: register a new sanctioned pattern partway through a stream of windows, measure FP-rate before and after registration. The learned layer with provenance subtraction should show a smaller transient than the hand-engineered layer alone.

**Decision gate:**

- Does the integrated learned + provenance system reduce FP-rate-during-transient compared to the hand-engineered + provenance system?
- Does total FP-rate at steady state drop?
- If yes: the holistic MVP ships. If no: the hand-engineered system remains primary, and the learned layer is shipped as an experimental feature pending more work.

**Estimated effort:** 3-5 weeks. Most components are extensions of existing Sprint 3 work; the new integration with the learned layer is the additional cost.

**Risks:**

- The learned rate matrix may not decompose cleanly into sanctioned + residual if the encoder doesn't respect the zone structure tightly enough. Sprint B2's Schnakenberg consistency loss helps here, but is not a guarantee.
- Pattern-registration transient measurement requires the ability to register patterns mid-stream, which is supported by the architecture but needs explicit testing harness.

---

## Phase B Definition of Done

In addition to the original MVP definition of done:

1. **Learned representation operational.** TGN encoder + TPP intensity head + likelihood loss training stably on real data, producing a per-window anomaly score.
2. **Learned score adds value.** TPP-NLL anomaly score improves AUC on benchmark corpus when added to fusion. Quantified target: ≥3% AUC improvement, or improvement on at least one operational regime (soft variation, unregistered patterns, transient FP) where hand-engineered signals struggle.
3. **Physics regularization validated.** Ablation table comparing TPP-only vs. regularized variants on parameterized attack grid. Best variant integrated into fusion.
4. **Provenance integration working.** Sanctioned-pattern rate-matrix contributions computed, residual rate matrix produced, residual entropy production used in fusion.
5. **Transient FP reduction demonstrated.** Pattern-registration transient test shows FP-rate reduction compared to hand-engineered + provenance baseline.
6. **Tests green.** Coverage on new modules ≥80%. Integration tests covering the full hand-engineered + learned + provenance pipeline.
7. **Theoretical documentation current.** `docs/theory/schnakenberg_formalization.md` Sections 5-6 reflect the integrated implementation. New doc `docs/theory/learned_representation.md` covers the TGN + TPP design (written during B1).
8. **Dashboard accommodates learned signals.** The Pulse + Flow Map + Lineage views surface learned-layer signals appropriately. This is a small extension of the Sprint 4 work.

---

## Total Phase B Effort

| Sprint | Estimated Effort | Cumulative |
|---|---|---|
| B1: Learned representation | 4-6 weeks | 6 wk |
| B2: Physics-informed regularization | 4-6 weeks | 12 wk |
| B3: Provenance integration | 3-5 weeks | 17 wk |

Phase B follows the end of Sprint 2 (~Week 4 of the original MVP). Total elapsed time from project start to Phase B complete: ~17-21 weeks. Sprint 4 (Dashboard) runs in parallel from Sprint 1 and is complete by ~Week 8.

If pace is a constraint (investor demo, runway), Phase B can be split: ship the original MVP at Week 5 with Sprint 3's hand-engineered provenance, then begin Phase B as a continuation. The Phase B sprints become post-original-MVP milestones in this case, and `post_mvp_roadmap.md` should be updated to reflect that the items it lists as Phase 1.1, 2.1, 2.2 are subsumed by Sprints B1-B3.

---

## What Phase B Replaces in `post_mvp_roadmap.md`

If Phase B is executed as part of the holistic MVP, several items in `post_mvp_roadmap.md` are subsumed and should be marked accordingly:

- Phase 1.1 (sigma_relative / EMA baseline) — subsumed by B1's TPP-NLL score and B2's Schnakenberg consistency. The non-adiabatic decomposition view becomes a property of the learned layer rather than a separate signal.
- Phase 2.1 (auto-observed pattern discovery) — partially subsumed; clustering in the learned latent space is a more principled basis for auto-discovery than clustering on hand-engineered features. Detail work on the discovery algorithm itself remains post-MVP.
- Phase 2.2 (per-actor behavioral profiling) — subsumed; the per-actor latent state z_t is a learned behavioral profile, with prediction error as the deviation signal.

The remaining post-MVP items (transfer entropy, adversarial hardening, full dashboard, shadow bandit, STRONG provenance) are unaffected by Phase B and remain as written.

---

## Decision Recap

This Phase B plan is structured so that the original MVP (Sprints 0-4) is unchanged and ships independently if Phase B is deferred or abandoned. Phase B is a conditional continuation, not a replacement.

The decision points are:

1. **End of Sprint 2:** Did hand-engineered physics signals validate? If no, Phase B is moot.
2. **End of Sprint B1:** Does the learned representation add value? If no, Phase B stops here and the original Sprint 3 (hand-engineered provenance + closure) takes over.
3. **End of Sprint B2:** Does physics regularization help? If no, ship TPP-only and proceed to B3.
4. **End of Sprint B3:** Does the integrated system reduce transient FP? If no, learned layer ships as experimental, hand-engineered remains primary.

Phase B is research-grade work integrated into the MVP path. It does not delay shipping the core thesis — that hand-engineered physics signals + provenance subtraction detect adversarial cloud-agent activity — because that thesis ships regardless of B's outcome at the end of the original Sprint 4. What Phase B adds is a more holistic, learned, and theoretically integrated system, conditional on the experiments succeeding.
