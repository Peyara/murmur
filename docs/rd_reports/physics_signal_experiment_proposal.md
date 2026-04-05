# Experiment Proposal: Validating Physics Signals Under Volumetric/Temporal Anomaly

> Post-MVP experiment. Can be run as a standalone R&D session.

## Motive

Phase 3 attack injection (Session I) revealed that Murmur's physics signals (sigma_coarse, delta_f) are **confirming** what invariants and novelty already detect, not **discovering** things they miss. In 21,837 events across 994 windows, there was no scenario where:
- sigma_coarse spiked AND
- zero invariants fired AND
- novelty was low

The physics signals add ~10% of score weight but ~0% of independent detection capability. They're redundant with novelty for the attack types we tested.

## The Gap

The attacks tested (Session I) were all **structural anomalies**: new actors, new zone edges, new target access. These trigger novelty and invariants by definition.

What we DID NOT test: **volumetric/temporal anomalies** — an established actor performing known actions in known zones, but with anomalous timing or intensity. This is the scenario where physics should uniquely contribute:

- Same actor → no novelty (known edges)
- Same actions → no invariants (no rule violation)
- Same zones → no bridge_new
- Different volume or cadence → sigma_coarse spikes (zone flux magnitude changes)

## Hypothesis

**H1:** A volumetric anomaly (established actor performing 10x normal activity in one window) will spike sigma_coarse and delta_f without triggering invariants or novelty.

**H2:** A cadence anomaly (scheduled actor operating off-schedule) will spike delta_f via EMA deviation without triggering invariants.

**H3:** If H1 and H2 hold, physics signals provide **unique detection capability** for insider threats and compromised automation that the invariant/novelty system cannot catch.

## Experimental Design

### Scenario V1: Volumetric Spike (normal-worker-sa)

normal-worker-sa normally generates ~12 events per window (burst ~1.3/min). In one window, generate **120 events** — 10x the normal volume — performing the exact same actions (read secret, read GCS, encrypt KMS, write GCS).

**Method:** Script that calls the normal-worker Cloud Run endpoint 10 times in rapid succession via Cloud Scheduler override or direct HTTP trigger.

**Expected signals:**
- sigma_coarse: HIGH (10x zone flux in SECRET→DATA→COMPUTE)
- delta_f: HIGH (massive EMA deviation)
- novelty_score: 0 (same edges, all known)
- bridge_new: 0 (same zone pairs)
- inv_score: 0 (same actor, same targets, within 30-day history)
- Expected tier: WATCH or higher from sigma/delta_f alone

**If this fails (sigma doesn't spike):** The zone flux matrix normalizes by edge count, so 10x the same transitions may produce the same proportional flux. In that case, the Schnakenberg entropy formula needs modification — it should be sensitive to volume, not just proportional flow.

### Scenario V2: Cadence Anomaly (maintenance-sa)

maintenance-sa operates hourly. Trigger it at an unexpected time (e.g., 3:37 AM instead of the :00 mark) and verify that the unexpected window shows a sigma/delta_f deviation.

**Method:** Manually trigger the maintenance Cloud Run endpoint outside the scheduler's normal cadence.

**Expected signals:**
- sigma_coarse: MODERATE (same zones but in an unexpected window)
- delta_f: MODERATE (sigma in a window that normally has 0 sigma from this actor)
- All other signals: 0 or minimal
- Expected tier: NORMAL or WATCH (subtle signal)

**If this fails:** delta_f compares sigma to the EMA of ALL historical sigma values, not per-actor sigma. A single actor's off-schedule activity may not meaningfully change the window-level sigma if other actors are also active.

### Scenario V3: Slow Volume Ramp (novel pattern)

An actor gradually increases activity over 4-6 hours: 1x normal → 2x → 4x → 8x. Each window is individually within noise range, but the trend is anomalous.

**Method:** Script that increases Cloud Run trigger frequency every hour.

**Expected signals:**
- sigma_coarse: gradually increasing
- delta_f: increasingly positive (each sigma exceeds its EMA more)
- No invariants fire (same actions, same zones)
- Expected: physics signals detect the ramp that per-window invariants can't

**If this fails:** EMA with alpha=0.1 may adapt too quickly, absorbing the ramp into the baseline before delta_f registers it significantly.

## What to Validate

1. **Does sigma_coarse respond to volume changes (not just new zone pairs)?**
   If yes: physics uniquely detects volumetric anomalies.
   If no: the Schnakenberg formula needs a volume-sensitivity term.

2. **Does delta_f detect cadence anomalies?**
   If yes: physics detects off-schedule activity that invariants can't.
   If no: per-actor EMA (not per-window) is needed — a design change.

3. **Is the EMA alpha appropriate?**
   alpha=0.1 converges in ~30 windows (7.5h). For slow ramps, this may be too fast.
   Test with alpha=0.05 and alpha=0.01 as alternatives.

4. **Can physics signals alone produce WATCH+ tier?**
   With current weights (sigma 0.05 + delta_f 0.10 = 0.15 total), the max possible contribution from physics is 0.15. WATCH threshold is 0.30 (= watch_threshold/10 = 3.0/10). So physics alone CANNOT produce WATCH under current weights — it needs at least some invariant or novelty contribution.
   
   **This is a design constraint:** if physics is intended to independently detect volumetric anomalies, its weight must be higher (≥0.30), OR the WATCH threshold must be lower, OR physics needs to trigger a separate alerting path.

## Prerequisites

- GCP sandbox active with normal-worker + maintenance generating baseline
- 10+ days of baseline data in murmur.duckdb (currently have 12 days)
- Ability to manually trigger Cloud Run endpoints (may need Cloud Run invoker IAM)
- No org policy blocking the triggers

## Success Criteria

| Criterion | What it proves |
|---|---|
| V1 spikes sigma ≥ 5x baseline with 0 invariants | Physics detects volumetric anomaly independently |
| V2 spikes delta_f in off-schedule window | Physics detects cadence anomaly independently |
| V3 shows increasing delta_f across windows | Physics detects slow ramp pattern |
| Any scenario produces WATCH+ from physics alone | Physics is detection-viable, not just confirming |

## Estimated Effort

- Scenario design + scripting: 2-3 hours
- Execution + observation: 4-6 hours (similar to Phase 3)
- Analysis + writeup: 1-2 hours
- Total: 1 full R&D session

## Relationship to burst_per_min Redesign

The burst_per_min B+C redesign (per-actor EMA z-score + per-actor-type sensitivity) is conceptually related to V1/V3. If burst_deviation is implemented, it provides a per-actor volumetric signal that works alongside sigma_coarse. The experiment should be run AFTER burst_deviation is implemented, so we can compare:
- sigma_coarse (global zone flux) vs burst_deviation (per-actor rate) for volumetric detection
- Which is more sensitive? Which has fewer false positives?

---

*Proposed: 2026-04-05 (Session I)*
*Status: PROPOSAL — not yet executed*
