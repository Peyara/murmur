# Session C: 24h Real Data Inspection Report

**Date:** 2026-03-27
**Mode:** R&D + local
**Data window:** 2026-03-24 20:48 UTC to 2026-03-28 02:07 UTC (~5 days)
**Data source:** GCS sink `murmur-audit-logs-sandbox` -> local snapshot `data/real/`

---

## 1. Data Landscape

| Metric | Value |
|---|---|
| Total log entries | 3,415 |
| Files processed | 166 |
| Total size | 4.8 MB |
| Days covered | 5 (03/24 - 03/28) |
| Distinct actors | 7 |
| Distinct log types | 7 |
| Distinct audit methods | 36 |

### Log type distribution

| Log type | Entries | % |
|---|---|---|
| cloudaudit/data_access | 2,043 | 59.8% |
| cloudscheduler/executions | 838 | 24.5% |
| run.googleapis.com/requests | 417 | 12.2% |
| cloudaudit/activity | 73 | 2.1% |
| run.googleapis.com/stderr | 27 | 0.8% |
| cloudaudit/system_event | 9 | 0.3% |
| run.googleapis.com/varlog/system | 8 | 0.2% |

### Events per day

| Day | Events (audit only) | Notes |
|---|---|---|
| 03/24 | 32 | Initial setup (human only) |
| 03/25 | 133 | Pre-worker human exploration |
| 03/26 | 521 | Deploy day + worker start + heavy human activity |
| 03/27 | 1,333 | Steady-state worker + sprinkled human activity |
| 03/28 | 106 | Worker-only (partial day) |

---

## 2. Pipeline Health

### Parse rates

| Format | Parsed | Errors | Rate | Target |
|---|---|---|---|---|
| Audit logs | 2,125 | 0 | 100% | >90% |
| Scheduler logs | 838 | 0 | 100% | >90% |
| Cloud Run requests | 417 | 0 | 100% | >90% |
| Unparseable (stderr/varlog/system_event) | 0 | 35 | N/A | — |

All 3 supported formats achieved 100% parse rate. The 35 "errors" are entries from formats we intentionally don't parse (stderr, varlog, system_event). The parsers correctly reject these.

### Correlation accuracy

| Metric | Value |
|---|---|
| Worker events total | 1,513 |
| Worker events correlated | 1,509 (99.7%) |
| Worker events uncorrelated | 4 (0.3%) |
| Target | >80% |

Confidence distribution of correlated events:

| Confidence bucket | Count | % of correlated |
|---|---|---|
| 0.99 - 1.0 (very high) | 1,440 | 95.4% |
| 0.90 - 0.98 (high) | 44 | 2.9% |
| 0.50 - 0.89 (medium) | 25 | 1.7% |

The 4 uncorrelated worker events (one each of SECRET_ACCESS, GCS_LIST, GCS_READ, GCS_WRITE) are likely from the very first invocation before sufficient scheduler data accumulated for temporal matching.

The 25 "medium" confidence events warrant investigation in Session D — they may be near temporal window boundaries or have ambiguous candidate matches.

### Critical finding: silent failure without env vars

The `service_worker_map` is populated from `GCP_PROJECT_ID` env var. When not set, it defaults to `{}` — and the correlator silently produces 0 correlations with no error or warning. First pipeline run in this session showed `correlated: 0` because `.env` wasn't sourced.

**Production risk:** A deployment that fails to load env vars would appear to work (events still parse and insert) but produce zero provenance — making all worker activity look uncorrelated and potentially anomalous.

---

## 3. Actor Landscape

### 7 distinct actors

| Actor | Events | % | Role | Infrastructure? |
|---|---|---|---|---|
| normal-worker-sa@...iam.gserviceaccount.com | 1,513 | 71.2% | Scheduled worker | No |
| samreen654@gmail.com | 353 | 16.6% | Human operator | No |
| service-...@gcp-sa-logging.iam.gserviceaccount.com | 163 | 7.7% | Log sink writes to GCS | Yes |
| ...compute@developer.gserviceaccount.com | 63 | 3.0% | Default compute SA (deploy-time) | Yes |
| service-...@serverless-robot-prod.iam.gserviceaccount.com | 20 | 0.9% | Cloud Run delegation SA | Yes |
| unknown | 9 | 0.4% | Unattributed events | N/A |
| service-agent-manager@system.gserviceaccount.com | 4 | 0.2% | GCP internal IAM maintenance | Yes |

