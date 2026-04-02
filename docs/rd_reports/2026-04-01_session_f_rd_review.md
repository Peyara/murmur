# Session F: R&D Review — Signal Analysis, Blind Spots, Score Separation

**Date:** 2026-04-01
**Mode:** R&D + local
**Data window:** 2026-03-24 20:46 UTC to 2026-04-01 19:55 UTC (9 days)
**Data source:** GCS sink `murmur-audit-logs-sandbox` → local snapshot `data/real/` + live ingest

---

## 1. Data Landscape (Post-Refresh)

| Metric | Value |
|---|---|
| Total events ingested | 11,286 |
| Blobs processed | 851 |
| Correlated events (WEAK provenance) | 7,644 (67.7%) |
| Windows (15-min) | 630 |
| Actor-window pairs scored | 916 |
| Distinct actors | 8 |
| Days covered | 9 |

### Actor activity

| Actor | Windows | Avg events/window | Max burst/min | Max entropy |
|---|---|---|---|---|
| normal-worker-sa | 577 | 12.5 | 1.76 | 3.057 |
| logging-sa | 191 | 4.4 | 6.00 | 3.322 |
| maintenance-sa | 114 | 4.0 | 4.00 | 1.447 |
| samreen654 (human) | 22 | 116.0 | 863.00 | 8.754 |
| compute-developer | 4 | 36.0 | 33.00 | 4.338 |
| unknown | 4 | 4.5 | 3.00 | 1.975 |
| serverless-robot-prod | 3 | 14.7 | 12.00 | 4.085 |
| service-agent-manager | 1 | 4.0 | 4.00 | 0.000 |

### Zone coverage

| Zone | Events | % |
|---|---|---|
| DATA | 9,108 | 80.7% |
| SECRET | 2,000 | 17.7% |
| IDENTITY | 142 | 1.3% |
| CONTROL | 25 | 0.2% |
| COMPUTE | 11 | 0.1% |
| **EXFIL_RISK** | **0** | **0.0%** |

### Action type coverage

| Action | Events | % |
|---|---|---|
| GCS_READ | 3,651 | 32.4% |
| GCS_WRITE | 2,585 | 22.9% |
| GCS_LIST | 2,179 | 19.3% |
| SECRET_ACCESS | 1,876 | 16.6% |
| OTHER | 693 | 6.1% |
| IAM_IMPERSONATE | 138 | 1.2% |
| SECRET_ADMIN | 124 | 1.1% |
| IAM_SET_POLICY | 17 | 0.2% |
| COMPUTE_CREATE | 11 | 0.1% |
| SCHEDULER_ADMIN | 8 | 0.1% |
| IAM_CREATE_SA | 3 | <0.1% |
| IAM_CREATE_KEY | 1 | <0.1% |

---

## 2. Provenance Validation

### Correlation before fix

maintenance-sa was missing from `service_worker_map`. Only normal-worker-sa was correlated.

| Actor | Provenance level | Correlation | Discount |
|---|---|---|---|
| normal-worker-sa | WEAK | 7,208 events | 17.0% |
| maintenance-sa | **NONE** | **0 events** | **0.0%** |

### Correlation after fix

Added `"maintainer": "maintenance-sa@..."` to `service_worker_map`.

| Actor | Provenance level | Correlation | Discount |
|---|---|---|---|
| normal-worker-sa | WEAK | 7,208 events | 17.0% |
| maintenance-sa | WEAK | 436 events | **20.7%** |

### Alert distribution impact

| Tier | Before fix | After fix | Delta |
|---|---|---|---|
| HIGH | 0 | 0 | — |
| MEDIUM | 7 | 6 | -1 |
| WATCH | 119 | 10 | **-109** |
| NORMAL | 790 | 900 | +110 |

The 109 eliminated WATCH alerts were all maintenance-sa INV_004 (impersonation) windows that dropped to NORMAL after provenance discount.

---

## 3. Signal Contribution Analysis

### Per-signal statistics (raw, pre-normalization)

| Signal | Mean | Std | p50 | p90 | Max | Nonzero% |
|---|---|---|---|---|---|---|
| inv_score | 0.547 | 1.393 | 0.0 | 4.0 | 5.0 | 13.4% |
| novelty_score | 0.084 | 1.063 | 0.0 | 0.0 | 26.0 | 1.4% |
| sigma_coarse | 0.352 | 0.281 | 0.288 | 0.406 | 3.525 | 94.1% |
| bridge_new | 0.081 | 0.666 | 0.0 | 0.0 | 8.0 | 1.7% |
| delta_f | -0.001 | 0.278 | -0.003 | 0.034 | 3.150 | 48.8% |
| burst_per_min | 4.038 | 35.940 | 1.230 | 4.0 | 863.0 | 100.0% |
| breadth_entropy | 2.351 | 0.955 | 2.793 | 2.896 | 8.754 | 94.4% |

