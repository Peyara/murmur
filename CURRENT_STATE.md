# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 1A: Core Detection Build** — Sessions A+B COMPLETE. 24h observation clock running. Session C target: 2026-03-27T20:30 UTC.

## Last Completed Milestone

Sprint 1A Session B (2026-03-26): Real worker deployed, correlation validated on real data (8/8 at 0.9998-1.0 confidence). PR #11 + #12 merged. 213 tests green. PreToolUse hook for sensitive data scanning installed globally.

## GCP Sandbox Status (all live, accumulating data)

- Cloud Run `normal-worker` rev 3: reads secret + GCS, writes output. Every 5 min.
- Scheduler jobs: trigger-normal-worker (5min), trigger-health-check (hourly), trigger-cleanup (daily POST)
- GCS sink: all 3 log types (audit + scheduler + cloudrun) → murmur-audit-logs-sandbox
- SAs: normal-worker-sa, scheduler-sa, default compute
- Buckets: murmur-audit-logs-sandbox, murmur-input-sandbox (3 seed files), murmur-output-sandbox

## Open Blockers / Questions

1. ~~24h observation in progress~~ — DONE (Session C complete)
2. Hydration validator mismatch (deploy noise) — verify self-resolves with 5 days of data
3. Correlation confidence weights — 25 medium-confidence events (0.50-0.89) need investigation
4. Docker-* audit methods from Cloud Build — mapped to OTHER/DATA, acceptable (82 events, deploy-only)
5. Detection latency: GCS sink batch vs Cloud Logging API — post-MVP
6. Self-learning parser — Sprint 2-3, issue to be created
7. Schema migration for existing DuckDB files — Sprint 3. **Note:** `delegation_chain` column added in Session C. Existing DuckDB files need: `ALTER TABLE events ADD COLUMN delegation_chain VARCHAR DEFAULT '[]';`
8. EXFIL_RISK pattern tuning — pending from issue #2

## Files to Read for Context

- **Sprint 1 spec:** `docs/sprints/sprint_01_core_detection.md`
- **Correlation validation report:** `docs/rd_reports/2026-03-26_trigger_ref_correlation_benign_validation.md`
- **MVP strategy:** `docs/mvp_strategy.md` (includes hydration/onboarding section)
- **Latest learnings:** `LEARNINGS.md` (Sessions A+B entries at top)
- **Worker app:** `scripts/worker/app.py`

## What To Do Next

1. **Session C (after 2026-03-27T20:30 UTC):** Run inspector on 24h of real multi-format data. Observe zone flux, temporal patterns, actor fingerprints, blind spots. Calibrate correlation weights.
2. **Session D+:** World model + scoring + provenance scaffold — informed by Session C observations.
