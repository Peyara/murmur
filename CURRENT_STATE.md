# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 1A: Core Detection Build** — Sessions A-F complete. R&D review done. Sandbox diversified. Benchmark + attack injection remaining (Sprint 1B).

## Last Completed Milestone

Session F (2026-04-01): R&D review + sandbox diversification. Full signal analysis, false positive classification, invariant blind spot mapping, score separation projections. Deployed KMS encrypt (worker rev 4), VM label update (maintainer rev 4), EXFIL_RISK bucket, INV_011 (delegation chain). 355 tests. Data accumulating.

## GCP Sandbox Status (all live, accumulating data)

- Cloud Run `normal-worker` rev 4: reads secret + GCS, **encrypts via KMS**, writes output. Every 5 min.
- Cloud Run `maintainer` rev 4: rotates secret, generates token, toggles IAM, **updates VM label**. Every hour.
- KMS keyring `murmur-keyring` / key `worker-encrypt-key`: created, normal-worker-sa has encrypt permission.
- EXFIL_RISK bucket: `gs://public-export-sandbox` created. Empty (attack injection target).
- Scheduler jobs: trigger-normal-worker (5min), trigger-health-check (hourly), trigger-cleanup (daily), trigger-maintainer (hourly)
- SAs: normal-worker-sa, maintenance-sa, scheduler-sa
- Local snapshot: `data/real/` (refreshed 2026-04-01, includes 851 blobs through 19:55 UTC)

## Open Blockers / Questions

1. Verify maintainer rev 4 VM label audit events flowing (after 02:00 UTC trigger)
2. After ~3h KMS data: register updated sanctioned pattern for normal-worker (add KMS zone)
3. service-agent-manager INV_001 false positive — Sprint 1B allow-list fix
4. 1,127 parse errors — likely stderr/varlog files, non-blocking
5. Weight rebalancing — Sprint 1B with attack data

## Files to Read for Context

- **Sprint 1 spec:** `docs/sprints/sprint_01_core_detection.md` (updated with Session F findings + sandbox diversification)
- **Session F learnings:** `LEARNINGS.md` (top entry — R&D review findings, signal analysis, sandbox diversification)
- **Invariants:** `src/score/invariants.py` (11 invariants, INV_011 = delegation chain)
- **Settings:** `config/settings.py` (service_worker_map now includes maintainer)
- **Worker:** `scripts/worker/app.py` (rev 4 with KMS encrypt)
- **Maintainer:** `scripts/maintainer/app.py` (rev 4 with VM label update)

## What To Do Next

1. **Verify new data flowing:** Ingest fresh data, confirm KMS_ENCRYPT and COMPUTE_METADATA_CHANGE events parsed correctly. Confirm INV_008/INV_009 baseline established.
2. **Register updated sanctioned patterns:** Add KMS zone to normal-worker pattern, add COMPUTE zone to maintainer pattern.
3. **Sprint 1B: Attack injection + signal validation gate.** Both invariant-triggering (S01, S04 into EXFIL_RISK) and stealth attacks (stolen credential without delegation chain). Weight rebalancing experiments. Benchmark scenarios.
4. **Deferred Tier 3:** Cross-actor patterns, data volume anomaly, temporal anomaly.