### Correlation with fusion and residual risk

| Signal | Corr(fusion_raw) | Corr(residual_risk) |
|---|---|---|
| **inv_score** | **+0.94** | **+0.89** |
| novelty_score | +0.38 | +0.45 |
| bridge_new | +0.40 | +0.48 |
| sigma_coarse | +0.28 | +0.33 |
| delta_f | +0.25 | +0.32 |
| burst_per_min | +0.06 | +0.07 |
| **breadth_entropy** | **-0.37** | **-0.32** |

### NORMAL vs WATCH vs MEDIUM signal means

| Signal | NORMAL | WATCH | MEDIUM | MED/NORM ratio |
|---|---|---|---|---|
| inv_score | 0.484 | 3.500 | 5.000 | **10.3x** |
| novelty_score | 0.011 | 1.700 | 8.333 | **750.7x** |
| bridge_new | 0.038 | 1.000 | 5.000 | **132.3x** |
| sigma_coarse | 0.339 | 0.734 | 1.633 | 4.8x |
| delta_f | -0.016 | 0.460 | 1.459 | inf |
| burst_per_min | 4.022 | 5.315 | 4.346 | 1.1x |
| breadth_entropy | 2.352 | 2.039 | 2.789 | 1.2x |

### Signal decomposition for MEDIUM alerts (% contribution to fusion)

| Window | Actor | inv | nov | sig | brg | df | bst | ent |
|---|---|---|---|---|---|---|---|---|
| 03-26 19:30 | samreen654 | 46.8% | 26.8% | 1.2% | 10.7% | 2.4% | 2.8% | 9.4% |
| 03-28 03:30 | maintenance-sa | 47.8% | 20.5% | 4.8% | 13.6% | 8.6% | 1.2% | 3.5% |
| 03-24 20:45 | samreen654 | 48.2% | 27.6% | 0.3% | 13.8% | 0.0% | 1.2% | 9.0% |
| 03-28 03:30 | samreen654 | 52.2% | 3.0% | 5.3% | 14.9% | 9.4% | 4.8% | 10.4% |
| 03-26 19:45 | samreen654 | 63.5% | 10.9% | 1.4% | 7.3% | 2.4% | 3.2% | 11.4% |
| 03-26 19:30 | service-agent-mgr | 69.6% | 6.0% | 1.8% | 15.9% | 3.6% | 3.2% | 0.0% |

### Key findings

1. **inv_score dominates fusion** at 0.94 correlation and 47-70% of every MEDIUM alert. The system is essentially "fire if invariant fires + boost from novelty/bridges."
2. **novelty_score and bridge_new are the sharpest discriminators** (750x and 132x MEDIUM/NORMAL) but only fire during hydration windows. Post-hydration they're zero.
3. **burst_per_min is dead weight:** 1.1x separation, 0.06 correlation. Bursts don't differentiate threat from admin.
4. **breadth_entropy is anti-correlated** (-0.37): higher entropy = more diverse targets = legitimate admin. Correct for this environment but wrong sign as a "risk signal."
5. **Physics signals (sigma, delta_f) contribute mildly** (4.8x, inf) but at weight 0.10 each, they can't independently push scores to MEDIUM.

---

## 4. False Positive Analysis

### 6 MEDIUM alerts — classified

| Window | Actor | Fired | Classification |
|---|---|---|---|
| 03-26 19:30 | samreen654 | INV_001, INV_004 | Setup noise — IAM + impersonation during project setup |
| 03-28 03:30 | maintenance-sa | INV_002, INV_004, INV_005, INV_010 | True positive / one-time — SA key creation (only one in 9 days) |
| 03-24 20:45 | samreen654 | INV_001, INV_004, INV_005, INV_010 | Setup noise — first window, novelty=26 (everything new) |
| 03-28 03:30 | samreen654 | INV_001, INV_004, INV_005 | Setup noise — concurrent with maintenance spike |
| 03-26 19:45 | samreen654 | INV_001, INV_004, INV_006, INV_007, INV_010 | Setup noise — 5 invariants, most diverse window |
| 03-26 19:30 | service-agent-manager | INV_001 | **False positive** — GCP internal SA, needs allow-list |

