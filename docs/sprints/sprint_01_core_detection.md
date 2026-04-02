# Sprint 1: Core Detection + Signal Validation

## Hypothesis

Do zone flux + sigma_coarse + invariants produce meaningful signal on real GCP audit logs? Can we distinguish injected attacks from normal scheduled activity using physics-informed signals?

## Prerequisites

Sprint 0 complete. Key Sprint 0B findings that shape this sprint:

- **trigger_ref is derived, not parsed.** No native per-execution correlation ID exists in GCP audit logs. Temporal-identity correlation across 3 log streams is the mechanism. See `docs/rd_reports/2026-03-25_trigger_ref_discovery.md`.
- **Multi-log ingestion required.** Cloud Scheduler execution logs and Cloud Run request logs are separate streams (`jsonPayload`, `httpRequest`) not captured by the current GCS audit log sink.
- **3 log formats, not 1.** The parser needs a multi-format dispatcher: `protoPayload` (audit logs), `jsonPayload` (scheduler), `httpRequest` (Cloud Run).
- **Parse rate 100%, action type coverage 34%.** 9 unmapped GCP methods need ACTION_MAP entries.
- **121 tests green.** Inspector + CLI + provenance pipeline operational.

## Stack Layers

- **Ingestion (extended):** multi-format parsing, temporal-identity correlation, expanded sink
- **World Model:** windowing, zone flux graph, edge tracking
- **Scoring:** invariants, physics (sigma_coarse), novelty, basic fusion
- **Provenance (scaffold):** pattern registry, pattern match, trigger chain, residual risk

## Duration: 8-9 days (2 days ingestion + 4-5 days core + 2 days validation)

---

## Phase 1A: Core Detection Build (6-7 days)

### Day 0: Sandbox Activity Generator (~half day)

Deploy a realistic mini-production workload that gives Murmur diverse, cross-zone activity to validate against. Do this first — let logs accumulate while building the pipeline.

**Workflow 1 — Real Worker (every 5 min, replace hello-world):**
- [ ] Cloud Run `normal-worker`: reads secret, reads GCS input, writes GCS output
- [ ] Produces: CONTROL -> COMPUTE -> SECRET -> DATA chain every 5 minutes
- [ ] Python + Flask, ~50 lines. Deploy with `gcloud run deploy`.

**Workflow 2 — Maintainer (hourly):**
- [ ] Second Cloud Scheduler job -> maintenance script (on e2-micro or second Cloud Run)
- [ ] Rotates secrets (`AddSecretVersion`), creates/deletes SA keys, updates IAM, verifies rotation
- [ ] Produces: CONTROL -> IDENTITY -> SECRET transitions hourly

**Workflow 3 — Cleanup (daily):**
- [ ] Daily cron: list/delete old GCS objects, write summary report
- [ ] Produces: DATA -> DATA transitions, adds daily cadence to temporal patterns

**Resources to create:**
- [ ] `murmur-input-sandbox` + `murmur-output-sandbox` GCS buckets
- [ ] `maintenance-sa` service account
- [ ] Seed input data (small JSON files in input bucket)
- [ ] Second Cloud Scheduler job (hourly trigger for maintenance)
- [ ] Third Cloud Scheduler job or cron (daily trigger for cleanup)

**Workflow 4 — Unstructured human activity (ad-hoc, manual):**
- [ ] Manually run `gcloud` commands at irregular intervals during the sprint:
  - Access secrets via CLI (not scheduled — no trigger_ref)
  - List and inspect resources (`gcloud compute instances list`, `gcloud iam service-accounts list`)
  - SSH to the VM (`gcloud compute ssh`)
  - Make one-off IAM changes (grant/revoke a test permission)
- [ ] These produce events that don't follow patterns, don't have trigger_ref, but ARE legitimate
- [ ] Purpose: test that the system handles unstructured sanctioned activity without false-alerting

**Observation-first validation (critical):**
- [ ] After 24h of activity, run the inspector BEFORE writing detection code
- [ ] Produce an inspector report: what zones are active, what temporal patterns exist, what actors appear, what our invariants would flag, and — critically — what they would MISS
- [ ] Do NOT pre-label expected outcomes. Let the data speak first.
- [ ] Keep infrastructure meta-logs (logging SA) in the dataset — they're real noise the system must handle

**Expected output after 24h:** Cross-zone activity across 5-6 zone pairs. Multiple temporal cadences. 3+ SAs + human activity. A landscape rich enough to evaluate our model against — including signals we didn't anticipate.

### Ingestion Foundation (~2 days)

These deliverables unblock the provenance layer. Build before world model.