### Delegation chains

The `serviceAccountDelegationInfo` field is present in 1,515 of 3,415 entries (44%). Two delegation patterns observed:

1. **Runtime:** `serverless-robot-prod` delegates to `normal-worker-sa` — every worker API call (storage, secrets) goes through this chain. Present in all 1,513 worker events.
2. **Deploy-time:** `gcp-sa-cloudbuild` delegates to `1013530516622-compute` — Cloud Build deploy operations.

**Signal value:** If a `normal-worker-sa` event appears WITHOUT `serverless-robot-prod` in the delegation chain, it means someone is using the SA key directly (not through Cloud Run). This absence-of-delegation is a strong anomaly signal for stolen credential detection.

### Human vs automated fingerprint

| Signal | Human (samreen654) | Worker (normal-worker-sa) |
|---|---|---|
| User-agent | `google-cloud-sdk gcloud/562.0.0 command/...` (113 variants) | `gcloud-python/2.19.0 gl-python/3.12.13 grpc/...` (1 pattern) |
| IP address | `2600:4041:5b3b:...` (residential IPv6) | `2600:1900:...` (GCP internal) |
| Temporal pattern | Bursty, irregular, clustered around sessions | Regular 5-min cadence |
| Zone coverage | All 5 zones | SECRET + DATA only |

The `callerSuppliedUserAgent` field alone is sufficient to classify human vs automated with high confidence. The 113-variant cardinality for human use reflects different `gcloud` subcommands; the worker's SDK signature is near-constant.

### Human activity breakdown

| Action type | Count |
|---|---|
| GCS_LIST | 157 |
| OTHER | 96 |
| GCS_READ | 54 |
| IAM_IMPERSONATE | 13 |
| IAM_SET_POLICY | 9 |
| SCHEDULER_ADMIN | 6 |
| SECRET_ADMIN | 6 |
| GCS_WRITE | 6 |
| COMPUTE_CREATE | 3 |
| IAM_CREATE_SA | 2 |
| SECRET_ACCESS | 1 |

Human activity spans all 5 populated zones. The heavy GCS_LIST (157) reflects console/CLI bucket browsing. The IAM and SCHEDULER_ADMIN events are from initial project setup on 03/24-03/26.

---

## 4. Zone Flux Analysis

### Zone event distribution

| Zone | Events | % |
|---|---|---|
| DATA | 1,685 | 79.3% |
| SECRET | 400 | 18.8% |
| CONTROL | 19 | 0.9% |
| IDENTITY | 15 | 0.7% |
| COMPUTE | 6 | 0.3% |
| EXFIL_RISK | 0 | 0.0% |

### Cross-zone transitions (top flows)

| Actor | Transition | Count |
|---|---|---|
| normal-worker-sa | SECRET -> DATA | 393 |
| normal-worker-sa | DATA -> SECRET | 392 |
| samreen654 | DATA -> IDENTITY | 9 |
| samreen654 | IDENTITY -> CONTROL | 8 |
| samreen654 | IDENTITY -> DATA | 6 |
| samreen654 | CONTROL -> DATA | 6 |
| samreen654 | CONTROL -> IDENTITY | 4 |

**Worker flux is a tight oscillation:** SECRET<->DATA, ~393 transitions each way. This is the worker reading a secret, then reading/writing GCS objects. Highly regular, highly predictable.

**Human flux is sparse but multi-zone:** 17 distinct transition types across all 5 zones. This is the pattern we want — human ops touch many zones infrequently, worker ops touch few zones frequently.

### 6x6 matrix sparsity

Of 30 possible zone pairs (excluding self-transitions), only 17 are populated — all from human activity. Worker contributes exactly 2 pairs (SECRET<->DATA). The matrix is ~57% sparse.

