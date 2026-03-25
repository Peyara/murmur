# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 0B: GCP Provisioning** — Implementation complete. PR #9 open (GCSFetcher + CLI consolidation). Remaining: merge PR #9, trigger_ref experiment, parse rate validation.

## Last Completed Milestone

PR #9 (2026-03-25): GCSFetcher + SingleFileFetcher, unified all CLI ingest paths through `fetch_and_ingest()`, fixed 3 deferred PR #7 nits + 3 review warnings. 118 tests green.

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

1. trigger_ref viability — Sprint 0B critical experiment (pipeline ready, PR #9 must merge first)
2. 2 remaining items on issue #2: EXFIL_RISK tuning (Sprint 0B), index planning (Sprint 1)
3. Signal normalization method — decide during Sprint 1
4. EXFIL_RISK zone patterns — tune with real GCP data
5. `gh pr edit` blocked by Projects Classic deprecation — use REST API workaround

## Files to Read for Context

- **Active sprint spec:** `docs/sprints/sprint_00_foundation_data.md` (Phase 0B section)
- **Fetch pipeline:** `src/ingest/fetch.py` (BlobSource protocol, LocalFetcher, SingleFileFetcher, GCSFetcher, checkpointing)
- **CLI:** `src/cli.py` (unified ingest with 4 modes)
- **Sprint 0A review follow-ups:** GitHub issue #2 (2 items remaining)
- **MVP strategy + architecture:** `docs/mvp_strategy.md`
- **Latest learnings:** `LEARNINGS.md` (most recent entry at top)

## What To Do Next

1. Merge PR #9 (squash merge)
2. Run trigger_ref experiment with real audit logs (`murmur ingest --gcs-bucket murmur-audit-logs-sandbox`)
3. Measure parse rate on real logs (target >90%)
4. Manual inspection of 10+ parsed events for correctness
5. Document trigger_ref findings — native propagation or fallback to temporal correlation
6. Close Sprint 0B gate
