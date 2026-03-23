# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 0B: GCP Provisioning** — not started

## Last Completed Milestone

Sprint 0A (2026-03-22): Foundation data pipeline complete. Schema (25-field CanonicalEvent, 8 enums, 10 DuckDB tables), parser (14 GCP method mappings → 13 action types → 6 zones), dedup, CLI, 70 tests green. GitHub Actions CI configured.

## Open Blockers / Questions

1. trigger_ref viability — does GCP propagate Cloud Scheduler execution IDs into triggered action audit logs? (Sprint 0B critical experiment)
2. Signal normalization method (z-score vs [0,1]) — decide during Sprint 1 when real distributions observed
3. Sandbox activity diversity — may need manual activity generation for cross-zone events
4. EXFIL_RISK zone patterns need tuning with real GCP data

## Files to Read for Context

- **Active sprint spec:** `docs/sprints/sprint_00_foundation_data.md` (Phase 0B section)
- **MVP strategy + architecture:** `docs/mvp_strategy.md`
- **Latest learnings:** `LEARNINGS.md` (most recent entry at top)
- **UI concept (reference):** `docs/ui/concept_and_spec.md`

## What To Do Next

Begin Sprint 0B: provision GCP sandbox (murmur-sandbox), configure Cloud Audit Logs → GCS sink, run trigger_ref experiment, build `src/ingest/fetch.py` for GCS pagination and `src/ingest/provenance_ingest.py` for full trigger_ref extraction + provenance_level assignment. Requires GCP project access.