**Implication for world model:** The zone flux matrix will be dominated by SECRET<->DATA at baseline. Any new zone pair appearing (e.g., IDENTITY->SECRET, DATA->EXFIL_RISK) will be a novelty signal by definition. This is correct by design — the rarity of unusual transitions IS the detection signal.

---

## 5. Inspector Findings

### Structure discovery

The inspector found 100+ distinct field paths across all 7 log types. Key findings:

- **Timestamp fields:** 15 distinct timestamp fields found. Primary: `timestamp`, `receiveTimestamp`. Scheduler-specific: `jsonPayload.scheduledTime`. Response metadata timestamps available for deploy correlation.
- **Actor candidates:** 10 email-type fields identified. Primary: `principalEmail` (cardinality 6). The inspector also found `serviceAccountDelegationInfo[].firstPartyPrincipal.principalEmail` (cardinality 2) — confirming delegation chains as a discoverable signal.
- **Correlation candidates:** Top-scored by the inspector: `protoPayload.request.parent` (score 1.0), `insertId` (0.99), `resourceName` (0.98).

### Temporal clustering

434 clusters found (30-second window). Patterns:

- **Worker clusters:** 4 events each, <2s span. SECRET_ACCESS -> GCS_LIST -> GCS_READ -> GCS_WRITE. Highly regular.
- **Human clusters:** Variable size (2-55 events), 0.5-34s span. Often burst-reading bucket contents (30 GCS_LIST in 3 seconds) or running setup commands.
- **Logging SA clusters:** 2 events, ~3-9s span. Writing sink files.
- **Deploy clusters:** 4-6 events, 10-35s span. VM creation, Cloud Run service deployment.

### Cross-log correlations

433 cross-log field overlaps found. Most significant:

1. `activity::authorizationInfo[].resource` <-> `scheduler::jsonPayload.jobName` (3 shared values) — **this is exactly the join key our correlator uses**, independently confirmed.
2. `stderr::labels.instanceId` <-> `varlog::labels.instanceId` (4 shared values) — instance lifecycle tracking across log types.
3. `activity::callerSuppliedUserAgent` <-> `data_access::callerSuppliedUserAgent` (3 shared values) — human activity fingerprint consistent across audit log subtypes.

---

## 6. Unmapped Methods (OTHER events)

179 events mapped to OTHER/DATA. Breakdown:

| Method | Count | Source | Assessment |
|---|---|---|---|
| storage.buckets.getStorageLayout | 39 | Human browsing | Benign. Read-only metadata. |
| Docker-HeadBlob | 25 | Cloud Build deploy | Deploy noise. One-time per deployment. |
| Docker-ServeBlob | 16 | Cloud Build deploy | Deploy noise. |
| Docker-FinishUpload | 15 | Cloud Build deploy | Deploy noise. |
| Docker-StartUpload | 15 | Cloud Build deploy | Deploy noise. |
| ListLogEntries | 15 | Human `gcloud logs read` | Benign. Cloud Logging read. |
| Docker-GetManifest | 9 | Cloud Build deploy | Deploy noise. |
| /Services.ReplaceService | 6 | Cloud Run deploy | Deploy event. Valuable signal. |
| ReplaceService | 5 | Cloud Run deploy | Deploy event. Valuable signal. |
| ListTimeSeries | 5 | Monitoring reads | Benign. |
| BatchEnableServices | 4 | API enablement | Setup activity. |
| CreateBuild | 4 | Cloud Build | Deploy event. |
| SubmitBuild | 3 | Cloud Build | Deploy event. |
| Other (10 types) | 18 | Various | Low-frequency setup/maintenance. |

**Docker-* methods (82 total):** All from Cloud Build during deployment. These are container image push operations. They appear as a burst during deploy and never again. Not worth adding to ACTION_MAP — they correctly map to OTHER/DATA and provide no detection value at steady state.

**Deploy-related methods (ReplaceService, CreateBuild, SubmitBuild):** These have potential detection value — an unauthorized deployment would produce these events. Currently mapped to OTHER. Consider adding `ReplaceService` -> `COMPUTE_UPDATE` / `COMPUTE` zone in ACTION_MAP.

---

## 7. Blind Spots

### Blind spot 1: EXFIL_RISK zone is completely empty

