# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 1A: Core Detection Build** — Sessions A-D complete. Session E target: provenance scaffold (patterns, trigger chain, residual risk, benchmark).

## Last Completed Milestone

Session D (2026-03-31): World model + scoring layers built and validated on real data. PR #15 created. 315 tests green. 5607 events, 8 actors, 350 windows scored.

## GCP Sandbox Status (all live, accumulating data)

- Cloud Run `normal-worker` rev 3: reads secret + GCS, writes output. Every 5 min.
- Cloud Run `maintainer` rev 3: rotates secret, generates token, toggles IAM. Every hour.
- Scheduler jobs: trigger-normal-worker (5min), trigger-health-check (hourly), trigger-cleanup (daily), trigger-maintainer (hourly)
- SAs: normal-worker-sa, maintenance-sa, scheduler-sa
- GCS sink: all 3 log types → murmur-audit-logs-sandbox
- Local snapshot: `data/real/` (431 files, 12MB, refreshed 2026-03-29)

## Open Blockers / Questions

1. PR #15 needs review/merge before Session E
2. Schnakenberg skip-zero blind spot — revisit formula in Sprint 1B if attacks aren't detected
3. maintenance-sa scores 0.32 mean — provenance discount (Session E) should fix
4. Fusion normalization bounds are guesses — empirically set in Sprint 1B
5. 25 medium-confidence correlations (0.50-0.89) — investigate in Sprint 1B
6. service-agent-manager INV_001 false positive — Sprint 1B allow-list fix
7. R&D review session planned — dig into real data results, stress-test assumptions

## Files to Read for Context

- **Sprint 1 spec:** `docs/sprints/sprint_01_core_detection.md`
- **Session D learnings:** `LEARNINGS.md` (top entry)
- **World model:** `src/world/window.py`, `src/world/graph.py`
- **Scoring:** `src/score/invariants.py`, `src/score/fusion.py`
- **Real data validation:** run `murmur init-db && murmur ingest --local-dir data/real/ && murmur window && murmur score`

## What To Do Next

1. **Review + merge PR #15** (world model + scoring)
2. **R&D review session:** Examine invariant fire patterns, sigma_coarse distribution, score separation. Stress-test assumptions about detection power.
3. **Session E:** Provenance scaffold — patterns.py, trigger_chain.py, signature.py, residual.py. Benchmark scenarios (S01/S04/S07/B01/B02/S13).
4. **Sprint 1B:** Attack injection, EXFIL_RISK baseline, system_event parser, GCP SA allow-list. Validate whether sigma_coarse adds detection power beyond invariants+novelty.
