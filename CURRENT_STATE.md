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

### Phase 1: Weight Rebalancing (can start immediately — synthetic data only)

The benchmark runner provides a closed feedback loop. No real data needed.

1. **Diagnose inv_score ceiling.** Currently MAX severity — 2 invariants and 8 produce identical scores. Options:
   - Add `inv_count` as a separate fusion signal (number of fired invariants, normalized)
   - Change inv_score to weighted sum (sum of severities / max possible)
   - Both — count captures breadth, max captures worst-case
2. **Increase physics signal weights.** sigma_coarse (0.10) and bridge_new (0.10) are underweighted — S04's 3-window EXFIL ratchet only scores 7% above S01's 2-event attack. Experiment with 0.15-0.20.
3. **Validate after each change:** `murmur benchmark --all --history data/benchmark/history_benign.jsonl --patterns-json data/benchmark/patterns.json` — attacks must still exceed 2x benign avg.
4. **Target:** S04 should clearly separate from S01 (currently 0.459 vs 0.429 = 7% gap, want 20%+).

### Phase 2: Fresh Data + Pattern Registration (after ~24-48h accumulation — April 3+)

Sandbox diversification deployed April 1 ~20:00 UTC. Wait for sufficient data:
- KMS encrypt: ~300+ events (every 5 min = ~288/day)
- Compute metadata: ~24+ events (every hour)
- Daily cleanup: at least 1 full cycle

Steps:
1. `murmur ingest --local-dir data/real/` or `--gcs-bucket` with fresh pull
2. Verify KMS_ENCRYPT and COMPUTE_METADATA_CHANGE events in DB
3. Register updated sanctioned patterns:
   - normal-worker: add SECRET (KMS) zone → `[CONTROL, COMPUTE, SECRET, DATA, SECRET]`
   - maintainer: add COMPUTE zone → `[CONTROL, IDENTITY, SECRET, COMPUTE]`
4. Re-score and verify discounts apply with new zones

### Phase 3: Deferred
- Live attack injection into GCP sandbox (optional confidence check)
- Edge-case benchmark tests (empty scenario, malformed JSONL) — before production