### 10 WATCH alerts — classified

| Actor | Count | Classification |
|---|---|---|
| maintenance-sa | 4 | Residual FP — INV_004 on windows without full pattern match |
| normal-worker-sa | 2 | True positive / one-time — INV_006 first secret access |
| samreen654 | 2 | Setup noise |
| serverless-robot-prod | 1 | Borderline FP — no invariant, pure novelty/bridge. GCP internal. |
| compute-developer | 1 | Borderline FP — no invariant, sigma=3.52 spike. GCP default SA. |

### Summary

- **0 false positives on malicious activity** (no attacks to miss — expected)
- **0 false alerts on steady-state benign activity** (post-hydration, system is silent)
- **1 clear FP:** service-agent-manager (GCP internal). Fix: add to known_initiators.
- **4 residual FPs:** maintenance-sa INV_004. Fix: per-invariant suppression for pattern-matched actors (Sprint 2).
- **All 6 MEDIUM alerts are from the first 4 days** (hydration period). Post-hydration: stable.

---

## 5. Invariant Blind Spots

### Never-fired invariants

| Invariant | What it detects | Why it never fired |
|---|---|---|
| INV_003 | Key created by novel actor | Only 1 key creation event, by known SA (maintenance-sa) |
| INV_008 | KMS decrypt by new actor | Zero KMS_DECRYPT events — no KMS usage in sandbox |
| INV_009 | Compute metadata change | Zero COMPUTE_METADATA_CHANGE events |

### Invariant fire rates

| Invariant | Fires | Rate | Actor(s) |
|---|---|---|---|
| INV_004 | 120 | 13.1% | maintenance-sa (114), samreen654 (6) |
| INV_001 | 6 | 0.7% | samreen654 (5), service-agent-manager (1) |
| INV_010 | 4 | 0.4% | samreen654 (3), normal-worker-sa (1) |
| INV_005 | 3 | 0.3% | samreen654 (2), maintenance-sa (1) |
| INV_006 | 3 | 0.3% | samreen654 (1), normal-worker-sa (2) |
| INV_002 | 1 | 0.1% | maintenance-sa |
| INV_007 | 1 | 0.1% | samreen654 |
| INV_003 | 0 | 0% | — |
| INV_008 | 0 | 0% | — |
| INV_009 | 0 | 0% | — |

### Structural blind spots (no invariant covers)

1. **Delegation chain anomaly.** 67% of events have delegation chains. Absence on a normally-chained SA signals credential theft. **→ INV_011 added this session.**
2. **EXFIL_RISK zone.** 0 events. Completely dark — no baseline to calibrate. **→ EXFIL_RISK bucket created this session.**
3. **Cross-actor lateral movement.** Actor A grants access to actor B who escalates. Invisible to per-actor scoring. **→ Deferred to Sprint 1B/2.**
4. **Data volume anomaly.** No invariant checks abnormal GCS read/write volume. **→ Deferred.**
5. **Temporal anomaly.** No time-of-day signal. **→ Deferred (needs >2 weeks baseline).**
6. **OTHER action type opacity.** 693 events (6.1%) mapped to OTHER — invisible to all invariants.

### Delegation chain coverage by actor

| Actor | With chain | Without | % chained |
|---|---|---|---|
| normal-worker-sa | 7,218 | 0 | **100%** |
| maintenance-sa | 346 | 115 | 75% |
| samreen654 (human) | 0 | 2,552 | 0% |
| logging-sa | 0 | 845 | 0% |
| compute-developer | 5 | 139 | 3% |
| serverless-robot-prod | 0 | 44 | 0% |
| unknown | 0 | 18 | 0% |
| service-agent-manager | 0 | 4 | 0% |

INV_011 fires when: SA has >80% historical chain ratio, but current window events lack chains. Threshold: minimum 10 historical events.

---

## 6. Score Separation Analysis

### Fusion score distribution

| Percentile | fusion_raw | residual_risk |
|---|---|---|
| min | 0.0040 | 0.0040 |
| p25 | 0.0583 | 0.0483 |
| p50 | 0.0584 | 0.0484 |
| p75 | 0.0591 | 0.0491 |
| p90 | 0.3131 | 0.2512 |
| p95 | 0.3131 | 0.3131 |
| p99 | 0.3610 | 0.3610 |
| max | 0.7476 | 0.7327 |

### Theoretical attack projections