Zero events mapped to EXFIL_RISK across 5 days. The `exfil_risk_patterns` in settings check for bucket names containing `public-`, `external-`, `export-`, `backup-`, or `temp-`. None of our sandbox buckets match.

**Risk:** An attacker creating a `public-export-data` bucket would be the first-ever EXFIL_RISK event. The world model has no baseline for this zone — it can't compute flux anomalies or EMA deviations because there's no history.

### Blind spot 2: system_event logs not parsed

9 system_event entries exist (all from Cloud Run revision deployments). These contain:
- `serving.knative.dev/creator` — who deployed the revision
- Revision metadata (image hash, env vars, scaling config)
- Container spec changes

An unauthorized deployment would primarily surface in system_event logs. We currently reject these as unparseable.

### Blind spot 3: No detection of delegation chain anomalies

The delegation chain (`serviceAccountDelegationInfo`) is not extracted or stored in CanonicalEvent. We record the `principalEmail` (the worker SA) but not the delegation SA. If an attacker uses a stolen SA key directly (bypassing Cloud Run), the event looks identical in our model — same actor, same action, same zone. The missing delegation chain is the distinguishing signal.

### Blind spot 4: IAM policy changes from GCP internal SAs

4 events from `service-agent-manager@system.gserviceaccount.com` performing `IAM_SET_POLICY` in the CONTROL zone. These are legitimate GCP-internal policy maintenance. Without a allow-list for GCP internal SAs, these look identical to attacker IAM modifications.

### Blind spot 5: `unknown` actor events

9 events have `actor_id = "unknown"`. These are events where `authenticationInfo.principalEmail` is absent — typically GCP internal operations or certain API calls that don't carry identity. Currently invisible to actor-based analysis.

### Blind spot 6: No KMS_DECRYPT or BQ_JOB_SUBMIT in real data

Two ACTION_MAP entries with zero observations. We can't validate that the parser handles these correctly on real data, and the world model will have no baseline for them.

---

## 8. Assumptions: Held vs Broke

### Held

| Assumption | Evidence |
|---|---|
| Temporal-identity correlation works at scale | 99.7% correlation rate (1,509/1,513 worker events) |
| Worker produces deterministic SECRET<->DATA flux | 393 SECRET->DATA transitions, 392 DATA->SECRET. Tight oscillation. |
| Human activity is distinguishable from automated | User-agent, IP, temporal pattern, zone coverage all differ clearly |
| GCS sink captures all audit event types | data_access, activity, system_event all present |
| Zone flux is sparse at baseline | 57% matrix sparsity. Dominated by 2 zone pairs. |
| Inspector can discover correlation chains zero-knowledge | scheduler::jobName <-> activity::authorizationInfo independently found |

### Broke

| Assumption | Evidence | Impact |
|---|---|---|
| `service_worker_map` always available | Empty when `.env` not sourced. Pipeline produces 0 correlations silently. | **High.** Production risk — silent degradation. |
| 6 distinct actors in sandbox | 7 found: `service-agent-manager@system.gserviceaccount.com` not in our model. | **Low.** Rare (4 events). Add to infrastructure allow-list. |
| All entries parseable by 3 formats | 35 entries from stderr/varlog/system_event rejected. | **Low.** Correct rejection. system_event has future value. |
| Delegation chain is metadata, not signal | Delegation chain is a first-class anomaly signal for stolen credential detection. | **Medium.** Need to extract and model delegation chains. |

---

## 9. What's Next: Tackling Issues Found

### Priority 1: Silent correlation failure (production risk)

**Problem:** Empty `service_worker_map` produces 0 correlations with no warning.
**Fix:** Add a startup validation check — if `service_worker_map` is empty and `gcp_project_id` is set, warn. If running in production mode and the map is empty, fail loudly.
**When:** Before Session D starts. Small change to `correlate.py` or `fetch.py`.
**Effort:** ~30 min.

### Priority 2: Delegation chain extraction (new anomaly signal)

