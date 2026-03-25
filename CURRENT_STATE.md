# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 0B: GCP Provisioning** — Fetch pipeline done (PR #7). Remaining: GCSFetcher + trigger_ref experiment.

## Last Completed Milestone

Sprint 0B-3 (2026-03-24): PR #7 merged. Fetch pipeline with BlobSource protocol, LocalFetcher, DuckDB checkpointing (`ingest_checkpoints` table), `--local-dir` CLI option. Dependabot alert dismissed. 102 tests green.

## GCP Sandbox Status (all live)

| Resource | Status |
|---|---|
| 9 GCP APIs | Enabled |
| GCS bucket `murmur-audit-logs-sandbox` | Created, audit logs flowing (9+ files) |
| Logging sink `murmur-audit-sink` | Active, routing to bucket |
| Data Access audit logs | Enabled (DATA_READ + DATA_WRITE) |
| Secrets (low/medium/high) | Created |
| Cloud Run `normal-worker` | Deployed, requires auth (--no-allow-unauthenticated) |
| Cloud Scheduler `trigger-normal-worker` | Firing every 5 min |
| Budget alert ($25) | Set via console |
| VM `murmur-vm` (e2-micro) | Running |

## Open Blockers / Questions

1. 7 Copilot nits from PR #6 + 4 nits from PR #7 — fix on `fix/` branch
2. trigger_ref viability — Sprint 0B critical experiment (pipeline ready)
3. Parser redundant provenance logic (parser.py:165-167) — clean up
4. Signal normalization method — decide during Sprint 1
5. EXFIL_RISK zone patterns — tune with real GCP data
6. 2 remaining items on issue #2: EXFIL_RISK tuning (Sprint 0B), index planning (Sprint 1)

## Files to Read for Context

- **Active sprint spec:** `docs/sprints/sprint_00_foundation_data.md` (Phase 0B section)
- **Fetch pipeline:** `src/ingest/fetch.py` (BlobSource protocol, LocalFetcher, checkpointing)
- **Sprint 0A review follow-ups:** GitHub issue #2 (2 items remaining)
- **MVP strategy + architecture:** `docs/mvp_strategy.md`
- **Sandbox scripts:** `scripts/setup-sandbox.sh`, `scripts/sandbox-status.sh`, `scripts/teardown-sandbox.sh`
- **Latest learnings:** `LEARNINGS.md` (most recent entry at top)

## What To Do Next

1. Fix deferred nits (PR #6 + PR #7) on `fix/` branch, merge
2. Add `google-cloud-storage` dependency, implement `GCSFetcher` (~30 lines)
3. Wire `--gcs-bucket BUCKET` CLI option
4. Run trigger_ref experiment with real audit logs
5. Measure parse rate on real logs (target >90%)
6. Manual inspection of 10+ parsed events for correctness
