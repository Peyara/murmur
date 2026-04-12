# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 3: Closure + Policy** — MERGED to main (PR #23).
**Sprint 2: UI + API** — on branch `feature/sprint-2-api-ui`, PR #21 open. Not merged to main.

## Last Completed Milestone

Session K (2026-04-12): Sprint 3 closure system built, calibrated, generalized, merged. Three-layer engine (explicit pairs, temporal TTL, settlement + auto-discovery), policy layer (risk_energy + shadow bandit), ClosureConfig for platform generalization. 23.0x separation on real data. 438 tests green on main. dotenv auto-loading fixed permanently.

## GCP Sandbox Status

- Cloud Run `normal-worker` + `maintainer`: active, generating baseline
- Live DB: `murmur.duckdb` — 35,155 events, 1,666 windows, 2,497 scored pairs
- Data through: 2026-04-12 13:55 UTC
- Tier distribution: HIGH 0, MEDIUM 6, WATCH 390, NORMAL 2,098
- trigger_ref coverage: 86.9% (Apr 6+ data)

## Open Blockers / Questions

1. **Closure signal ablation** — run with weights=0 to isolate independent contribution vs weight rebalancing
2. **Sprint 2 merge** — PR #21 on branch, contains dotenv fix main doesn't have yet
3. **Synthetic generator** — next major work item. Replaces benchmark expansion (6/18 scenarios).
4. **Discovery causality** — pair mining finds co-occurrence, not causation. Needs directionality filter.
5. **Post-MVP roadmap** — synthetic generator → autonomous agent simulation (OpenClaw/similar) → real customer data (Shamreen's company)

## Files to Read for Context

- **Sprint 3 closure:** `src/score/closure.py` (ClosureConfig, engine), `src/policy/` (energy, bandit)
- **Fusion weights:** `src/score/fusion.py` (10 signals, closure_gap + orphaned_priv)
- **Session K learnings:** `LEARNINGS.md` (top entry)
- **Post-MVP roadmap:** memory file `project_roadmap_post_mvp.md`
- **Agentic red teaming refs:** memory file `reference_agentic_red_teaming.md`

## What To Do Next

1. **Merge Sprint 2** — land PR #21 to main (or cherry-pick dotenv fix separately)
2. **Design synthetic generator** — architecture for diverse audit log trajectory generation at scale
3. **Run closure ablation** — weights=0 to prove/disprove signal value
4. **Sprint spec cleanup** — write/update sprint docs for Sprint 2 + Sprint 3
