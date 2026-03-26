# Murmur MVP Strategy

## MVP Thesis

Physics-informed signals + provenance subtraction can distinguish adversarial from legitimate agentic activity in GCP audit logs, and this holds across varied attack strategies.

The build is the experiment. Each sprint validates a hypothesis. Failure is information, not disaster.

---

## Architecture

### Stack Layers and Component Mapping

```
+==========================================================================+
|                         PRESENTATION LAYER                                |
|  FastAPI + React + D3.js                                                 |
|  [The Pulse] [Flow Map] [Lineage View] [Alert Queue]                    |
|  Sprint 4 (parallel from Sprint 1)                                       |
+--------------------------------------------------------------------------+
|                         POLICY LAYER                                      |
|  risk_energy() | shadow suggestions | confidence modifier                |
|  Sprint 3                                                                |
+--------------------------------------------------------------------------+
|                         SCORING LAYER                                     |
|  [10 Invariants] [Physics: sigma_coarse, novelty, bridge, delta_F]       |
|  [Closure: closure_ratio, orphaned_privilege]                            |
|  [Fusion: normalize -> weight -> residual_risk]                          |
|  Sprint 1 (core) | Sprint 3 (closure integration)                       |
+--------------------------------------------------------------------------+
|                         PROVENANCE LAYER                                  |
|  [Pattern Registry] [Pattern Match] [Trigger Chain] [Residual Risk]     |
|  Sprint 1 (scaffold) | Sprint 3 (full integration)                      |
+--------------------------------------------------------------------------+
|                         WORLD MODEL LAYER                                 |
|  [15-min Windowing] [Zone Flux 6x6] [Actor Windows] [Edge Tracking]     |
|  Sprint 1                                                                |
+--------------------------------------------------------------------------+
|                         INGESTION LAYER                                   |
|  [Multi-format Parser] [Temporal Correlator] [Dedup] [Inspector]        |
|  Sprint 0 (base) + Sprint 1 (multi-log + correlation)                   |
+--------------------------------------------------------------------------+
|                         INFRASTRUCTURE                                    |
|  GCP Sandbox | DuckDB (embedded) | systemd | e2-micro VM                |
|  Sprint 0                                                                |
+--------------------------------------------------------------------------+
|                         VALIDATION / TESTING                              |
|  [Parameterized Attack Generator] [Benchmark Corpus] [pytest]            |
|  Sprint 2 (attack gen) | All sprints (pytest)                           |
+==========================================================================+
```

### Data Flow

```
GCP Cloud Audit Logs          Cloud Scheduler Logs       Cloud Run Request Logs
(protoPayload)                (jsonPayload)              (httpRequest)
        |                           |                          |
        v                           v                          v
   [GCS Bucket / Cloud Logging API] --fetch--> [Multi-format Parser]
        |
        v
   [Temporal-Identity Correlator] --derive trigger_ref--> [Dedup] --> DuckDB events
        |
        v
   [15-min Windowing] --> actor_windows, edges_window, zone_flux_windows
        |
        v
   [Invariants + Physics Signals] --> fusion_raw
        |
        v
   [Provenance: pattern_match + trigger_chain] --> discount
        |
        v
   [Closure: closure_ratio + orphaned_privilege] --> adjustment
        |
        v
   residual_risk = fusion_raw x (1 - discount x match_score) + trigger_penalty
        |
        v
   [risk_energy()] --> shadow policy suggestions
        |
        v
   [Dashboard: Pulse + Flow Map + Lineage]
```

**Note:** trigger_ref is a derived field, not parsed from raw logs. GCP does not propagate a native per-execution correlation ID from Cloud Scheduler into triggered actions. See `docs/rd_reports/2026-03-25_trigger_ref_discovery.md`.

---

## Causal Validation Chain

Each sprint tests a hypothesis. Each hypothesis depends on the previous one passing.

```
Sprint 0: Can we get data + establish provenance?
    |
    +-- trigger_ref experiment DONE: no native ID exists.
    |   Temporal-identity correlation is the design (MEDIUM confidence).
    |   Multi-log ingestion required (3 log streams, 3 formats).
    v
Sprint 1: Do core signals detect obvious attacks on real data?
    |
    +-- sigma_coarse meaningful? --YES--> Physics thesis lives
    |                              NO---> Debug zones/flux
    v
Sprint 2: Are signals robust across varied attack strategies?
    |
    +-- Detection >80% across grid? --YES--> Signals generalize
    |                                  NO---> Need redesign
    v
Sprint 3: Does provenance + closure reduce false positives?
    |
    +-- Benign below threshold? --YES--> Full thesis validated
    |                            NO---> Provenance model rework
    v
Sprint 4 (parallel from Sprint 1): Dashboard + investor demo
    |
    +-- Pulse + Flow Map + Lineage --> Pitchable artifact
```

