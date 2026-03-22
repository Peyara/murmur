# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 0: Foundation & Data Pipeline** — not started

## Last Completed Milestone

Session 0 (2026-03-22): Project documentation and workflow setup complete.

## Open Blockers / Questions

1. trigger_ref viability — does GCP propagate Cloud Scheduler execution IDs into triggered action audit logs? (Sprint 0B critical experiment)
2. Signal normalization method (z-score vs [0,1]) — decide during Sprint 1 when real distributions observed
3. Sandbox activity diversity — may need manual activity generation for cross-zone events
4. docx/pdf conversion pipeline for final strategy deliverables

## Files to Read for Context

- **Active sprint spec:** `docs/sprints/sprint_00_foundation_data.md`
- **MVP strategy + architecture:** `docs/mvp_strategy.md`
- **Latest learnings:** `LEARNINGS.md` (most recent entry at top)
- **UI concept (reference):** `docs/ui/concept_and_spec.md`

## What To Do Next

Begin Sprint 0A: create `pyproject.toml` with uv, DuckDB schema, CanonicalEvent dataclass, parser for 13 action types, CLI skeleton, pytest fixtures. No GCP dependency yet — all local.