**Multi-log ingestion:**
- [ ] Expand GCS sink filter to include `cloudscheduler.googleapis.com/executions` and `run.googleapis.com/requests`, OR add a Cloud Logging API fetcher module alongside GCSFetcher
- [ ] `src/ingest/multi_parser.py`: format dispatcher that detects log type and routes to per-format parsers:
  - `protoPayload` → existing `parser.py` (audit logs)
  - `jsonPayload` with `@type` containing `scheduler.logging` → new scheduler parser (extracts jobName, scheduledTime, url, attempt type)
  - `httpRequest` with `run.googleapis.com` logName → new Cloud Run request parser (extracts userAgent, trace, requestUrl, status)
  - All three produce CanonicalEvent (may need new ActionType values for scheduler/CloudRun events)
- [ ] `src/ingest/correlate.py`: temporal-identity correlation module
  - Build scheduler execution index from AttemptStarted entries
  - Match Cloud Run requests to scheduler executions (url match + timestamp within 15s + userAgent == "Google-Cloud-Scheduler")
  - Match audit log entries to Cloud Run requests (principalEmail matches worker SA + timestamp within 30s)
  - Derive trigger_ref as `sched:{job_id}:{scheduledTime_epoch}`
  - Handle edge cases: no match (NONE provenance), ambiguous match (multiple candidates), retries (HTTP 500 → retry pattern)
- [ ] Expand ACTION_MAP with 9 unmapped methods found in Sprint 0B:
  - `storage.objects.list` → GCS_READ / DATA
  - `iam.serviceAccounts.actAs` → IAM_IMPERSONATE / IDENTITY
  - `secretmanager/CreateSecret` → SECRET_ADMIN / SECRET (new type or map to SECRET_ACCESS)
  - `secretmanager/AddSecretVersion` → SECRET_ADMIN / SECRET
  - `run.googleapis.com/CreateService` → COMPUTE_CREATE / COMPUTE (new type or OTHER)
  - `run.googleapis.com/SetIamPolicy` → IAM_SET_POLICY / CONTROL
  - `cloudscheduler/CreateJob` → SCHEDULER_ADMIN / CONTROL (new type or OTHER)
  - `compute.googleapis.com/instances.insert` → COMPUTE_CREATE / COMPUTE
- [ ] Update `data/fixtures/` with multi-log test data: scheduler + Cloud Run + audit log triplets that exercise the correlation pipeline
- [ ] Update `config/known_initiators.json` with real scheduler SA (load from env var via settings.py)

**Ingestion tests:**
- [ ] Multi-format dispatcher: routes each format correctly, handles unknown formats gracefully
- [ ] Scheduler parser: extracts fields, handles AttemptStarted vs AttemptFinished
- [ ] Cloud Run parser: extracts fields, handles missing optional fields
- [ ] Correlation: matched triplet, no-match, ambiguous (concurrent), retry pattern
- [ ] Expanded ACTION_MAP: tests for all 9 new method mappings
- [ ] Update existing provenance tests that assumed parsed trigger_ref

### World Model Layer

- [ ] `src/world/window.py`: 15-min windowing, actor_windows table, edges_window table
- [ ] `src/world/graph.py`: Zone flux 6x6 matrix computation per window, net currents, bridge detection

### Scoring Layer (Phase 1 signals)

- [ ] `src/score/invariants.py`: All 10 invariants + inv_score computation
  - INV_001: IAM policy change outside deploy window (sev 5)
  - INV_002: Service account key created (sev 5)
  - INV_003: Key created by novel actor (sev 5)
  - INV_004: Impersonation token generated (sev 4)
  - INV_005: Impersonation rate spike (sev 5)
  - INV_006: Secret accessed by new actor (sev 5)
  - INV_007: Secret access within 15 min of policy change (sev 5)
  - INV_008: KMS decrypt by new actor (sev 4)
  - INV_009: Compute metadata change (sev 5)
  - INV_010: New cross-zone edge to SECRET or EXFIL_RISK (sev 5)
- [ ] `src/score/physics.py`: sigma_coarse (Schnakenberg entropy production on 6x6 zone flux)
- [ ] `src/score/novelty.py`: novelty_score (weighted new actor-target edges), bridge_new (new cross-zone edges)
- [ ] delta_F (danger potential change), burst_per_min, breadth_entropy
- [ ] `src/score/fusion.py`: Basic fusion using Phase 1 signals only, with signal normalization

### Provenance Layer (scaffold)

