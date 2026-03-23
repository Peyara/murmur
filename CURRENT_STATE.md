# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 0B: GCP Provisioning** — not started

## Last Completed Milestone

Sprint 0A (2026-03-23): Foundation data pipeline merged to main (PR #1, squash `3b11364`). Schema (25-field CanonicalEvent, 8 enums, 10 DuckDB tables), parser (14 GCP method mappings -> 13 action types -> 6 zones), dedup, CLI, 71 tests green, CI pipeline (pytest + ruff + bandit). PR reviewed, blocker fixed, 6 items deferred to #2.

## Open Blockers / Questions

1. trigger_ref viability — does GCP propagate Cloud Scheduler execution IDs into triggered action audit logs? (Sprint 0B critical experiment)
2. Signal normalization method (z-score vs [0,1]) — decide during Sprint 1 when real distributions observed
3. Sandbox activity diversity — may need manual activity generation for cross-zone events
4. EXFIL_RISK zone patterns need tuning with real GCP data
5. 6 code/design follow-ups from Sprint 0A review tracked in issue #2 (3 quick fixes for 0B, 3 deferred)

## Files to Read for Context

- **Active sprint spec:** `docs/sprints/sprint_00_foundation_data.md` (Phase 0B section)
- **Sprint 0A review follow-ups:** GitHub issue #2
- **MVP strategy + architecture:** `docs/mvp_strategy.md`
- **Latest learnings:** `LEARNINGS.md` (most recent entry at top)
- **UI concept (reference):** `docs/ui/concept_and_spec.md`

## What To Do Next

1. Address Sprint 0A quick fixes from #2 (mutable default, SHA doc, connection leak) — 15 min
2. Begin Sprint 0B: provision GCP sandbox (murmur-sandbox), configure Cloud Audit Logs -> GCS sink, run trigger_ref experiment, build `src/ingest/fetch.py` and `src/ingest/provenance_ingest.py`. Requires GCP project access.
