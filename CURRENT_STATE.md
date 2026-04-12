# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 3: Closure + Policy** — MERGED to main (PR #23).
**Sprint 2: UI + API** — on branch `feature/sprint-2-api-ui`, PR #21 open. Not merged to main.

## Last Completed Milestone

Session L (2026-04-12): Added Autonomous mode to peyara-standards (PR #4 merged). Third session mode for parallel agentic execution with PR-gated review, worktree isolation, relaxed sign-off within scope boundaries. No Murmur code changes this session.

## GCP Sandbox Status

- Cloud Run `normal-worker` + `maintainer`: active, generating baseline
- Live DB: `murmur.duckdb` — 35,155 events, 1,666 windows, 2,497 scored pairs
- Data through: 2026-04-12 13:55 UTC
- Tier distribution: HIGH 0, MEDIUM 6, WATCH 390, NORMAL 2,098
- trigger_ref coverage: 86.9% (Apr 6+ data)

## Open Blockers / Questions

1. **Merge Sprint 2** — PR #21 on branch, contains dotenv fix main doesn't have yet
2. **Synthetic generator** — next major work item. Replaces benchmark expansion (6/18 scenarios).
3. **Closure signal ablation** — run with weights=0 to isolate independent contribution vs weight rebalancing
4. **Discovery causality** — pair mining finds co-occurrence, not causation. Needs directionality filter.
5. **Autonomous mode untested** — spec exists in peyara-standards but no session has run in Autonomous mode yet
6. **peyara-standards unreviewed additions** — new commands (architect, cleanup-pass, tdd-guide, etc.), settings-base.json, autonomous-loops-reference.md appeared on remote

## Files to Read for Context

- **Sprint 3 closure:** `src/score/closure.py` (ClosureConfig, engine), `src/policy/` (energy, bandit)
- **Fusion weights:** `src/score/fusion.py` (10 signals, closure_gap + orphaned_priv)
- **Session L learnings:** `LEARNINGS.md` (top entry)
- **Autonomous mode spec:** `peyara-standards/global/CLAUDE.md` (Mode: Autonomous section)
- **Post-MVP roadmap:** memory file `project_roadmap_post_mvp.md`

## What To Do Next

1. **Merge Sprint 2** — land PR #21 to main (or cherry-pick dotenv fix separately)
2. **Review peyara-standards additions** — new commands and settings from remote
3. **Design synthetic generator** — architecture for diverse audit log trajectory generation at scale
4. **Run closure ablation** — weights=0 to prove/disprove signal value
5. **Try Autonomous mode** — first real test with a Murmur feature task