- [ ] `src/provenance/patterns.py`: sanctioned_patterns table, compute_pattern_match (4 components: actor, zone sequence, time window, rate)
- [ ] `src/provenance/trigger_chain.py`: resolve_trigger_chain with cycle detection and max-depth
  - Now depends on `correlate.py` output — trigger_ref is derived, not parsed
  - Must handle correlation confidence: MEDIUM confidence trigger_ref gets a lower weight in chain resolution than a hypothetical STRONG (cryptographic) trigger_ref
- [ ] `src/provenance/signature.py`: verify_signature stub (always returns unverified)
- [ ] `src/provenance/residual.py`: compute_residual_risk with NONE/WEAK discount
- [ ] CLI: `register-pattern`, `list-patterns`, `deactivate-pattern`, `show-trigger-chain`
- [ ] 1+ real sanctioned pattern registered from sandbox `normal-worker`
  - Pattern must account for the 3-log-type event chain: scheduler AttemptStarted → Cloud Run request → downstream audit log events

### Benchmark (initial)

- [ ] 6 core scenarios defined in `data/benchmark/`:
  - S01: Key creation + secret access (5 min apart)
  - S04: Slow ratchet over 45 min (policy -> key -> secret -> data -> exfil)
  - S07: CONTROL -> IDENTITY -> SECRET chain across 3 actors
  - B01: Full deploy (Cloud Build -> IAM -> service -> confirmed)
  - B02: Secrets rotation (scheduler -> create key -> update -> revoke) — needs multi-log context (scheduler + audit logs)
  - S13: Activity matching pattern but trigger_ref NULL, NONE provenance — needs multi-log context (audit logs present but no scheduler/Cloud Run match)
- [ ] `benchmark --corpus` CLI command
- [ ] `score --window-minutes 15` CLI command

### Tests

- [ ] One test per invariant (10 tests) with hand-crafted event sequences
- [ ] Parser edge cases: missing fields, unknown action types, malformed JSON
- [ ] Multi-format parser: dispatch, unknown formats, mixed-format directories
- [ ] Correlation: matched, unmatched, ambiguous, concurrent, retry
- [ ] Trigger chain: resolved, unresolved, cycle detection, max-depth
- [ ] Pattern match: exact, partial, no match, inactive pattern
- [ ] Fusion: known-input/known-output with hand-calculated values
- [ ] Residual risk: NONE and WEAK provenance with various match scores

### Gate

`pytest` green. 6-scenario benchmark: S01/S04/S07 produce residual_risk above threshold, B01/B02 below threshold, S13 medium.

---

## Phase 1B: Signal Validation Gate (2 days)

**This is the most important gate in the project. Do not proceed without answering these questions.**

### Activities

1. Deploy scoring pipeline to GCP VM via systemd. Run continuously 24-48h on real sandbox logs (all 3 log types).
2. Measure and document:
   - [ ] Parse rate per log type: audit logs, scheduler executions, Cloud Run requests (target >90% each)
   - [ ] Correlation accuracy: what % of scheduler executions correctly link to Cloud Run + downstream audit logs?
   - [ ] Zone flux matrix shape on real data: how sparse? Which zone pairs have non-zero flux?
   - [ ] sigma_coarse distribution: what values during active windows? During quiet windows? Is variance meaningful?
   - [ ] Invariant false positives: do any invariants fire on normal Cloud Scheduler activity? (Must be zero)
   - [ ] pattern_match_score for registered normal-worker pattern: is it >0.7?
   - [ ] Distribution of fusion_raw values over 24h: mean, std, min, max, percentiles
   - [ ] Distribution of residual_risk values: same
3. Generate diverse sandbox activity if the zone flux matrix is too sparse:
   - Manual IAM operations
   - Secret access via gcloud CLI
   - Service account creation
   - At minimum: produce events in 4+ of 6 zones
4. Inject scripted attack (S01: key creation + secret access via manual API calls)
5. Verify attack produces elevated residual_risk

### Validation Criteria (ALL must be met to proceed)

**Pipeline health:**
- [ ] Parse rate >90% on each log type (audit, scheduler, Cloud Run)
- [ ] Action type coverage >80% (events mapped to specific types, not OTHER)
- [ ] Correlation accuracy >80% (scheduler executions linked to Cloud Run invocations)

**Signal validation:**
- [ ] sigma_coarse shows measurable variance between active and quiet windows
- [ ] Registered sanctioned pattern produces pattern_match_score >0.7 for normal-worker
- [ ] Injected attack produces residual_risk >= 2x normal window average
- [ ] Zero invariant false positives on baseline scheduled activity

