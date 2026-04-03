# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 1B: Signal Validation Gate** — Complete. PR #19 ready for merge.

## Last Completed Milestone

Session H (2026-04-02): Fresh GCS data pull, fixed 3 scoring bugs (parser case mismatch, column mapping, weight rebalancing). WATCH dropped 841→7 on real data. 395 tests green. Attack/benign ratio 2.7x.

## GCP Sandbox Status (all live, accumulating data)

- Cloud Run `normal-worker` rev 4: reads secret + GCS, encrypts via KMS, writes output. Every 5 min.
- Cloud Run `maintainer` rev 4: rotates secret, toggles IAM, updates VM label. Every hour.
- KMS keyring `murmur-keyring` / key `worker-encrypt-key`: active, normal-worker encrypting every 5 min.
- Local snapshot: `data/real/` (synced 2026-04-02, includes data through April 3 00:55 UTC)
- Live DB: `murmur.duckdb` — 14,560 events, scored with rebalanced weights.

## Open Blockers / Questions

1. **PR #19 needs merge** — fix/scoring-rebalance-session-h branch, 2 commits.
2. S04-S01 gap at 15% (target 20%) — sigma_coarse should close it under adversarial load.
3. burst_per_min normalization inverted for stealth attacks — parked.
4. B02 INV_006 on secret rotation — correct or overly sensitive?
5. Checkpoint bug for multi-prefix local ingestion (lexicographic ordering) — workaround: use GCS source_id.
6. Column mapping fragility — `_EVENT_COLS` manually synced with CanonicalEvent. Deferred NIT.

## Files to Read for Context

- **Sprint 1 spec:** `docs/sprints/sprint_01_core_detection.md`
- **Fusion weights:** `src/score/fusion.py` (FUSION_WEIGHTS, sigmoid_normalize)
- **Session H learnings:** `LEARNINGS.md` (top entry)
- **PR #19:** https://github.com/Peyara/murmur/pull/19

## What To Do Next

1. **Merge PR #19** after any final review.
2. **Live attack injection (Phase 3)** — inject adversarial activity into GCP sandbox to validate sigma_coarse activation and close S04-S01 gap.
3. **Deferred review fixes** — column mapping generation from dataclasses.fields() on a fix/ branch.
4. **Edge-case benchmark tests** — empty scenario, malformed JSONL — before production.
