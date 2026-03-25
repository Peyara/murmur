# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 0B: GCP Provisioning** — 0B-2 GCP sandbox fully provisioned. Security hardlines + reproducibility scripts on branch, PR pending.

## Last Completed Milestone

Sprint 0B-2 (2026-03-24): GCP sandbox fully provisioned (9 APIs, GCS bucket, audit log sink, Data Access logs, 3 secrets, Cloud Run, Cloud Scheduler, e2-micro VM). Audit logs confirmed flowing (9 files in bucket). Security hardlines added (.gitignore, .env pattern, gitleaks, CLAUDE.md rule). Sandbox scripts created (setup, teardown, status). 84 tests green.

## Current Blocker

`gh` CLI not authenticated on this device. Branch `feat/security-hardlines-sandbox-scripts` is pushed but PR not yet created. Run `gh auth login` to authenticate, then create PR.

## GCP Sandbox Status (all live)

| Resource | Status |
|---|---|
| 9 GCP APIs | Enabled |
| GCS bucket `murmur-audit-logs-sandbox` | Created, audit logs flowing (9+ files) |
| Logging sink `murmur-audit-sink` | Active, routing to bucket |
| Data Access audit logs | Enabled (DATA_READ + DATA_WRITE) |
| Secrets (low/medium/high) | Created |
| Cloud Run `normal-worker` | Deployed, HTTP 200 |
| Cloud Scheduler `trigger-normal-worker` | Firing every 5 min, succeeding |
| Budget alert ($25) | Set via console |
| VM `murmur-vm` (e2-micro) | Running, 34.173.237.254 |

## Open Blockers / Questions

1. `gh auth login` — needed to create PR (immediate)
2. trigger_ref viability — Sprint 0B critical experiment (sandbox is live, can now test)
3. Parser redundant provenance logic (parser.py:165-167) — clean up
4. Signal normalization method — decide during Sprint 1
5. EXFIL_RISK zone patterns — tune with real GCP data (data now available)
6. 2 remaining items on issue #2: EXFIL_RISK tuning (Sprint 0B), index planning (Sprint 1)
7. GitHub Dependabot alert (1 low severity) — check https://github.com/Peyara/murmur/security/dependabot/1

## Files to Read for Context

- **Active sprint spec:** `docs/sprints/sprint_00_foundation_data.md` (Phase 0B section)
- **Sprint 0A review follow-ups:** GitHub issue #2 (2 items remaining)
- **MVP strategy + architecture:** `docs/mvp_strategy.md`
- **Sandbox scripts:** `scripts/setup-sandbox.sh`, `scripts/sandbox-status.sh`, `scripts/teardown-sandbox.sh`
- **GCP config:** `.env` (gitignored, real values), `.env.example` (placeholder)
- **Latest learnings:** `LEARNINGS.md` (most recent entry at top)

## What To Do Next

1. Authenticate `gh` CLI: `gh auth login`
2. Create PR for `feat/security-hardlines-sandbox-scripts` branch
3. Merge PR after review
4. Build `src/ingest/fetch.py` (GCS fetch with pagination, reads from bucket)
5. Add `ingest_checkpoints` table + `--gcs-bucket` CLI command
6. Run trigger_ref experiment with real audit logs. Measure parse rate (target >90%).
7. Check Dependabot alert