| Scenario | Description | Projected fusion | Tier |
|---|---|---|---|
| Benign max (current) | samreen654 setup window | 0.748 | MEDIUM |
| S01 Key+Secret | Novel actor, key + secret access | 0.551 | MEDIUM |
| S04 Slow ratchet | 5-zone traversal with policy+key+secret+data+exfil | 0.788 | MEDIUM (near HIGH) |
| S07 Multi-actor | Per-actor chain component | 0.514 | MEDIUM |
| **Stealth** | **No invariant fires, novel edges only** | **0.229** | **NORMAL (invisible)** |
| Max theoretical | All signals maxed | 1.000 | HIGH |
| All maxed except inv | Physics signals only | 0.650 | MEDIUM (ceiling) |
| Only inv maxed | Invariant fire, flat physics | 0.401 | WATCH |

### The invariant dependency problem

Without inv_score, the fusion ceiling is **0.65** (MEDIUM at best, never HIGH). The system is structurally dependent on invariants for HIGH alerts. Stealth attacks that avoid triggering any invariant score **0.23 — invisible.**

### Provenance discount on attacks

| Attacker type | Pattern match | Multiplier | Discount |
|---|---|---|---|
| Unknown actor (no provenance) | N/A | NONE (0.0) | 0% — full price |
| Stolen credential, partial pattern match | 0.5 | WEAK (0.6) | ~9% |
| Stolen credential, strong pattern match | 0.9 | WEAK (0.6) | ~16% |

Attackers without provenance pay full price. Stolen credentials with partial pattern match get modest discount — acceptable for Sprint 1, revisit if attack injection reveals issues.

---

## 7. Sandbox Diversification (Deployed)

### Changes to exercise blind spots

| Addition | Purpose | Exercises | Status |
|---|---|---|---|
| KMS encrypt in normal-worker (rev 4) | Adds KMS audit events every 5 min | INV_008 (KMS by new actor) | Deployed, events confirmed |
| VM label update in maintainer (rev 4) | Adds compute metadata audit events hourly | INV_009 (compute metadata change) | Deployed, pending first trigger |
| EXFIL_RISK bucket (`gs://public-export-sandbox`) | Attack injection target | INV_010 (new edge to EXFIL_RISK) | Created, empty |
| INV_011 (delegation chain anomaly) | Detects SA acting without expected chain | Credential theft detection | Code + 5 tests |
| KMS_ENCRYPT action type | Parses KMS Encrypt audit events | Zone coverage | Parser mapping added |
| setLabels parser mapping | Parses compute label change events | Zone coverage | Parser mapping added |

### Cost impact

| Resource | Monthly cost |
|---|---|
| KMS key storage | $0.06 |
| KMS operations (8,640/month) | Free (10K free tier) |
| Compute API calls (1,440/month) | Free |
| EXFIL_RISK bucket (empty) | $0.00 |
| Cloud Run incremental | Free tier |
| **Total** | **~$0.06/month** |

---

## 8. Conclusions and Next Steps

### What this review validated

1. **Scoring produces meaningful separation.** NORMAL (0.058) → WATCH (0.31) → MEDIUM (0.65) — clear tiers with gaps.
2. **Provenance discount works.** 17-21% for scheduled services. 109 false WATCH alerts eliminated.
3. **Hydration model confirmed.** ~4 days to baseline. Post-hydration, system produces zero false alerts on steady-state activity.
4. **Invariants are the backbone.** They drive scoring precision. Physics signals provide supporting evidence but can't carry detection alone.

### What this review revealed

1. **Invariant dependency is a structural limit.** Stealth attacks (no invariant fire) score 0.23 — invisible.
2. **Two signals are problematic.** burst_per_min is dead weight. breadth_entropy is anti-correlated.
3. **Three invariants are untested.** INV_003, INV_008, INV_009 never fired (now addressed by sandbox diversification).
4. **EXFIL_RISK is a dark zone.** No baseline data. Attack injection will be the first test.
5. **Delegation chain is the strongest blind spot.** Now addressed by INV_011.

### Sprint 1B priorities (informed by this review)

1. **Attack injection:** Both invariant-triggering (S01, S04 into EXFIL_RISK) and stealth (stolen credential without delegation chain).
2. **Weight rebalancing:** Test 2-3 configs against attack+benign data. Evaluate burst_per_min and breadth_entropy.
3. **Benchmark scenarios:** S01/S04/S07/B01/B02/S13 with real scoring validation.
4. **Deferred Tier 3:** Cross-actor patterns, data volume anomaly, temporal anomaly.
