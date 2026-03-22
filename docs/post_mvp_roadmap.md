# Murmur Post-MVP Roadmap

## Context

This roadmap begins after the MVP is complete: working detector on real GCP data, validated across attack strategies, provenance subtraction reducing false positives, investor-grade dashboard operational.

Components are ordered by value-to-effort ratio. Each has explicit prerequisites and dependencies on MVP findings.

---

## Phase 1: Signal Refinement (2-3 weeks after MVP)

### 1.1 sigma_relative / EMA Baseline Experiment

**Value:** Measures departure from the system's own normal, not from global equilibrium. Could be the most sensitive meso-scale signal.

**Approach:** Side exploration. Build it, measure whether it adds detection value beyond sigma_coarse + invariants.

**Implementation:**
- EMA baseline with two-mode bootstrap (learning -> production)
- Learning mode: accept windows where provenance_level == WEAK OR actor matches registered pattern
- Production mode: strict gating (provenance WEAK/STRONG + pattern_match > 0.7 + loop_completeness > 0.8)
- sigma_relative = KL divergence between current residual zone flux and EMA baseline
- should_update_ema_baseline() with explicit transition logging

**Prerequisites:** 7+ days of production data. At least 3 sanctioned patterns registered.

**Decision gate:** Does sigma_relative fire on attacks that sigma_coarse misses? If yes, integrate into fusion. If it just duplicates sigma_coarse, defer further.

**Estimated effort:** 2-3 days

---

### 1.2 Phase 2 Physics Signals

**Value:** Refinement signals that catch specific attack patterns the core signals miss.

| Signal | What it detects | Estimated effort |
|---|---|---|
| target_convergence | Multiple actors converging on same sensitive target | 1 day |
| eddy_score | Cyclic zone transitions (reconnaissance without commitment) | 1 day |
| sigma_boundary | Flux from unregistered actors crossing zone boundaries | 1 day |
| automation_probability | Behavioral inference of automated vs human activity | 2 days |

**Prerequisites:** MVP robustness report (Sprint 2) identifies which attack strategies the core signals miss. Build only the signals that address those gaps.

**Decision gate:** Each signal must demonstrably improve detection rate on the attack parameter grid. If it doesn't, don't add it to fusion.

**Estimated effort:** 3-5 days (selective, not all)

---

### 1.3 Transfer Entropy

**Value:** Detects causal coordination between actors — A's activity predicting B's beyond shared causes.

**Why deferred:** Noise-dominated at per-window sample sizes. Requires hourly aggregates with sufficient event volume.

**Prerequisites:** 30+ days of production data. Sufficient event volume for meaningful hourly aggregates.

**Estimated effort:** 3-4 days

---

## Phase 2: Self-Learning Infrastructure (3-5 weeks after MVP)

### 2.1 Auto-Observed Pattern Discovery

**Value:** Reduces operator burden. System learns what's normal without manual registration.

**Implementation:**
- Background job every 24 hours
- Clusters last 30 days of actor windows
- Signals: structural regularity (0.40), causal footprint drift (0.35), peer corroboration (0.25), deployment anchoring (bonus 0.4x)
- AUTO_PROMOTION_TIERS: OBSERVED_HIGH (0.85, 5 runs), OBSERVED_MEDIUM (0.70, 10 runs), OBSERVED_LOW (0.55, 20 runs)
- Auto-promoted patterns earn at most WEAK-equivalent discount
- Operator can confirm, reject, or blocklist via dashboard

**Prerequisites:** 30+ days of production data. Pattern registry has at least 3 operator-registered patterns as ground truth for validation.

**Estimated effort:** 3-4 days

---

### 2.2 Per-Actor Behavioral Profiling

**Value:** Catches agents doing things they've never done before, regardless of whether the action matches a known attack pattern. Model-free, no labeled data needed.

**Implementation:**
- Historical behavioral envelope per actor: zones touched, action types, rate distributions, target vocabulary
- scope_deviation_score = KL divergence between current behavior and historical profile
- Adapts continuously as agents evolve
- Risk multiplier for actors with high automation_probability

**Prerequisites:** 30+ days of per-actor history. automation_probability implemented (Phase 1.2).

**Estimated effort:** 2-3 days

---

### 2.3 Workflow Template Expansion

**Value:** More templates = more useful loop_completeness signal.

**Implementation:**
- Auto-detect recurring event sequences from production data
- Seed from real operations (not Track B)
- Target: 10-15 templates covering common GCP workflows
- Integrate loop_completeness into fusion once templates are validated

**Prerequisites:** 30+ days of production data. Auto-observed pattern discovery operational.

**Estimated effort:** 2-3 days

---

## Phase 3: Adversarial Hardening (5-8 weeks after MVP)

### 3.1 Docker Terrarium Infrastructure

**Value:** Isolated environment for adversarial simulation. Required for all Level 1+ attackers.

