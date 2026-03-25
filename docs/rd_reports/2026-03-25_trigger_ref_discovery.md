# R&D Report: trigger_ref Discovery & Cloud-Agnostic Log Inspection

**Date:** 2026-03-25
**Sprint:** 0B (GCP Provisioning)
**Mode:** R&D
**Duration:** ~3 hours

---

## 1. Objective

Answer Sprint 0B's critical question: **does GCP propagate any per-execution correlation ID from Cloud Scheduler into the audit log entries of triggered Cloud Run actions?**

Secondary objectives:
- Build a cloud-agnostic log inspector prototype
- Measure parse rate on real GCP audit logs
- Identify correlation mechanisms for WEAK provenance

---

## 2. Method

### 2.1 Data Collection

Downloaded 22 hours of real GCP audit logs from `gs://<BUCKET>/` (3 categories: activity, data_access, system_event). Separately queried Cloud Logging API for scheduler execution logs and Cloud Run request logs — these are NOT audit logs and don't flow through the GCS sink.

**Dataset:** 480 total entries across 5 log types:
- 200 Cloud Run request logs (`run.googleapis.com/requests`)
- 200 Cloud Scheduler execution logs (`cloudscheduler.googleapis.com/executions`)
- 59 Data Access audit logs
- 18 Activity audit logs
- 3 System Event audit logs

### 2.2 Intelligent Log Inspector

Built `src/ingest/inspector.py` — a cloud-agnostic tool that takes raw log files and produces structured analysis with zero prior knowledge of the source system. It performs:
1. **Structure discovery** — recursive field inventory with type detection (email, IP, URI, timestamp, UUID, hex hash)
2. **Cardinality analysis** — fields ranked by cardinality ratio to identify grouping/correlation candidates
3. **Temporal clustering** — single-linkage agglomerative clustering with configurable time window
4. **Cross-log correlation** — value overlap detection across log types
5. **Actor/target heuristic detection** — pattern-based field role proposals

### 2.3 Agentic Interpretation

Built `inspect-interpret` custom Claude Code agent (`.claude/agents/inspect-interpret.md`) that reads the inspector's deterministic output and reasons about field mappings, correlation strategies, and provenance assessments. The agent reads raw samples, cross-references with the canonical schema, and produces structured recommendations.

---

## 3. Raw Findings

### 3.1 Log Type Discovery

**Critical finding:** Cloud Scheduler executions and Cloud Run invocations are NOT Cloud Audit Logs. They live in separate log streams with different logNames:

| Log Stream | logName Pattern | In Audit Log Sink? | Has protoPayload? |
|---|---|---|---|
| Activity audit logs | `cloudaudit.googleapis.com/activity` | YES | YES |
| Data Access audit logs | `cloudaudit.googleapis.com/data_access` | YES | YES |
| System Event audit logs | `cloudaudit.googleapis.com/system_event` | YES | YES |
| Scheduler executions | `cloudscheduler.googleapis.com/executions` | NO | NO (jsonPayload) |
| Cloud Run requests | `run.googleapis.com/requests` | NO | NO (httpRequest) |

**Implication:** The sink filter `logName:"cloudaudit.googleapis.com"` only captures audit logs. Scheduler + Cloud Run invocation logs require either expanding the sink or querying the Cloud Logging API directly.

### 3.2 Field Inventory (Key Fields)

**Audit logs (`protoPayload` structure):**
- `protoPayload.authenticationInfo.principalEmail` — actor identity (2 distinct: human user, logging SA)
- `protoPayload.methodName` — action (12 distinct methods)
- `protoPayload.resourceName` — target resource (41 distinct)
- `protoPayload.requestMetadata.callerIp` — source IP
- `protoPayload.requestMetadata.callerSuppliedUserAgent` — caller tool info
- `metadata.trigger_ref` — **ABSENT in all 80 real entries**

**Scheduler execution logs (`jsonPayload` structure):**
- `jsonPayload.@type` — `AttemptStarted` or `AttemptFinished`
- `jsonPayload.scheduledTime` — when the execution was scheduled
- `jsonPayload.url` — target URL (Cloud Run endpoint)
- `jsonPayload.jobName` — scheduler job resource path
- No `trace`, no `spanId`, no actor identity

**Cloud Run request logs (`httpRequest` structure):**
- `httpRequest.userAgent` — `"Google-Cloud-Scheduler"` (100% of entries)
- `httpRequest.remoteIp` — caller IP (varies across Google infrastructure IPs)
- `trace` — unique per request (`projects/<PROJECT_ID>/traces/<HEX>`)
- `spanId` — unique per request
- `resource.labels.service_name` — `"normal-worker"`

### 3.3 Correlation Analysis