**Bias check (observation-first):**
- [ ] Inspector report produced on 48h of real activity BEFORE evaluating results
- [ ] Catalog ALL invariant firings — explain each one (expected or unexpected)
- [ ] Name at least 2 patterns in the real data that no invariant checks — blind spots documented
- [ ] Name at least 1 type of legitimate activity that the model handles poorly (false positive or confusing score)
- [ ] Human ad-hoc activity (no trigger_ref, no pattern) does not produce false alerts

### If Validation Fails

Debug and fix. Common issues:
- Zone mapping wrong: events landing in unexpected zones
- Flux matrix all zeros: not enough cross-zone events (generate more diverse activity)
- sigma_coarse trivially zero: Schnakenberg formula getting zero flux (check matrix computation)
- Pattern match too low: pattern definition doesn't match real behavior (adjust pattern)
- Correlation failures: scheduler/Cloud Run logs not arriving in bucket (check sink filter), temporal window too narrow, SA mismatch

**Do NOT proceed to Sprint 2 until this gate passes.**

### Findings Log

**Sprint 0B carryforward (context for Sprint 1):**
- trigger_ref does not exist in real GCP audit logs. Temporal-identity correlation is the mechanism (MEDIUM confidence).
- GCP has 3 log formats. Multi-format parser dispatcher needed.
- Parse rate 100% on audit logs, but 66% of entries map to OTHER (9 unmapped methods).
- Scheduler logs arrive ~10s after Cloud Run processes the request. Temporal window must account for this.
- `root_trigger_id` exists as a native label on Compute Engine operations — proof GCP CAN propagate trigger IDs, just not for Scheduler.
- Full evidence: `docs/rd_reports/2026-03-25_trigger_ref_discovery.md`

**Session C findings (2026-03-27): 24h real data inspection**

Pipeline health (pre-validation — scoring/invariants not yet built):
- [x] Parse rate >90%: audit 100%, scheduler 100%, Cloud Run 100%
- [x] Correlation accuracy >80%: 99.7% (1,509/1,513 worker events correlated)
- [ ] Action type coverage >80%: 91.6% (1,946/2,125 events mapped to specific types). 179 OTHER events from unmapped methods.

Bias check (observation-first):
- [x] Inspector report on real data BEFORE pipeline evaluation: `docs/rd_reports/2026-03-27_session_c_24h_inspection.md`
- [x] 2+ blind spots documented: (1) EXFIL_RISK zone empty, (2) system_event not parsed, (3) delegation chain not modeled, (4) GCP internal SA IAM changes, (5) unknown actor events, (6) KMS/BQ untested
- [x] 1+ legitimate activity type handled poorly: GCP internal `service-agent-manager` IAM_SET_POLICY events indistinguishable from attacker IAM modifications without actor allow-listing

Key findings:
- 7 actors (not 6): `service-agent-manager@system.gserviceaccount.com` discovered
- Delegation chain is a first-class anomaly signal (absence = stolen credential)
- `service_worker_map` silently empties without env vars — production risk
- Zone flux matrix 57% sparse. Worker: SECRET<->DATA only. Human: all 5 zones.
- 35 entries from stderr/varlog/system_event correctly rejected by parsers

Full report: `docs/rd_reports/2026-03-27_session_c_24h_inspection.md`

**Session C fixes (completed):**
- [x] Fix silent correlation failure: startup validation when `service_worker_map` is empty (warning in `fetch_and_ingest_multi`)
- [x] Add `delegation_chain` to CanonicalEvent + parser extraction (JSON array of delegation SA emails, stored in events table). Validated: 100% of worker events have `serverless-robot-prod` delegation chain.

**Session F findings (2026-04-01): R&D review + provenance validation**

Data refresh: 11,286 events (March 24 → April 1), 630 windows, 916 scored pairs.

Provenance validation:
- [x] normal-worker-sa: 17% average discount (pattern registered, WEAK provenance via Scheduler→CloudRun→audit correlation)
- [x] maintenance-sa: 20.7% average discount after adding `"maintainer"` to `service_worker_map` — was 0% because correlation chain was broken
- [x] WATCH alerts: 119 → 10 after both fixes. 109 false WATCH alerts from maintenance-sa eliminated.
- [x] Score separation: NORMAL avg=0.058, WATCH avg=0.31, MEDIUM avg=0.65. Clear tiers.
- [x] All 7 MEDIUM alerts from first 4 days (hydration period). Post-hydration: stable, no new alerts. Validates hydration model.

Design decision — auto-discovery (product roadmap, NOT Sprint 1):
- `service_worker_map` is hardcoded per-environment. Product path: hydration auto-discovers mappings from observed (service → SA) patterns. `validate_service_worker_map()` already has the observation logic; needs write-back.
- Sanctioned patterns should be auto-proposed from observed recurring cadences during hydration. Human approves. Pattern lifecycle: discovered → proposed → approved → active.