---

## Sprint-to-Stack Mapping

| Sprint | Stack Layers Touched | Hypothesis | Duration |
|--------|---------------------|-----------|----------|
| 0: Foundation & Data | Infrastructure, Ingestion | Can we ingest GCP audit logs + establish trigger_ref? | 4-5 days |
| 1: Core Detection | Ingestion (extended), World Model, Scoring, Provenance (scaffold) | Do zone flux + sigma_coarse + invariants produce meaningful signal? | 8-9 days |
| 2: Attack Robustness | Validation, Scoring (analysis) | Are physics signals robust across varied strategies? | 3-4 days |
| 3: Provenance + Closure | Provenance (full), Scoring (closure), Policy | Does provenance subtraction + closure reduce FP? | 5-6 days |
| 4: Dashboard (parallel) | Presentation | Can this be demonstrated to investors? | 5-6 days |

### Timeline

```
Week 1        Week 2        Week 3        Week 4        Week 5
|--Sprint 0--|--Sprint 1 + validation--|--Sprint 2--|--Sprint 3--|
                           |----------Sprint 4 (UI, parallel)-----------|
                                                              |Buffer|
```

---

## MVP Scope

### What's IN

| Component | Stack Layer | Sprint | Why necessary |
|---|---|---|---|
| GCS ingestion + parser | Ingestion | 0 | No data = no experiment |
| trigger_ref extraction | Ingestion | 0 | Foundation of WEAK provenance (experiment result: temporal correlation, not native) |
| Multi-format parser + correlator | Ingestion | 1 | 3 log streams with different formats; trigger_ref derived by temporal-identity correlation |
| Infrastructure event filtering | Ingestion | 1 | Logging SA meta-logs are 31% of entries; must filter or tag to avoid skewing signals |
| DuckDB schema + CLI | Infrastructure | 0 | Storage + interface |
| Zone flux 6x6 matrix | World Model | 1 | Core physics computation substrate |
| sigma_coarse (Schnakenberg) | Scoring | 1 | THE core physics signal |
| 10 invariants | Scoring | 1 | Hard rules that anchor detection |
| novelty_score, bridge_new, delta_F | Scoring | 1 | Novel relationships + progressive risk |
| burst_per_min, breadth_entropy | Scoring | 1 | Per-actor stats for state vector |
| Basic fusion (normalized, weighted) | Scoring | 1 | Compose signals into risk score |
| Parameterized attack generator | Validation | 2 | Validates signal robustness (not circular) |
| Sanctioned pattern registry + matching | Provenance | 1 (scaffold), 3 (full) | Required for provenance subtraction |
| Trigger chain resolution | Provenance | 3 | Traces authorization chains |
| compute_residual_risk | Provenance | 3 | The key subtraction: total - authorized |
| closure_ratio + orphaned_privilege | Scoring | 3 | Detects unclosed privileged actions |
| risk_energy() + shadow policy | Policy | 3 | Actionable output |
| Pulse + Flow Map + Lineage UI | Presentation | 4 | Investor demo |
| 18-scenario benchmark | Validation | 1 (6 core), 3 (full 18) | End-to-end validation |

### What's OUT (Post-MVP Summary)

Deferred components, ordered by value. Full details in `docs/post_mvp_roadmap.md`.

| Component | Why deferred |
|---|---|
| sigma_relative / EMA baseline | Side exploration; core signals carry the load |
| sigma_boundary, target_convergence, eddy_score | Refinement signals, not core thesis |
| automation_probability | Complex; explicitly "never standalone trigger" |
| Transfer Entropy | Noise-dominated at per-window scale |
| Auto-observed pattern discovery | Needs 30 days of production data |
| loop_completeness | Needs more workflow templates |
| RL co-evolution (Level 2 PPO) | Hardening, not validation |
| LLM red team (Level 1) | Param generator covers this need for MVP |
| Provenance mimicry (Level 3) | Needs mature provenance layer |
| Shadow bandit / RL policy | Premature without calibrated thresholds |
| STRONG provenance | Needs Frame (Product 2) |
| Docker terrarium | Not needed for parameterized generator |
| Per-actor behavioral profiling | Needs 30+ days per-actor history |
| Agent-driven ACTION_MAP discovery | See MVP Stretch Goals below |