**Scheduler → Cloud Run:** Temporal match. Scheduler's `scheduledTime` ≈ Cloud Run's `timestamp` (within ~1s). Cloud Run's `userAgent` confirms caller. **No shared correlation ID.**

**Cloud Run → Audit Logs:** Identity match (worker SA appears as `principalEmail`). Temporal proximity. But `trace`/`spanId` from Cloud Run does NOT appear in audit logs — only 1 audit log entry out of 80 has a `trace` field.

**Native trigger ID:** `labels.compute.googleapis.com/root_trigger_id` exists on Compute Engine operations (UUID, shared across related entries). Proves GCP CAN propagate trigger IDs — but doesn't do so for Cloud Scheduler.

---

## 4. Hypotheses: Held vs Broke

| Hypothesis | Status | Evidence |
|---|---|---|
| `metadata.trigger_ref` exists in real GCP audit logs | **BROKE** | 0 occurrences in 80 entries. Field was our invention in fixtures. |
| Audit logs capture all cloud activity | **BROKE** | Scheduler executions and Cloud Run invocations are separate log streams, not audit logs. |
| `trace` propagates from Cloud Run into audit logs | **BROKE** | Cloud Run has trace/spanId on every entry. Audit logs have trace on 1 of 80 entries. |
| Temporal correlation is viable at 5-min cadence | **HELD** | Clear 5-minute periodic pattern. Scheduler → Cloud Run latency is ~1s. No overlap at this cadence. |
| `userAgent` identifies scheduler as caller | **HELD** | `"Google-Cloud-Scheduler"` on 100% of Cloud Run request entries. |
| All 14 ACTION_MAP methods appear in real data | **BROKE** | Only 3 mapped methods appear (GCS_WRITE, IAM_SET_POLICY, IAM_CREATE_SA). 9 unmapped real methods found. |

---

## 5. Unexpected Discoveries

1. **GCP has 3 fundamentally different log structures** (protoPayload, jsonPayload, httpRequest). The parser can't be a single function — it needs a multi-format dispatch layer.

2. **The logging SA writing to the bucket generates its own audit logs** (25 of 80 entries = 31%). These are meta-logs: audit logs of the audit log export. Murmur needs to filter these out or classify them as infrastructure noise.

3. **Scheduler logs arrive ~10s after the actual Cloud Run invocation.** The `timestamp` on scheduler AttemptStarted is ~10s AFTER the Cloud Run request timestamp. This means the scheduler knows the result before it logs the attempt — the log is post-hoc, not pre-hoc.

4. **`callerIp` varies across scheduler invocations** — Google uses multiple infrastructure IPs. IP-based correlation is unreliable.

5. **The inspector found 109 temporal clusters** with a 30s window. Many are pairs (scheduler + Cloud Run entries near each other), validating temporal clustering as a viable correlation mechanism.

---

## 6. trigger_ref Verdict

**No native per-execution correlation ID exists in GCP audit logs for the Cloud Scheduler → Cloud Run chain.**

**Recommended implementation: Composite temporal-identity correlation**

```
Scheduler AttemptStarted (scheduledTime, jobName, url)
    ↓ temporal match (scheduledTime ≈ Cloud Run timestamp, within 15s)
    ↓ url match (scheduler url == Cloud Run requestUrl)
    ↓ userAgent match (== "Google-Cloud-Scheduler")
Cloud Run Request (timestamp, trace, userAgent)
    ↓ identity match (Cloud Run worker SA == audit log principalEmail)
    ↓ temporal match (within 30s)
Audit Log Entry (principalEmail, timestamp, methodName)
```

**trigger_ref encoding:** `sched:{job_id}:{scheduledTime_epoch}`
Example: `sched:trigger-normal-worker:1742929205`

**Confidence: MEDIUM.** Works well for:
- Single scheduler job with 5-minute cadence
- No concurrent executions
- Low worker SA reuse

Degrades when:
- Multiple jobs hit the same Cloud Run service within the temporal window
- Concurrent scheduler retries (HTTP 500 → retry pattern observed)
- Same SA used by multiple services

---

## 7. Architecture Implications

### 7.1 Multi-Log Ingestion (Decision: Needed)

Murmur must ingest 3 log streams, not just audit logs:
1. **Audit logs** (from GCS sink) — what actions occurred
2. **Scheduler execution logs** (from Cloud Logging API or expanded sink) — when jobs fired
3. **Cloud Run request logs** (from Cloud Logging API or expanded sink) — what services were invoked

This requires:
- Expanding the GCS sink filter OR adding a Cloud Logging API fetcher
- A multi-format parser dispatcher (protoPayload / jsonPayload / httpRequest)
- A correlation step between parse and enrich that builds the trigger chain

### 7.2 Parser Architecture (Decision: Needs Redesign)

