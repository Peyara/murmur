# Correlation Validation: Real GCP Audit Logs

**Date:** 2026-03-26
**Mode:** Production (Sprint 1A Session B)
**Verdict:** Temporal-identity correlation works on real data. 8/8 events correlated at 0.9998-1.0 confidence.

---

## 1. What We Set Out to Validate

Sprint 0B discovered that GCP has no native per-execution correlation ID (trigger_ref). Session A built a temporal-identity correlator that reconstructs the causal chain:

```
Scheduler fires → Cloud Run receives request → Worker SA executes API calls
```

The correlator uses composite confidence scoring:
- Identity match (SA → service): 0.4 weight
- URL match (scheduler target → Cloud Run endpoint): 0.3 weight
- Ambiguity penalty (1/candidate_count): 0.2 weight
- Temporal ratio (gap/cadence): 0.1 weight

**Hypothesis:** This mechanism can link independently-produced log entries with high confidence on real data, not just test fixtures.

## 2. Experimental Setup

### Activity Generator
- **Cloud Run `normal-worker`**: Flask app, triggered every 5 min by Cloud Scheduler
  - Reads `secret_high` from Secret Manager (→ SECRET_ACCESS / SECRET zone)
  - Lists + reads file from `murmur-input-sandbox` (→ GCS_LIST + GCS_READ / DATA zone)
  - Writes processed result to `murmur-output-sandbox` (→ GCS_WRITE / DATA zone)
- **Actor:** `normal-worker-sa@project-1f4f13c5-912e-45ae-b8a.iam.gserviceaccount.com`
- **Scheduler:** `trigger-normal-worker` (*/5 * * * *, OIDC auth via `scheduler-sa`)
- **Additional noise:** Cloud Build deploy events (~40 Docker-* audit entries), human ad-hoc commands, infrastructure logging SA

### Data Collection
- GCS logging sink captures all 3 log types: `cloudaudit.googleapis.com`, `cloudscheduler.googleapis.com`, `run.googleapis.com`
- Sink batches hourly, delivers ~5-15 min after hour close
- Test window: 19:00-20:00 UTC, 2026-03-26
- 2 worker invocations (19:50, 19:55) in the test window

### Pipeline
Multi-format dispatcher → per-format parsers → temporal-identity correlator → confidence scoring

## 3. Results

### 3.1 Parsing

| Log Type | Entries | Parser | Routing |
|----------|---------|--------|---------|
| Scheduler executions | 24 | SchedulerExecution | 100% correct |
| Cloud Run requests | 12 | CloudRunRequest | 100% correct |
| Audit logs (data_access + activity) | 157 | CanonicalEvent | 100% correct |

157 audit entries included: 8 from worker SA, ~40 from Cloud Build, ~60 from human, ~30 from infrastructure SA, ~20 from other.

### 3.2 Correlation

| Event | Time | Action | Zone | trigger_ref | Confidence |
|-------|------|--------|------|-------------|------------|
| 1 | 19:50:14 | SECRET_ACCESS | SECRET | sched:trigger-normal-worker:1774569014 | 0.9999 |
| 2 | 19:50:14 | GCS_LIST | DATA | sched:trigger-normal-worker:1774569014 | 0.9999 |
| 3 | 19:50:14 | GCS_READ | DATA | sched:trigger-normal-worker:1774569014 | 0.9999 |
| 4 | 19:50:15 | GCS_WRITE | DATA | sched:trigger-normal-worker:1774569014 | 0.9998 |
| 5 | 19:55:07 | SECRET_ACCESS | SECRET | sched:trigger-normal-worker:1774569307 | 1.0000 |
| 6 | 19:55:07 | GCS_LIST | DATA | sched:trigger-normal-worker:1774569307 | 0.9999 |
| 7 | 19:55:07 | GCS_READ | DATA | sched:trigger-normal-worker:1774569307 | 0.9999 |
| 8 | 19:55:07 | GCS_WRITE | DATA | sched:trigger-normal-worker:1774569307 | 0.9999 |

**8/8 events correlated. 0 false positives. 0 false negatives in the test window.**

Confidence breakdown for event 5 (perfect score = 1.0):
- Identity match: 0.4 (worker SA matches configured mapping)
- URL match: 0.3 (scheduler target URL matches Cloud Run service URL)
- Ambiguity: 0.2 (1 candidate in window — no competing matches)
- Temporal: 0.1 (gap ≈ 4s relative to 300s cadence → ratio ≈ 0.99)