### MVP Stretch Goals

| Goal | Description | Unlocked by |
|---|---|---|
| **Agent-driven ACTION_MAP discovery** | Use `inspect-interpret` agent to auto-discover service/method combinations from raw logs and propose ACTION_MAP entries. Makes the parser configuration-driven rather than hardcoded. Seed of cloud-agnostic onboarding. | Sprint 0B R&D (trigger_ref experiment). See `docs/rd_reports/2026-03-25_trigger_ref_discovery.md` Section 8.3. |

---

## Onboarding & Time-to-Value

Murmur is a self-learning system. It requires a **hydration period** when deployed to a new cloud environment. This is architecturally intentional — the system observes before it acts. The murmurs of today power the Murmur of tomorrow.

### Why hydration is necessary

Traditional security tools deploy static rules and start alerting on day 1. This produces false positives because the rules don't know what "normal" looks like in your environment. Murmur takes the opposite approach: it observes your environment first, learns the baseline, and then detects deviations from that baseline. The cost is a brief onboarding period. The payoff is zero false positives at steady state.

### What Murmur learns during hydration

- **Identity mappings:** Which service accounts belong to which Cloud Run services (validated via `validate_service_worker_map()`)
- **Temporal cadences:** How often each scheduled job fires, what the normal timing distribution looks like
- **Causal chains:** Which scheduler jobs trigger which services, which services call which APIs
- **Zone flux baseline:** What "normal" cross-zone activity looks like — the steady-state currents of the system
- **Actor patterns:** Who does what, when, and how often — the fingerprint of legitimate activity

### Onboarding timeline

| Phase | Duration | What happens | Output |
|-------|----------|-------------|--------|
| **Deploy** | ~1 hour | Connect log sink, configure initial service mappings | Logs flowing to Murmur |
| **Hydrate** | 3x longest job cadence | Observe actors, cadences, causal chains | Identity mappings confirmed, cadence estimates, correlation operational |
| **Baseline** | 24-48h | Build normal behavior profile across full diurnal cycle | Zone flux baseline, scoring calibration, sanctioned patterns registered |
| **Operational** | Ongoing | Full detection, scoring, and continuous self-validation | Alerts, provenance chains, risk scores, drift detection |

**Typical GCP environment** (5-min scheduled jobs + hourly maintenance): deploy in 1h, hydrate in 15 min, baseline in 24h. **Operational in ~25 hours.**

**Environments with daily batch jobs**: deploy in 1h, hydrate in 3 days, baseline in 1 week.

### Self-maintaining operation

Murmur doesn't stop learning after hydration. It continuously:
- Validates configured identity mappings against observed patterns (flags drift)
- Discovers new services and proposes mappings without human intervention
- Updates baseline patterns as the environment evolves
- Distinguishes organic drift (new legitimate patterns) from adversarial injection

This is not a system you configure once and hope it stays current. It's a system that listens, learns, and adapts — with human oversight at decision points.

---

## Critical Design Decisions (from plan critique)

These were identified as bugs or risks in the original MVP plan and are corrected in this build:

1. **Signal normalization before weighting.** All signals normalized to comparable scales before fusion weights apply. Weights are "initial estimates" to be calibrated after real-data validation.

2. **Coverage as confidence, not score multiplier.** Low coverage reduces alert confidence, does not amplify risk score. Alerts require both high risk AND adequate confidence.

3. **Provenance-conditional incident discount.** Activity with WEAK provenance during incidents gets discounted. Activity with NONE provenance during incidents does NOT -- unattributed activity during chaos is more suspicious.

4. **Closure signal tiers.** Short-window pairs (24h or less) active immediately. Long-window pairs (30 days) report "insufficient data" until enough time has elapsed. No false signal from structural emptiness.

5. **STRONG provenance is a stub.** Interface defined, always returns "unverified." No discount logic built. Activates when Frame ships.

6. **trigger_ref experiment complete (Sprint 0B).** No native per-execution correlation ID exists in GCP audit logs. Temporal-identity correlation across 3 log streams is the production design, not a fallback. MEDIUM confidence — works well at low concurrency, degrades with concurrent executions. See `docs/rd_reports/2026-03-25_trigger_ref_discovery.md`.