**Sandbox diversification (Session F, 2026-04-01):**
- [x] EXFIL_RISK bucket: `gs://public-export-sandbox` created. Matches `exfil_risk_patterns`. Zero baseline — attack writes here.
- [x] INV_011: delegation chain anomaly. SA acting without expected delegation chain → severity 5. 5 tests.
- [x] KMS in normal-worker: encrypt output digest via Cloud KMS `worker-encrypt-key`. Exercises INV_008.
- [x] Compute metadata in maintainer: VM label update (`last-maintenance`). Exercises INV_009.
- [ ] Deploy updated normal-worker rev 4 + maintainer rev 4
- [ ] Verify new audit events flowing (KMS encrypt, compute setLabels)
- [ ] Register updated sanctioned patterns after ~3h of new data

**Deferred to Sprint 1B (Tier 3 — need more baseline data or architectural change):**
- [ ] Cross-actor pattern detection: actor A grants access to actor B who escalates. Requires cross-actor window analysis (architectural change to scoring). Currently invisible to per-actor invariants.
- [ ] Data volume anomaly: detect abnormal GCS read/write volume per actor per window. New invariant design + baseline calibration.
- [ ] Temporal anomaly: detect action at unusual time-of-day for actor. Needs longer baseline (weekday/weekend patterns, >2 weeks).
- [ ] Weight rebalancing: try 2-3 fusion weight configs on attack+benign data. Increase physics signal influence. Evaluate separation.

**Parked for Sprint 1B (attack injection phase):**
- [ ] EXFIL_RISK baseline: (a) treat first-ever zone event as maximum novelty in scoring layer, (b) exercise zone during attack injection by writing to `gs://public-export-sandbox`
- [ ] system_event parser: new `system_event_parser.py` for Cloud Run revision deployments. Extracts deployer identity, image hash, scaling config. Map to `COMPUTE_UPDATE` / `COMPUTE` zone. Needed for deploy-based attack detection.
- [ ] GCP internal SA allow-list: add `service-agent-manager@system.gserviceaccount.com` to `known_initiators.json` with infrastructure tag. Prevents invariant false positives on GCP internal IAM maintenance.
- [ ] `ReplaceService` -> ACTION_MAP: add `("run.googleapis.com", "ReplaceService")` -> `(COMPUTE_UPDATE, COMPUTE)`. New `COMPUTE_UPDATE` action type.
- [ ] Investigate 25 medium-confidence correlations (0.50-0.89) — edge cases or systematic?

**Parked for post-MVP:**
- [ ] KMS_DECRYPT / BQ_JOB_SUBMIT validation: no real data to test against. Validate when sandbox uses these services.
- [ ] stderr/varlog parsing: application-level logs with no actor identity. Revisit if instance lifecycle tracking becomes relevant.
- [ ] `murmur doctor` CLI command: validate configuration completeness (env vars, service_worker_map, known_initiators, GCS connectivity).

---

## Files Created/Modified

| File | Purpose |
|---|---|
| `src/ingest/multi_parser.py` | Multi-format log dispatcher |
| `src/ingest/correlate.py` | Temporal-identity correlation for trigger_ref |
| `src/world/window.py` | 15-min windowing |
| `src/world/graph.py` | Zone flux matrix |
| `src/score/invariants.py` | 10 invariants |
| `src/score/physics.py` | sigma_coarse |
| `src/score/novelty.py` | novelty_score, bridge_new |
| `src/score/fusion.py` | Basic fusion pipeline |
| `src/provenance/patterns.py` | Pattern registry + matching |
| `src/provenance/trigger_chain.py` | Trigger chain resolution (uses derived trigger_ref) |
| `src/provenance/signature.py` | Signature verification stub |
| `src/provenance/residual.py` | Residual risk computation |
| `data/benchmark/S01.jsonl` through `S13.jsonl` | Benchmark scenarios (multi-log format) |
| `data/benchmark/B01.jsonl`, `B02.jsonl` | Benign scenarios (multi-log format) |
| `data/fixtures/` | Updated with multi-log test data |
| `tests/test_multi_parser.py` | Multi-format parser tests |
| `tests/test_correlate.py` | Correlation tests |
| `tests/test_invariants.py` | Invariant tests |
| `tests/test_physics.py` | Physics signal tests |
| `tests/test_provenance.py` | Provenance tests |
| `tests/test_fusion.py` | Fusion tests |
