# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 1A: Core Detection Build** — Sessions A+B+C complete. Maintainer deployed. Session D target: world model + scoring layers.

## Last Completed Milestone

Mini session (2026-03-28): Deployed Workflow 2 (maintainer service). Hourly IDENTITY/CONTROL/SECRET zone events accumulating from `maintenance-sa`. PR #14 merged.

## GCP Sandbox Status (all live, accumulating data)

- Cloud Run `normal-worker` rev 3: reads secret + GCS, writes output. Every 5 min.
- Cloud Run `maintainer` rev 3: rotates secret, generates token, toggles IAM. Every hour.
- Scheduler jobs: trigger-normal-worker (5min), trigger-health-check (hourly), trigger-cleanup (daily), trigger-maintainer (hourly)
- SAs: normal-worker-sa, maintenance-sa, scheduler-sa
- GCS sink: all 3 log types → murmur-audit-logs-sandbox
- Secrets: secret_high, secret_low, secret_maintenance
- Local snapshot: `data/real/` (5 days Session C data, gitignored — needs refresh for Session D)

## Open Blockers / Questions

1. Org policy blocks SA key creation (`constraints/iam.disableServiceAccountKeyCreation`) — affects Sprint 1B attack scenario S01?
2. Update `known_initiators.json` with `maintenance-sa` before running correlator on new data
3. 25 medium-confidence correlations (0.50-0.89) — investigate in Session D
4. EXFIL_RISK baseline: first-ever zone event = max novelty, or synthesize during attack injection?
5. Schema migration for existing DuckDB files: `ALTER TABLE events ADD COLUMN delegation_chain VARCHAR DEFAULT '[]';`
6. Secret version accumulation from maintainer (~720/month) — cleanup needed?
7. Detection latency: GCS sink batch vs Cloud Logging API — post-MVP

## Files to Read for Context

- **Sprint 1 spec:** `docs/sprints/sprint_01_core_detection.md` (includes Session C findings + parked items)
- **Session C RD report:** `docs/rd_reports/2026-03-27_session_c_24h_inspection.md`
- **Zone flux design notes:** `.claude/plans/eager-strolling-bumblebee.md` (tiered confidence strategy)
- **Latest learnings:** `LEARNINGS.md` (mini session + Session C entries)
- **Maintainer service:** `scripts/maintainer/app.py` + `deploy.sh`

## What To Do Next

1. **Session D:** Refresh `data/real/` snapshot (will now include maintainer events). Build world model layer — 15-min windowing (`src/world/window.py`), zone flux 6x6 matrix (`src/world/graph.py`) with observation counts per cell, edge tracking. Apply tiered confidence design (Cold/Warm/Calibrated).
2. **Session D:** Scoring layer — invariants, sigma_coarse (handle zero-flux cells), novelty scoring with confidence tiers, basic fusion.
3. **Sprint 1B:** Attack injection, EXFIL_RISK baseline, system_event parser, GCP SA allow-list.