**Implementation:**
- Docker Compose on local/Pi
- Cloud Scheduler execution IDs simulated as trigger_ref values
- Normal workload generator (legitimate activity)
- Event sink that feeds into Murmur's ingestion pipeline

**Estimated effort:** 2-3 days

---

### 3.2 Level 1: LLM-Driven Red Team

**Value:** Generates novel attack trajectories not anticipated in the parameterized grid. Each LLM run produces a different strategy.

**Implementation:**
- Agent framework with red-team prompt
- Each run: LLM plans and executes a multi-step attack
- Output: event sequence + LLM's attack narrative
- Diversity: slow mimicry, novel zone paths, adaptive strategies

**Prerequisites:** Docker terrarium operational. MVP detector stable.

**Estimated effort:** 3-4 days (20 LLM runs)

---

### 3.3 Level 2: RL-Trained Attackers

**Value:** Finds minimal-cost evasion paths that humans and LLMs wouldn't think of. The hardest test cases.

**Implementation:**
- PPO agent
- Reward: reach EXFIL_RISK undetected
- Penalty: residual_risk > threshold
- Environment: Murmur's scoring pipeline as the "detector" the RL agent optimizes against
- Each discovered evasion strategy -> reviewed -> converted to detector improvements

**Prerequisites:** Docker terrarium. LLM red team corpus as training seed. Stable residual_risk as reward signal.

**Estimated effort:** 5-7 days

---

### 3.4 Level 3: Provenance Mimicry

**Value:** Tests provenance layer specifically. Attacker given full sanctioned_patterns registry. Goal: match a pattern while achieving attack objective.

**Implementation:**
- LLM attacker with access to pattern definitions
- Produces high pattern_match_score events
- Cannot forge Cloud Scheduler execution IDs (trigger_ref stays NULL)
- Tests: trigger_chain_resolved is necessary even when pattern_match_score is high

**Prerequisites:** Mature provenance layer. Level 1 and 2 complete.

**Estimated effort:** 2-3 days (10 runs)

---

### 3.5 Frozen Benchmark Corpus

**Value:** Standardized evaluation. 65 trajectories that never change, enabling reproducible comparison across detector versions.

**Composition:** 10 Level 0 (scripted) + 20 Level 1 (LLM) + 20 Level 2 (RL) + 10 Level 3 (mimicry) + 5 benign variants

**Prerequisites:** All adversarial levels complete.

**Estimated effort:** 1-2 days (curation + documentation)

---

## Phase 4: Platform Maturation (8-12 weeks after MVP)

### 4.1 Full Dashboard (7 Panels)

**Value:** Production-grade UI for real users, not just investor demo.

**Additional panels beyond MVP:**
- Closure loop visualization (arc diagrams)
- Auto-observed pattern management (confirm/reject/blocklist)
- Historical trend analysis
- Alert correlation view

**Estimated effort:** 3-4 days

---

### 4.2 Shadow Bandit / RL Policy

**Value:** Learn which alert actions are most effective from observed outcomes.

**Prerequisites:** Weeks of alert data with observed outcomes. Calibrated risk thresholds.

**Estimated effort:** 3-4 days

---

### 4.3 STRONG Provenance (requires Frame)

**Value:** Eliminates false positives from legitimate agent swarms by construction. Ground truth provenance.

**This is Murmur Frame (Product 2)** — not an incremental feature. Separate product development track.

---

## Dependency Graph

```
MVP Complete
    |
    +-- Phase 1.1 (sigma_relative) -- needs 7d data
    +-- Phase 1.2 (Phase 2 signals) -- needs robustness report
    |
    +-- [30 days of data] ---+
    |                        |
    |   Phase 2.1 (auto-discovery)
    |        |
    |   Phase 2.2 (per-actor profiling) -- needs 2.1 + automation_probability
    |        |
    |   Phase 2.3 (workflow templates) -- needs 2.1
    |
    +-- Phase 3.1 (terrarium)
         |
         +-- Phase 3.2 (LLM red team)
         |    |
         |    +-- Phase 3.3 (RL attackers) -- needs 3.2 as seed
         |         |
         |         +-- Phase 3.4 (provenance mimicry)
         |              |
         |              +-- Phase 3.5 (frozen corpus)
         |
    +-- Phase 4.1 (full dashboard) -- can start anytime
    +-- Phase 4.2 (shadow bandit) -- needs weeks of alert data
    +-- Phase 4.3 (Frame) -- separate product track
```

---

## Total Post-MVP Effort Estimate

| Phase | Estimated Days | Cumulative |
|-------|---------------|------------|
| 1: Signal Refinement | 8-12 days | 12 days |
| 2: Self-Learning | 7-10 days | 22 days |
| 3: Adversarial Hardening | 13-19 days | 41 days |
| 4: Platform Maturation | 6-8 days | 49 days |

These are independent work tracks that can be prioritized based on MVP findings. The dependency graph shows which can run in parallel.