### 3.3 Uncorrelated Events (correct negatives)

149 audit events correctly NOT correlated:
- Infrastructure SA (logging writes): no match in service_worker_map → confidence 0.0
- Human activity (samreen654): no match in service_worker_map → confidence 0.0
- Cloud Build SA (Docker operations): no match in service_worker_map → confidence 0.0

### 3.4 Hydration Status

`validate_service_worker_map()` reported: `hydration_complete=False`, mismatch detected.

**Explanation:** In the 19:00 hour, human activity (deploy + manual commands) produced 37 events in scheduler→cloudrun correlation windows, outnumbering the 8 worker events. The validator picked `samreen654@gmail.com` as the most frequent SA — correct behavior given the data, but a false mismatch caused by deploy noise.

**Expected resolution:** After ~2 hours of uninterrupted 5-min worker invocations (~24 events/hour × 4 per invocation = 96 worker events vs diminishing human activity), the worker SA will dominate and hydration will confirm.

### 3.5 Infrastructure Tagging

All 4 logging SA events in the 18:00 hour correctly tagged `is_infrastructure=True`.

## 4. Observations (Not Pre-Labeled)

Things we noticed in the real data that we didn't predict:

1. **Cloud Build generates rich audit trail.** A single `--source` deploy produced ~40 Docker-* events from the default compute SA. These are `Docker-GetManifest`, `Docker-StartUpload`, `Docker-FinishUpload`, `Docker-HeadBlob`, `Docker-PutManifest`, `Docker-ServeBlob`. None of these are in our ACTION_MAP — they all map to OTHER/DATA. This is a real-world signal class we hadn't considered.

2. **A new SA appeared: `serverless-robot-prod`.** The `service-1013530516622@serverless-robot-prod.iam.gserviceaccount.com` SA performed Docker operations during the Cloud Run deployment. This is GCP's internal service agent for Cloud Run container image pulling. It's infrastructure, not attacker or operator.

3. **`storage.buckets.getStorageLayout` appears in human gcloud commands.** This is a read-only metadata operation that's not in our ACTION_MAP. Maps to OTHER/DATA currently.

4. **`google.logging.v2.LoggingServiceV2.ListLogEntries` appears** from human `gcloud run services logs read` commands. This is a Cloud Logging API read, not an audit log — but it produces a data_access audit event.

5. **Worker events cluster tightly (~1s spread per invocation).** The 4 events per invocation (secret + list + get + create) all have timestamps within 1 second. This tight clustering is useful for the correlator — the temporal window could be tightened significantly from the current 120s.

## 5. Implications

### For Sprint 1 (detection)
- **Correlation is validated.** The pipeline can proceed to world model and scoring.
- **Zone flux baseline** will be SECRET↔DATA from worker, with occasional OTHER from uncorrelated events.
- **Provenance subtraction** will work: correlated events (confidence > 0.99) get full discount, uncorrelated human events get none.

### For Hydration Design
- **Deploy noise can delay hydration.** A heavy deploy during the hydration window skews the validator. Consider excluding one-time deploy events or requiring a minimum number of worker observations before declaring hydration complete.
- **Current minimum_observations threshold is too coarse.** Should be per-service minimum, not global minimum.

### For Production (post-MVP)
- **GCS sink batching is the real latency bottleneck** (~75 min worst case), not correlation quality. Cloud Logging API streaming would enable near-real-time detection.
- **ACTION_MAP will need ongoing expansion.** Real environments produce methods we don't anticipate. The self-learning parser (Sprint 2-3) becomes more important with this evidence.

## 6. What's Next

24h observation clock started at 2026-03-26T20:30 UTC. Session C will:
1. Run the inspector on 24h of accumulated multi-format data
2. Measure zone flux distribution, temporal patterns, actor fingerprints
3. Verify hydration self-resolves after deploy noise subsides
4. Identify blind spots — patterns in the data that no invariant would catch
5. Calibrate scoring parameters before building the world model

---

*Evidence collected from real GCP audit logs in project `project-1f4f13c5-912e-45ae-b8a`. No synthetic data used. All findings derived from observation, not pre-labeled expectations.*
