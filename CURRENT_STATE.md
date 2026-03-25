# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 0B: GCP Provisioning** — Infrastructure provisioned. PR #6 merged. Next: fetch.py + trigger_ref experiment.

## Last Completed Milestone

Sprint 0B-2 (2026-03-24): PR #6 merged to main. GCP sandbox fully provisioned (9 APIs, GCS bucket, audit log sink, Data Access logs, 3 secrets, Cloud Run, Cloud Scheduler, e2-micro VM). Security hardlines added (.gitignore, .env pattern, gitleaks, pre-commit hook, CLAUDE.md rule). Sandbox scripts created (setup, teardown, status). 4 review warnings fixed. 84 tests green.

## GCP Sandbox Status (all live)

| Resource | Status |
|---|---|
| 9 GCP APIs | Enabled |
| GCS bucket `murmur-audit-logs-sandbox` | Created, audit logs flowing (9+ files) |
| Logging sink `murmur-audit-sink` | Active, routing to bucket |
| Data Access audit logs | Enabled (DATA_READ + DATA_WRITE) |
| Secrets (low/medium/high) | Created |
| Cloud Run `normal-worker` | Deployed, requires auth (--no-allow-unauthenticated) |
| Cloud Scheduler `trigger-normal-worker` | Firing every 5 min |
| Budget alert ($25) | Set via console |
| VM `murmur-vm` (e2-micro) | Running |

## Open Blockers / Questions

1. 7 Copilot nits from PR #6 — fix on `fix/` branch before next sprint
2. GitHub Dependabot alert (1 low severity) — check
3. trigger_ref viability — Sprint 0B critical experiment (sandbox ready)
4. Parser redundant provenance logic (parser.py:165-167) — clean up
5. Signal normalization method — decide during Sprint 1
6. EXFIL_RISK zone patterns — tune with real GCP data
7. 2 remaining items on issue #2: EXFIL_RISK tuning (Sprint 0B), index planning (Sprint 1)

## Files to Read for Context

- **Active sprint spec:** `docs/sprints/sprint_00_foundation_data.md` (Phase 0B section)
- **Sprint 0A review follow-ups:** GitHub issue #2 (2 items remaining)
- **MVP strategy + architecture:** `docs/mvp_strategy.md`
- **Sandbox scripts:** `scripts/setup-sandbox.sh`, `scripts/sandbox-status.sh`, `scripts/teardown-sandbox.sh`
- **GCP config:** `.env` (gitignored, real values), `.env.example` (placeholder)
- **Latest learnings:** `LEARNINGS.md` (most recent entry at top)

## What To Do Next

1. Fix 7 Copilot nits on `fix/` branch, merge
2. Check Dependabot alert
3. Build `src/ingest/fetch.py` (GCS fetch with pagination, reads from bucket)
4. Add `ingest_checkpoints` table + `--gcs-bucket` CLI command
5. Run trigger_ref experiment with real audit logs. Measure parse rate (target >90%).
