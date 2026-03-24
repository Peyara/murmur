# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 0B: GCP Provisioning** — 0B-1 complete, 0B-2 in progress (plan approved, blocked on gcloud auth)

## Last Completed Milestone

Sprint 0B-1 (2026-03-23): PR #5 merged. Dedup race fixed. Provenance enrichment pipeline built. 84 tests green.

## Current Blocker

gcloud CLI authenticated as shamreen.iram@lightbird.ai, not samreen654@gmail.com. Run `gcloud auth login samreen654@gmail.com` before resuming. User already created GCP account, billing, and murmur-sandbox project in console.

## GCP Provisioning Plan (approved, not yet executed)

10-step plan at `.claude/plans/wondrous-scribbling-graham.md`. Region: us-central1. Steps:
1. Set project + link billing (project already created in console)
2. Enable APIs (Run, SecretManager, Logging, Scheduler, IAM, BQ, Storage, CloudBuild, ResourceManager)
3. Create GCS bucket `murmur-audit-logs-sandbox`
4. Configure audit log sink to GCS
5. Enable Data Access audit logs
6. Create 3 secrets (low/medium/high)
7. Deploy Cloud Run hello container (normal-worker)
8. Create Cloud Scheduler job (trigger_ref experiment)
9. Billing budget alert ($25, via console)
10. Provision e2-micro VM

## Open Blockers / Questions

1. gcloud auth — authenticate as samreen654@gmail.com (immediate blocker)
2. trigger_ref viability — Sprint 0B-2 critical experiment (after provisioning)
3. Parser redundant provenance logic (parser.py:165-167) — clean up in 0B-2
4. Signal normalization method — decide during Sprint 1
5. EXFIL_RISK zone patterns — tune with real GCP data
6. 2 remaining items on issue #2: EXFIL_RISK tuning (Sprint 0B), index planning (Sprint 1)

## Files to Read for Context

- **GCP provisioning plan:** `.claude/plans/wondrous-scribbling-graham.md`
- **Active sprint spec:** `docs/sprints/sprint_00_foundation_data.md` (Phase 0B section)
- **Sprint 0A review follow-ups:** GitHub issue #2 (2 items remaining)
- **MVP strategy + architecture:** `docs/mvp_strategy.md`
- **Latest learnings:** `LEARNINGS.md` (most recent entry at top)

## What To Do Next

1. Authenticate gcloud: `gcloud auth login samreen654@gmail.com`
2. Execute GCP provisioning plan steps 1-10 (interactive, guided)
3. After provisioning: build `src/ingest/fetch.py`, add `ingest_checkpoints` table, add `--gcs-bucket` CLI command
4. Run trigger_ref experiment with real audit logs. Measure parse rate (target >90%).
