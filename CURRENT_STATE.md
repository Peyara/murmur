# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 0B: GCP Provisioning** — 0B-1 complete (provenance enrichment), 0B-2 pending (GCS fetch + infra)

## Last Completed Milestone

Sprint 0B-1 (2026-03-23): PR #5 merged. Dedup race fixed (ON CONFLICT DO NOTHING). Provenance enrichment pipeline built (`provenance_ingest.py`). CLI wired: parse -> enrich -> insert. 84 tests green. PR reviewed (Claude + Copilot, 0 blockers, 1 warning fixed in-PR, 1 deferred).

## Open Blockers / Questions

1. trigger_ref viability — does GCP propagate Cloud Scheduler execution IDs into triggered action audit logs? (Sprint 0B-2 critical experiment)
2. Parser redundant provenance logic (parser.py:165-167) — hardcodes WEAK+CLOUD_SCHEDULER, enrichment overwrites. Clean up in 0B-2.
3. Signal normalization method (z-score vs [0,1]) — decide during Sprint 1
4. Sandbox activity diversity — may need manual activity generation for cross-zone events
5. EXFIL_RISK zone patterns need tuning with real GCP data
6. 2 remaining items on issue #2: EXFIL_RISK tuning (Sprint 0B), index planning (Sprint 1). Dedup race FIXED.

## Files to Read for Context

- **Active sprint spec:** `docs/sprints/sprint_00_foundation_data.md` (Phase 0B section)
- **Sprint 0A review follow-ups:** GitHub issue #2 (2 items remaining)
- **MVP strategy + architecture:** `docs/mvp_strategy.md`
- **Latest learnings:** `LEARNINGS.md` (most recent entry at top)

## What To Do Next

1. Begin Sprint 0B-2 on a new branch: build `src/ingest/fetch.py` (BlobSource protocol with GCS + Local implementations), add `ingest_checkpoints` table to schema, add `--gcs-bucket` CLI command, add `google-cloud-storage` dependency. Clean up parser redundant provenance logic.
2. GCP sandbox provisioning (interactive): create murmur-sandbox project, enable APIs, provision resources, configure audit log sink, set billing alert, provision e2-micro VM.
3. Run trigger_ref experiment with real GCP audit logs. Measure parse rate (target >90%).
