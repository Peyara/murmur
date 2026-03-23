# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 0B: GCP Provisioning** — not started

## Last Completed Milestone

Sprint 0A review follow-ups (2026-03-23): PR #4 merged (`27c9d52`). Fixed mutable default arg, SHA truncation doc, CLI connection leak, fallback logging. 4 of 7 issue #2 items resolved. Peyara-standards updated with fix branch standard (v1.4).

## Open Blockers / Questions

1. trigger_ref viability — does GCP propagate Cloud Scheduler execution IDs into triggered action audit logs? (Sprint 0B critical experiment)
2. Signal normalization method (z-score vs [0,1]) — decide during Sprint 1 when real distributions observed
3. Sandbox activity diversity — may need manual activity generation for cross-zone events
4. EXFIL_RISK zone patterns need tuning with real GCP data
5. 3 remaining items on issue #2: dedup race (Sprint 0B/1), EXFIL_RISK tuning (Sprint 0B), index planning (Sprint 1)

## Files to Read for Context

- **Active sprint spec:** `docs/sprints/sprint_00_foundation_data.md` (Phase 0B section)
- **Sprint 0A review follow-ups:** GitHub issue #2 (3 items remaining)
- **MVP strategy + architecture:** `docs/mvp_strategy.md`
- **Latest learnings:** `LEARNINGS.md` (most recent entry at top)
- **UI concept (reference):** `docs/ui/concept_and_spec.md`

## What To Do Next

1. Begin Sprint 0B: provision GCP sandbox (murmur-sandbox), configure Cloud Audit Logs -> GCS sink, run trigger_ref experiment, build `src/ingest/fetch.py` and `src/ingest/provenance_ingest.py`. Requires GCP project access.
