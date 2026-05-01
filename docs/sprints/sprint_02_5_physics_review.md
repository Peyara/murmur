# Sprint 2.5: Physics Signal Architecture Review

## Hypothesis

`sigma_coarse` and `delta_f` fired 0% on attack across two independent harness configurations (Sprint 2 attack-only PR #36 + Sprint 2 attack-in-benign PR #37). This is empirical refutation of the *current implementation*, not the *physics-informed framing*. The 0% pattern is suspiciously clean — implementation bugs and calibration mismatches produce that shape; conceptual failures usually leave a tail. Some physics-flavored signal should be recoverable.

## Prerequisites

PR #37 merged to main (done — merge commit `f21fd13`). The existing 50-trajectory grid + 121 benign-only (window, actor) pairs from PR #37 are the test substrate. No new data generation in scope.

## Falsifier (locked before Day 1)

**Discrimination ratio = max(attack_fire_rate / benign_fire_rate, attack_mean_max / benign_mean_max)** measured on existing PR #37 data.

| Result | Action |
|---|---|
| ≥2.0x | Keep at standard fusion weight (alongside `inv_score`). |
| 1.5–2.0x | Keep at low fusion weight (≤0.04). Note as supporting signal. |
| <1.5x | Set fusion weight=0. CLAUDE.md framing amended to "physics-informed (aspirational; current implementation supports invariants + closure as load-bearing signals)." Branding retained; technical claim retired. |

The 1.5x floor is meaningfully above novelty/bridge_new (1.2x ≈ noise) and below `inv_score`'s 2.2x. Locked before Day 1; no negotiation.

## Stack Layers

- **Scoring physics:** `src/score/physics.py`, `src/score/fusion.py` (sigma_coarse, delta_f weighting + normalization)
- **World model flux:** `src/world/graph.py:compute_zone_flux` (where sigma_coarse is computed)
- **Validation:** `src/validation/baseline_robustness.py` (re-uses existing PR #37 harness for re-runs)

## Duration: 2-3 days

R&D mode, not autonomous. Day 1 has an explicit user-review checkpoint before Day 2 commits to a fix path.

---

## Why This Sprint Matters

Sprint 2's empirical 0% physics fire rate produced a strong but premature conclusion ("architecturally dead"). Conflating empirical refutation with mechanistic refutation forecloses recovery paths that are likely available. This sprint resolves that ambiguity with a controlled, falsifiable review.

The product framing — "physics-informed trajectory risk engine" — is retained as aspirational regardless of outcome. The technical question is whether the *current implementation* supports the framing or whether it's a placeholder for future work. Clarity on this distinguishes load-bearing from supporting from absent signals.

---

## Predictions (commit BEFORE Day 1 starts)

| Outcome | Prior probability | Reasoning |
|---|---|---|
| A: Implementation bug | 35% | 0% across two harnesses is suggestive of a degenerate computation. Bugs produce clean failures; conceptual failures usually leave a tail. |
| B: Calibration mismatch | 30% | `SIGMA_SIGMOID_X0=3.0` has no documented basis. If raw values live in 0.01–0.1 range, sigmoid output is essentially zero everywhere. |
| C: Conceptual mismatch | 25% | "Zone-flux variance" is one analog among many. Information-theoretic alternatives (KL divergence on action distributions, zone-crossing entropy, detailed balance) may carry the framing better. |
| D: Genuinely refuted | 10% | Even if literal sigma_coarse is wrong, *some* physics-flavored signal should discriminate. Unlikely all variants fail at ≥1.5x. |

65% probability the issue is in (A) or (B) — fixable without rebuilding. Document the prior at sprint start.

---

## Day 1 — Diagnostics (no fixes)

Three probes in order. Each has a binary output that selects the next probe or stops.

### 1. Implementation probe

Construct a synthetic input by hand: 5 windows with constant low-rate benign-only activity, 1 window with a sharp spike (e.g., 10x normal zone-crossing rate). Run through `compute_zone_flux` and read raw `sigma_coarse` for the spike window.

- **Expected if implementation correct:** spike window's sigma_coarse measurably above quiet windows.
- **If sigma_coarse is 0 or unchanged:** implementation bug. Likely candidates: per-window variance instead of cross-window, missing baseline reference, divide-by-zero returning 0, or wrong window scope.

### 2. Calibration probe

If implementation probe passes, histogram raw sigma_coarse values across the full PR #37 data:
- 50-trajectory grid (attack-in-benign) — extract sigma_coarse from `risk_scores` table per (window, actor).
- 121 benign-only (window, actor) pairs — same.

Compare distribution to the sigmoid: `SIGMA_SIGMOID_K=1.0`, `SIGMA_SIGMOID_X0=3.0`. Sigmoid output is 0.5 at x=3.0, ~0.01 at x=-1.5, ~0.99 at x=7.5.

- **Expected if calibration correct:** raw P95 in 1.5–5.0 range so sigmoid output spans 0.18–0.88.
- **If raw P95 < 1.0:** calibration mismatch. Sigmoid floor is dominating — every observation produces output near zero.

### 3. Concept probe

If implementation and calibration both pass, the analog itself is wrong: zone-flux variance doesn't carry the discriminating information for this data substrate. Candidates ranked by first-principles fit:

- **KL divergence between action-type distributions across consecutive windows.** Information-theoretic free-energy analog. Workers have stable distributions; attackers diverge. Discriminates by construction.
- **Shannon entropy of zone-crossings per window.** Temperature analog. Focused attacks (low entropy) vs scattered benign (higher entropy).
- **Detailed-balance violation.** Equilibrium analog. Workers cycle through zones (A→B→A); attackers chain irreversibly (A→B→C→D→E).

### Day 1 output

- Failure layer identified: A / B / C
- Raw sigma_coarse distribution histogram
- Recommended Day 2 path
- **Checkpoint:** present findings, get user signoff on Day 2 path before any code change.
- **Stop-and-rescope trigger:** if Day 1 surfaces a deeper architectural issue (e.g., world model insufficient to support any physics signal), stop. Do not let the sprint mutate.

---

## Day 2 — Single-Shot Fix

Branch on Day 1 verdict. **One iteration only.** No tweak-and-retry loop — first attempt is the data point.

### Branch A: Bug fix
Fix the implementation. Re-run baseline harness (`murmur robustness-baseline` from PR #37) on existing seeds. Record fire rates and discrimination ratio.

### Branch B: Calibration retune
Recompute `SIGMA_SIGMOID_X0` and `SIGMA_SIGMOID_K` from the raw distribution observed in Day 1's histogram. Document the rationale (e.g., set X0 to median of attack distribution, K to give 0.99 saturation at attack P95). Re-run baseline harness. Record.

### Branch C: Replace with physics_v2
Implement *one* replacement signal. Default first choice: KL divergence on action-type distributions across consecutive windows. User-confirmed alternates from Day 1 review: zone-crossing entropy or detailed-balance violation.

Implement as `physics_v2` signal in `src/score/physics.py` (or new module). Add to fusion at sigma_coarse's current weight (0.04) for the test run. Re-run baseline harness. Record.

### Predict-then-observe (mandatory)

Before each Day 2 run, commit predictions:
- Predicted attack fire rate
- Predicted benign fire rate
- Predicted discrimination ratio

Document divergence after observation. If predictions hit, that's mechanistic confirmation. If predictions miss dramatically (e.g., 80% fire on benign), the fix is producing a signal that doesn't carry the intended semantics.

---

## Day 3 — Verdict and Writeup

Compare Day 2 result to falsifier:

| Discrimination ratio | Action |
|---|---|
| ≥2.0x | Promote to standard weight in `src/score/fusion.py`. Update `FUSION_WEIGHTS`. |
| 1.5–2.0x | Keep at low weight (≤0.04). |
| <1.5x | Set weight=0. Update `CLAUDE.md` framing line: "physics-informed (aspirational; ...)." |

R&D report at `docs/rd_reports/2026-05-XX_sprint2_5_physics_review.md`:
- Predictions (frozen pre-Day 1)
- Day 1 diagnostic findings
- Day 2 fix attempt + observation + divergence
- Verdict and decision per falsifier table
- LEARNINGS.md entry summarizing the sprint

---

## Tests

- Day 1 implementation probe: minimal synthetic positive case as a permanent regression test in `tests/test_physics_signals.py`.
- Day 2 if Branch C: tests for `physics_v2` signal — KL divergence on hand-computed distributions, edge cases (single-window, identical distributions, completely disjoint distributions).
- Re-run full test suite (currently 575 tests post-PR #37). No regressions allowed.

## Gate

- [ ] Failure layer identified on Day 1 (A/B/C/D)
- [ ] User checkpoint completed before Day 2
- [ ] Single Day 2 fix attempt with predict-then-observe
- [ ] Verdict landed per falsifier table — keep / low-weight / retire — no "almost" rationalizations
- [ ] Fusion weights and CLAUDE.md framing updated to match verdict
- [ ] R&D report and LEARNINGS entry committed

## Out of Scope

- novelty / bridge_new audit (1.2x discrimination each — same protocol, deferred to Sprint 2.6)
- Phase B B1 (TGN/TPP) — blocked until per-window signals settled
- Real GCP sandbox baseline — separate axis; needs clean physics verdict first
- New synthetic generators or validation distributions
- Changes to `src/score/closure.py`, `src/score/invariants.py`, `src/provenance/*` — not in this review
- Multi-signal stacking — one fix per failure layer

## Anti-Confirmation Guards

- Falsifier locked at 1.5x **before Day 1**
- Test on existing PR #37 distributions only
- One fix attempt per failure layer
- Predictions committed before each run
- Day 1 → user checkpoint → Day 2 (no autonomous drift past the checkpoint)
- "Almost" rationalizations rejected — 1.49x is a retirement, not a "near miss to keep"

## Findings Log

_Sprint 2.5 findings updated as work progresses:_

## Files Created/Modified

| File | Purpose |
|---|---|
| `docs/sprints/sprint_02_5_physics_review.md` | This spec |
| `docs/rd_reports/2026-05-XX_sprint2_5_physics_review.md` | Predictions + Day 1 diagnostics + Day 2 fix + verdict |
| `src/score/physics.py` | Bug fix / recalibration / physics_v2 (one of three) |
| `src/score/fusion.py` | FUSION_WEIGHTS update per verdict |
| `tests/test_physics_signals.py` | Implementation probe as regression test |
| `CLAUDE.md` | Framing line update per verdict |
| `LEARNINGS.md` | Sprint 2.5 entry |
| `CURRENT_STATE.md` | Resume point update |
