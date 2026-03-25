# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 0B: GCP Provisioning** — Fetch pipeline done, nits resolved. Remaining: GCSFetcher + trigger_ref experiment.

## Last Completed Milestone

PR #8 (2026-03-24): Fixed 9 deferred review nits from PRs #6 + #7. Shell script fixes (curl, bucket deletion, audit log checks), LocalFetcher `is_dir()` validation, parser CLOUD_SCHEDULER cleanup. 103 tests green.

## GCP Sandbox Status (all live)

| Resource | Status |
|---|---|
| 9 GCP APIs | Enabled |
| GCS bucket `murmur-audit-logs-sandbox` | Created, audit logs flowing (9+ files) |
| Logging sink `murmur-audit-sink` | Active, routing to bucket |
| Data Access audit logs | Enabled (DATA_READ + DATA_WRITE) |
| Secrets (low/medium/high) | Created |
| Cloud Run `normal-worker` | Deployed, requires auth |
| Cloud Scheduler `trigger-normal-worker` | Firing every 5 min |
| Budget alert ($25) | Set via console |
| VM `murmur-vm` (e2-micro) | Running |

## Open Blockers / Questions

1. trigger_ref viability — Sprint 0B critical experiment (pipeline ready)
2. 3 deferred PR #7 nits — fix with GCSFetcher (click.Path, mutual exclusivity, _ingest_content)
3. Signal normalization method — decide during Sprint 1
4. EXFIL_RISK zone patterns — tune with real GCP data
5. 2 remaining items on issue #2: EXFIL_RISK tuning (Sprint 0B), index planning (Sprint 1)

## Files to Read for Context

- **Active sprint spec:** `docs/sprints/sprint_00_foundation_data.md` (Phase 0B section)
- **Fetch pipeline:** `src/ingest/fetch.py` (BlobSource protocol, LocalFetcher, checkpointing)
- **Sprint 0A review follow-ups:** GitHub issue #2 (2 items remaining)
- **MVP strategy + architecture:** `docs/mvp_strategy.md`
- **Latest learnings:** `LEARNINGS.md` (most recent entry at top)

## What To Do Next

1. Add `google-cloud-storage` dependency, implement `GCSFetcher` (~30 lines)
2. Wire `--gcs-bucket BUCKET` CLI option (fix 3 deferred PR #7 nits here)
3. Run trigger_ref experiment with real audit logs
4. Measure parse rate on real logs (target >90%)
5. Manual inspection of 10+ parsed events for correctness