7. **Action type coverage matters, not just parse rate.** Sprint 0B showed 100% parse rate but only 34% action type coverage (66% → OTHER). If most events fall to OTHER/DATA zone, the zone flux matrix skews and invariants never fire. ACTION_MAP expansion is a prerequisite for Sprint 1's core hypothesis.

8. **Infrastructure meta-logs must be filtered.** The logging SA writing audit log files to the GCS bucket generates 31% of all entries. These are DATA zone GCS_WRITE events from a single actor that will dominate the flux matrix and dilute per-window metrics. Filter at ingestion or tag as `is_infrastructure`.

---

## Repository Structure

```
murmur/
  src/
    cli.py                         # All CLI commands
    schema.py                      # CanonicalEvent dataclass, enums
    ingest/                        # INGESTION LAYER
      fetch.py                     #   GCS fetch, pagination, checkpointing
      parser.py                    #   GCP audit log -> CanonicalEvent
      multi_parser.py              #   Multi-format dispatcher (Sprint 1)
      correlate.py                 #   Temporal-identity correlation (Sprint 1)
      provenance_ingest.py         #   trigger_ref extraction, provenance_level
      dedup.py                     #   Idempotent deduplication
      inspector.py                 #   Cloud-agnostic log structure/pattern discovery
      inspector_agent.py           #   Agentic interpretation prompt builder
    world/                         # WORLD MODEL LAYER
      window.py                    #   15-min windowing, actor_windows, edges
      graph.py                     #   Zone flux 6x6 matrix, net currents, bridges
      ema.py                       #   EMA baseline (post-MVP, bootstrap modes)
    provenance/                    # PROVENANCE LAYER
      patterns.py                  #   sanctioned_patterns, compute_pattern_match
      trigger_chain.py             #   resolve_trigger_chain
      signature.py                 #   verify_signature (stub)
      residual.py                  #   compute_residual_risk
      discovery.py                 #   Auto-observed pattern discovery (post-MVP)
    score/                         # SCORING LAYER
      invariants.py                #   10 invariants + inv_score
      novelty.py                   #   Novel edge scoring
      physics.py                   #   sigma_coarse + Phase 1 signals
      closure.py                   #   closure_ratio, orphaned_privilege
      fusion.py                    #   Normalization + fusion_raw -> residual_risk
    policy/                        # POLICY LAYER
      state.py                     #   18-dim PolicyState
      energy.py                    #   risk_energy() with provenance-conditional discounts
      bandit.py                    #   Shadow bandit logger
    report/                        # PRESENTATION LAYER
      api.py                       #   FastAPI endpoints
      frontend/                    #   React + D3.js dashboard
  sql/
    schema.sql                     # All DuckDB table definitions
  data/
    fixtures/                      # Sample JSONL for testing
    benchmark/                     # Scenario definitions
  config/
    known_initiators.json          # Cloud Scheduler/Build trigger IDs
    settings.py                    # All configurable parameters
  tests/
    conftest.py                    # DuckDB in-memory fixture, event factory
    test_parser.py
    test_invariants.py
    test_provenance.py
    test_physics.py
    test_closure.py
    test_fusion.py
    test_pipeline.py               # Integration tests
  docs/                            # Strategy, sprint specs, UI concept
  murmur.service                   # systemd unit
  pyproject.toml                   # uv-managed
  README.md
```

---

## MVP Definition of Done

1. **Pipeline operational:** 3 GCP log streams (audit, scheduler, Cloud Run) ingested every 15 min. Parse rate >90% per stream. Action type coverage >80%.
2. **Core signals producing value:** sigma_coarse + invariants + novelty show non-trivial variance on real data (with infrastructure meta-logs filtered).
3. **Robustness validated:** >80% detection rate across parameterized attack grid.
4. **Provenance working:** 1+ registered pattern reduces residual_risk for matched activity.
5. **Closure active:** closure_ratio + orphaned_privilege producing meaningful signal.
6. **Benchmark passing:** 18 scenarios correctly classified.
7. **Dashboard live:** Pulse + Flow Map + Lineage views, investor-demo-ready.
8. **Tests green:** >80% coverage on scoring/provenance. Unit + integration + benchmark in pytest.
9. **Demonstrable:** Inject attack -> Pulse shifts -> Flow Map shows bright thread -> Lineage shows broken chain -> "This is not authorized."
