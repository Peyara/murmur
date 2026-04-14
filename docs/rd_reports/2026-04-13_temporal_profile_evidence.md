# R&D Report: Temporal Profile Evidence Grounding

**Date:** 2026-04-13
**Context:** Synthetic generator hardening — before designing temporal profiles for attack/benign activity, we ran a research pass to ground parameters in empirical evidence rather than assumptions.

---

## Motivation

The synthetic generator's `TemporalEngine` had only `uniform_random_time()` in active use. Poisson arrivals were defined but dead code. Designing "burst" and "stealth" profiles from intuition would violate the observe-before-hypothesize principle — we'd be creating test cases that confirm our own theory about what attacks look like.

**Question:** What empirical data exists to parameterize realistic temporal profiles for GCP audit log generation?

---

## Findings

### 1. Attack Timing — Hard Numbers

| Metric | Value | Source |
|---|---|---|
| Initial access to handoff | **22 seconds median** (was 8h in 2022) | Mandiant M-Trends 2026 |
| Median dwell time | **14 days** | Mandiant M-Trends 2026 |
| Lateral movement attempt rate | **62.2%** of intrusions | Google Threat Horizons H2 2025 |
| IAM policy propagation delay | **2 min typical, 7+ min possible** | GCP IAM docs |
| SA access token default lifetime | **1 hour** (max 12h) | GCP IAM docs |

**Interpretation:** Two distinct attack tempo archetypes exist:
- **Smash-and-grab:** Actions compressed into 10-60 seconds (anchored by the 22s M-Trends number). Automated tooling or pre-staged exploitation.
- **Patient escalation:** Actions spaced hours to days apart (anchored by 14-day dwell time). Physically constrained by IAM propagation delay — SetIAMPolicy -> use new permission requires minimum 2-minute wait.

### 2. GCP Platform Constraints — Physical Bounds

| Constraint | Value | Source | Generator Impact |
|---|---|---|---|
| IAM propagation | 2-7+ minutes | [GCP docs](https://cloud.google.com/iam/docs/access-change-propagation) | Minimum gap between privilege grant and use |
| SA token lifetime | 1 hour default | [GCP docs](https://docs.cloud.google.com/iam/docs/service-account-creds) | Attack chain window limit |
| Cloud Scheduler min interval | 60 seconds | [GCP docs](https://docs.cloud.google.com/scheduler/docs/creating) | Floor for scheduled job frequency |
| Cloud Run cold start | 0.5-2s (Python) | [GCP docs](https://docs.cloud.google.com/run/docs/tips/general) | Observable gap in scheduled execution |
| KMS rate limit | 60K QPM | [GCP quotas](https://docs.cloud.google.com/kms/quotas) | Ceiling for automated KMS operations |
| Secret Manager rate limit | 90K QPM | [GCP quotas](https://cloud.google.com/secret-manager/quotas) | Ceiling for secret access bursts |
| Audit log delivery | Near real-time (seconds) | GCP Logging docs | Tight coupling between action and observability |

### 3. Benign Temporal Patterns

| Finding | Grounding | Source |
|---|---|---|
| **Poisson is invalid** for cloud traffic | Empirical measurement since Paxson 1995 | [Paxson 1995](https://web.stanford.edu/class/cs244/papers/paxson1995.pdf) |
| Real cloud workloads are **bursty and self-similar** | Academic consensus, BURSE framework | [BURSE](https://www.researchgate.net/publication/270793594) |
| Scheduled jobs are periodic + small jitter | Platform behavior (magnitude undocumented) | GCP Scheduler docs |
| CI/CD pipelines are concentrated bursts then silence | Universal observation | Multiple sources |
| Human admin temporal patterns: **no published cloud data** | Gap in literature | — |

**Key implication:** The existing `poisson_arrivals()` is not appropriate for modeling benign scheduled activity. Benign activity clusters around trigger events with dead time between.

### 4. Competitor Approaches to Temporal Analysis

| Company | Temporal Method | Relevance |
|---|---|---|
| **Alpha Level** (Josh Neil) | Scan statistics on graphs, Markov models for bursty behavior | Graph-shape intuition (star, k-path) maps to Murmur's zone flux |
| **Panther** | Sequence correlation rules with explicit timing constraints + CNN-BiLSTM | Analogous to Murmur's closure pair detection |
| **Command Zero** | LLM-powered "Chain-of-Timeline" | SQL-style temporal formalization |
| **Dropzone AI** | Multi-agent LLM reasoning | Implicit temporal correlation via context |

### 5. RANK Paper (Soliman et al., IEEE TDSC)

The RANK paper (arxiv 2101.02573) encodes temporal-causal logic via MITRE ATT&CK tactic transition weights in graph edge construction:

```
C(v,v') = max[T_KC(t,t')] x max[C_IP(ip,ip')]
```

**Architectural insight:** Graph structure preserves information that linear fusion destroys — specifically, attack stage ordering and progression. This directly relates to Murmur's "discovery directionality" gap: `mine_candidate_pairs()` finds co-occurrence, not causation. RANK solves this with tactic transition matrices; Murmur could define equivalent zone-transition weights.

---

## How Findings Were Applied

Three temporal profiles implemented in `src/synthetic/temporal.py`:

| Profile | Default Params | Evidence Anchor |
|---|---|---|
| `burst_cluster()` | spread_sec=30 | M-Trends 22s median handoff |
| `stealth_spread()` | min_gap_sec=120 | GCP IAM 2-min propagation delay |
| `scheduled_periodic()` | jitter_sec=2 | Cloud Scheduler wall-clock regularity |

Three attack provenance patterns in `src/synthetic/provenance.py`:

| Pattern | Purpose | Grounding |
|---|---|---|
| `no_trigger_ref()` | Manual/attack actions, no scheduler backing | Absence of provenance is itself a signal |
| `forged_trigger_ref()` | Attacker mimicking scheduled provenance | Provenance mimicry attack vector (Phase 3.4 in roadmap) |
| `partial_trigger_ref()` | Weak/broken provenance | Represents token expiry, deleted jobs, truncation |

---

## Open Questions

1. **Cloud Scheduler jitter magnitude** — undocumented. Our jitter_sec=2 is a reasonable guess, not measured. Could be validated during hydration on real GCP data.
2. **Human admin temporal patterns** — no published cloud-specific data. We model ad-hoc actions as Poisson (rare, independent events). This is an assumption worth validating.
3. **Token lifetime as temporal signal** — if attack actions span > 1 hour without refresh, that's detectable. Not yet implemented in the scoring layer.
4. **RANK-style transition weights** — zone-transition weights (e.g., IDENTITY->SECRET is higher-signal than DATA->DATA) could replace the flat closure pair mining. Thread 3 architectural decision.

---

## Sources

- [Mandiant M-Trends 2026](https://www.mandiant.com/m-trends)
- [Google Threat Horizons H2 2025](https://cloud.google.com/resources/content/cloud-threat-horizons-report-h2-2025)
- [GCP IAM Access Change Propagation](https://cloud.google.com/iam/docs/access-change-propagation)
- [GCP SA Credentials](https://docs.cloud.google.com/iam/docs/service-account-creds)
- [Paxson 1995 — Failure of Poisson Modeling](https://web.stanford.edu/class/cs244/papers/paxson1995.pdf)
- [RANK — Soliman et al.](https://arxiv.org/abs/2101.02573)
- [Alpha Level — Scan Statistics](https://www.researchgate.net/publication/277180693)