**Problem:** CanonicalEvent doesn't capture `serviceAccountDelegationInfo`. Stolen credential detection requires knowing whether an SA acted through Cloud Run (delegation present) or directly (delegation absent).
**Approach:** Add `delegation_chain: list[str]` to CanonicalEvent. Extract from `protoPayload.authenticationInfo.serviceAccountDelegationInfo[].firstPartyPrincipal.principalEmail`. Store as JSON array in events table.
**When:** Sprint 1B or Session D. This informs invariant design — e.g., INV: "worker SA event without expected delegation chain."
**Effort:** ~2h (schema change + parser update + tests).

### Priority 3: system_event parser (deploy detection)

**Problem:** 9 system_event entries rejected. Contains deployment metadata (who deployed, what image, what config changed).
**Approach:** Add a fourth parser (`system_event_parser.py`) that extracts: deployer identity, revision name, image hash, scaling config. Map to `COMPUTE_UPDATE` action type in `COMPUTE` zone.
**When:** Sprint 1B. Deploy detection is an attack vector — unauthorized deployments are a key Cloud Run threat.
**Effort:** ~3h (new parser + tests + ACTION_MAP expansion).

### Priority 4: EXFIL_RISK baseline bootstrapping

**Problem:** Zero EXFIL_RISK events means no baseline for that zone. First exfil event can't be compared to history.
**Approach:** Two options:
  - **Option A (Sprint 1B):** During attack injection, create a `temp-export-*` bucket to populate EXFIL_RISK. This gives the model at least one observation before scoring.
  - **Option B (design-level):** Treat any first-ever zone appearance as an anomaly signal by definition. If a zone has zero history, ANY event in it has maximum novelty. This may already be implicit in the novelty scoring design.
**When:** Decide approach during Session D world model design.
**Effort:** Option A: ~1h. Option B: verify during scoring implementation.

### Priority 5: Infrastructure SA allow-list

**Problem:** `service-agent-manager` and other GCP internal SAs produce IAM_SET_POLICY events that look like attacker activity.
**Approach:** Extend `known_initiators.json` to include GCP internal SAs with a `role: infrastructure` tag. Provenance enrichment already uses this file — add a `is_gcp_internal` flag to CanonicalEvent or use `is_infrastructure` (already in schema).
**When:** Session D. Low urgency — 4 events across 5 days.
**Effort:** ~1h (config update + enrichment logic).

### Priority 6: Medium-confidence correlation investigation

**Problem:** 25 events at 0.50-0.89 confidence. May indicate temporal window edge cases.
**Approach:** Query these events, examine their temporal gaps and candidate counts. If the pattern is consistent (e.g., events near the 120s window boundary), consider tuning the window or adjusting the confidence formula.
**When:** Session D, during correlation weight calibration.
**Effort:** ~1h analysis.

### Priority 7: `ReplaceService` -> ACTION_MAP

**Problem:** Cloud Run `ReplaceService` (11 events) maps to OTHER. This is a deploy operation with detection value.
**Approach:** Add `("run.googleapis.com", "ReplaceService")` -> `(COMPUTE_UPDATE, COMPUTE)` to ACTION_MAP. Also add a new `COMPUTE_UPDATE` action type to the enum.
**When:** Sprint 1B alongside system_event parser (both are deploy detection).
**Effort:** ~30 min.

### Not prioritized (parking)

- **stderr/varlog parsing:** Application-level logs (gunicorn startup, instance scaling). No actor identity. Low detection value. Revisit if instance lifecycle tracking becomes relevant.
- **KMS_DECRYPT / BQ_JOB_SUBMIT validation:** No real data to test against. Will validate when/if these services are exercised in the sandbox.
- **`unknown` actor events:** 9 events. GCP internal operations without identity. No actionable fix — these will always exist. Tag as `is_infrastructure` if their methods are identifiable.

---

## 10. Methodology Notes

- Inspector and pipeline were run in parallel on the same local snapshot (`data/real/`).
- Inspector ran zero-knowledge (no prior schema assumptions). Pipeline ran with full parser configuration.
- Comparing the two outputs validates that our model covers what the data actually contains.
- All analysis ran locally on an in-memory DuckDB instance. No data was committed or pushed.
- `data/real/` is gitignored — contains real GCP project IDs and email addresses.
