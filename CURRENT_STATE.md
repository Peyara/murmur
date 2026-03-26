# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 1A: Core Detection Build** — IN PROGRESS. Sessions A+B complete. 24h observation clock running (started 2026-03-26T20:30 UTC, target Session C: 2026-03-27T20:30 UTC).

## Last Completed Milestone

Sprint 1A Session B (2026-03-26): Real Cloud Run worker deployed (reads secret + GCS, writes output). Hourly health check + daily cleanup schedulers live. End-to-end correlation validated on real data: 8/8 events correlated at 0.9998-1.0 confidence. 210 tests green.

## GCP Sandbox Status (all live)

- **Cloud Run `normal-worker`**: Real worker (reads secret_high, reads GCS input, writes GCS output). Revision 2, serving 100%.
- **Scheduler `trigger-normal-worker`**: Every 5 min → GET / (main worker)
- **Scheduler `trigger-health-check`**: Hourly → GET /health
- **Scheduler `trigger-cleanup`**: Daily 3AM UTC → GET /cleanup
- **GCS sink**: Captures all 3 log types (audit + scheduler + Cloud Run) to `murmur-audit-logs-sandbox`
- **GCS buckets**: `murmur-input-sandbox` (3 seed files), `murmur-output-sandbox` (worker writes here)
- **SAs**: `normal-worker-sa` (worker), `scheduler-sa` (scheduler), default compute (Cloud Build)
- **Secrets**: `secret_high` (worker reads), `secret_low` (health check reads), `secret_medium` (human ad-hoc)

## Open Blockers / Questions

1. 24h observation period in progress — do NOT build detection code until Session C observation
2. Hydration validator reports mismatch (deploy noise > worker events) — self-resolves with time
3. Detection latency: GCS sink batch (~75 min worst case) vs Cloud Logging API — post-MVP decision
4. Docker-* and other unmapped audit methods discovered in real data — ACTION_MAP expansion needed
5. Schema migration for existing DuckDB files — track for Sprint 3
6. Self-learning parser — Sprint 2-3 scope, issue to be created
7. EXFIL_RISK pattern tuning — pending from issue #2

## Files to Read for Context

- **Sprint 1 spec:** `docs/sprints/sprint_01_core_detection.md`
- **MVP strategy:** `docs/mvp_strategy.md` (includes hydration/onboarding section)
- **Latest learnings:** `LEARNINGS.md` (Session B entry at top — correlation validated)
- **Correlator:** `src/ingest/correlate.py` (temporal-identity correlation + hydration validation)
- **Worker app:** `scripts/worker/app.py` (3 endpoints: /, /health, /cleanup)

## What To Do Next

1. **Session C (after 2026-03-27T20:30 UTC):** Run inspector on 24h of real multi-format data. Observe zone flux, temporal patterns, actor fingerprints. Calibrate correlation confidence weights against real latency distributions. Identify blind spots.
2. **Session D+:** World model (windowing, zone flux), scoring (invariants, sigma_coarse), provenance scaffold — all informed by Session C observations.
3. **Before Session C:** Run some manual human activity (ad-hoc gcloud commands) at different times to add unstructured events to the observation dataset.