The current parser is hardcoded for `protoPayload` audit log structure. It needs:
- A format detector (which log type is this entry?)
- Per-format parsers that produce CanonicalEvents
- A configurable field mapping layer (informed by the inspector)

### 7.3 Provenance Pipeline Change

Current: `parse → enrich → insert`
Proposed: `parse → correlate → enrich → insert`

The new `correlate` step builds the trigger chain by matching events across log types using the temporal-identity mechanism. This is where `trigger_ref` gets assigned — it's derived, not parsed.

---

## 8. Recommendations

### 8.1 Immediate (Sprint 0B Close)
- Update fixtures to reflect real GCP log structure (remove synthetic `trigger_ref`)
- Update `known_initiators.json` with real scheduler SA
- Expand GCS sink to include scheduler and Cloud Run request logs
- Map the 9 unmapped methods found in real data

### 8.2 Sprint 1
- Build multi-format parser dispatcher
- Implement temporal-identity correlation module (`src/ingest/correlate.py`)
- Add the `correlate` step to the ingestion pipeline

### 8.3 MVP Stretch Goal: Agent-Driven ACTION_MAP Discovery

**Problem:** The static ACTION_MAP (14 methods → 13 action types) only covers 34% of real audit log methods. Each new cloud deployment may have different methods based on which services are active.

**Proposed solution:** Use the `inspect-interpret` agent to:
1. Run the inspector on raw logs from a new deployment
2. Discover all service/method combinations present
3. Propose ACTION_MAP entries (method → action type + zone) based on:
   - Method name semantics (Create/Delete/Get/Set patterns)
   - Service name → zone mapping (iam → IDENTITY, storage → DATA, etc.)
   - Cardinality and frequency patterns
4. Human reviews and approves the proposed mappings
5. Export as a configuration file that the parser loads at startup

This makes ACTION_MAP a **configuration artifact generated by agent analysis**, not hardcoded Python. It's the seed of Murmur's cloud-agnostic onboarding capability — feed any cloud's logs into the inspector + agent, get a field mapping config out.

### 8.4 Post-MVP: Cloud-Agnostic Onboarding Vision

The inspector + agent combo is the foundation for deploying Murmur on any cloud:

1. **Bootstrap:** Customer points Murmur at their log storage
2. **Discover:** Inspector analyzes structure, patterns, correlations
3. **Propose:** Agent recommends field mappings and correlation strategy
4. **Configure:** Human approves/adjusts, generates config
5. **Ingest:** Parser uses the config to parse, correlate, and enrich

This eliminates the need for per-cloud-provider parser implementations. The detective work moves from code to configuration, guided by an LLM agent.

### 8.5 Inspector v2 Ideas
- **Periodicity detection:** Detect recurring patterns (every 5 min = scheduled, every hour = batch job)
- **Anomaly surface:** Find entries that don't match any cluster (potential attack signals)
- **Schema drift detection:** Compare current run with previous runs to detect new/missing fields
- **Multi-cloud normalization:** Detect cloud provider from log structure and suggest canonical mappings

---

## 9. Appendix

### A. Parse Rate Results

- **Rate:** 100% (80/80 audit log entries parsed without errors)
- **Action type coverage:** 34% mapped to specific types, 66% fallthrough to OTHER
- **Unmapped methods found:**

| Count | Service / Method |
|---|---|
| 34 | storage.googleapis.com / storage.objects.list |
| 3 | iam.googleapis.com / iam.serviceAccounts.actAs |
| 3 | secretmanager / CreateSecret |
| 3 | secretmanager / AddSecretVersion |
| 3 | run.googleapis.com / CreateService |
| 2 | run.googleapis.com / SetIamPolicy |
| 2 | cloudscheduler / CreateJob |
| 2 | compute.googleapis.com / instances.insert |
| 1 | run.googleapis.com / CreateService (v1) |

### B. Temporal Correlation Evidence

At 5-minute cadence with 100 scheduler executions observed:
- Mean scheduler-to-CloudRun latency: ~1 second
- No overlapping execution windows detected
- Scheduler logs arrive ~10s after Cloud Run processes the request
- 100% of Cloud Run requests have `userAgent: "Google-Cloud-Scheduler"`

### C. Files Created/Modified

| File | Purpose |
|---|---|
| `src/ingest/inspector.py` | Cloud-agnostic log structure/pattern/correlation discovery |
| `src/ingest/inspector_agent.py` | Agentic interpretation layer (prompt builder) |
| `.claude/agents/inspect-interpret.md` | Custom Claude Code agent for log analysis |
| `src/cli.py` | Added `inspect` command |
| `.gitignore` | Added `data/raw_inspection/` |
| `README.md` | Updated with agents section, current capabilities |
| `docs/rd_reports/` | Created directory for R&D investigation reports |
