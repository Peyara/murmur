# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 1B: Signal Validation Gate** — Benchmark infrastructure complete. Weight rebalancing + fresh data pull remaining.

## Last Completed Milestone

Session G (2026-04-01): Built benchmark infrastructure. 6 scenarios (3 attack, 2 benign, 1 hybrid) validated through full pipeline. Signal validation gate PASSED — attacks score 2.4-2.5x benign average. 388 tests green.

## GCP Sandbox Status (all live, accumulating data)

- Cloud Run `normal-worker` rev 4: reads secret + GCS, encrypts via KMS, writes output. Every 5 min.
- Cloud Run `maintainer` rev 4: rotates secret, generates token, toggles IAM, updates VM label. Every hour.
- KMS keyring `murmur-keyring` / key `worker-encrypt-key`: created, normal-worker-sa has encrypt permission.
- EXFIL_RISK bucket: `gs://public-export-sandbox` created. Empty (attack injection target).
- Scheduler jobs: trigger-normal-worker (5min), trigger-health-check (hourly), trigger-cleanup (daily), trigger-maintainer (hourly)
- Local snapshot: `data/real/` (refreshed 2026-04-01, includes 851 blobs through 19:55 UTC)

## Open Blockers / Questions

1. **inv_score MAX vs SUM** — biggest weight rebalancing question. 8 invariants produce same score as 2.
2. Physics signal differentiation weak — S04 only 7% higher than S01 despite much more complex attack.
3. Fresh data pull needed — verify KMS_ENCRYPT and COMPUTE_METADATA_CHANGE events flowing.
4. Register updated sanctioned patterns on live DB (add KMS zone for normal-worker, COMPUTE for maintainer).
5. B02 fires INV_006 on new secret targets — correct or overly sensitive?

## Files to Read for Context

- **Sprint 1 spec:** `docs/sprints/sprint_01_core_detection.md`
- **Benchmark runner:** `src/benchmark/runner.py` (in-memory isolated scenario runner)
- **Scenarios:** `data/benchmark/` (s01, s04, s07, b01, b02, s13 + history + patterns.json)
- **Benchmark tests:** `tests/test_benchmark.py` (33 tests, all passing)
- **Session G learnings:** `LEARNINGS.md` (top entry)

## What To Do Next

1. **Weight rebalancing:** Experiment with invariant COUNT as signal, increase sigma_coarse/bridge_new weights. Use benchmark as validation — attacks must still exceed 2x.
2. **Fresh data pull:** `murmur ingest --gcs-bucket` → verify KMS/compute events → register updated patterns.
3. **Consider inv_score redesign:** MAX → weighted sum or separate count signal. This is the biggest lever for attack complexity discrimination.
4. **Deferred:** Live attack injection into GCP sandbox as confidence check.
