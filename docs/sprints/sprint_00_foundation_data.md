# Sprint 0: Foundation & Data Pipeline

## Hypothesis

Can we reliably ingest GCP Cloud Audit Logs into DuckDB and establish trigger_ref as the foundation for WEAK provenance?

## Key Risk

trigger_ref may not propagate natively from Cloud Scheduler into the audit log entries of triggered actions. If this fails, the entire WEAK provenance tier is broken. This sprint treats trigger_ref as THE critical experiment.

## Stack Layers

- **Infrastructure:** GCP sandbox, DuckDB, e2-micro VM, systemd
- **Ingestion:** GCS fetch, parser, trigger_ref extraction, dedup

## Duration: 4-5 days

---

## Phase 0A: Local Setup (2-3 days)

### Deliverables

- [ ] `pyproject.toml` with `uv`: Python 3.11+, duckdb, numpy, pytest, click
- [ ] `sql/schema.sql`: all DuckDB table definitions (events, sanctioned_patterns, actor_windows, zone_flux_windows, edges_window, closure_state, opening_closing_pairs, risk_scores, policy_suggestions, candidate_patterns)
- [ ] `src/schema.py`: CanonicalEvent dataclass with all fields + enums (action_type, target_zone, provenance_level, actor_type, etc.)
- [ ] `data/fixtures/`: 3 sample JSONL files:
  - `normal_scheduled.jsonl` — Cloud Scheduler triggers normal-worker
  - `key_secret_attack.jsonl` — key creation + secret access sequence
  - `quiet_window.jsonl` — minimal/no activity
- [ ] `src/ingest/parser.py`: GCP audit log JSON -> CanonicalEvent for all 13 action types (see mapping table in original spec)
- [ ] `src/ingest/dedup.py`: idempotent event_id from deterministic hash of (ts, actor_id, methodName, resource, insertId)
- [ ] `src/cli.py`: `init-db`, `ingest --sample`, `ingest --file PATH`
- [ ] `config/settings.py`: all configurable parameters centralized (window_size, thresholds, GCS bucket, etc.)
- [ ] `tests/conftest.py`: DuckDB in-memory fixture, sample event factory
- [ ] Unit tests:
  - Parser: one test per action type (13 tests)
  - Schema: table creation succeeds
  - Dedup: duplicate events rejected, unique events accepted
  - event_id: deterministic (same input = same hash)

### Gate

`pytest` green. `ingest --sample` populates DuckDB with correct event count. All 13 action types parse correctly.

### Findings Log

_Updated as work progresses:_

---

## Phase 0B: GCP Provisioning (2 days)

### Deliverables

- [ ] GCP sandbox project `murmur-sandbox` created
- [ ] APIs enabled: Cloud Run, Secret Manager, Cloud Logging, Cloud Scheduler, IAM, BigQuery
- [ ] Resources provisioned:
  - Secrets: `secret_low`, `secret_medium`, `secret_high`
  - Cloud Run service: `normal-worker`
  - Cloud Scheduler: job calling normal-worker every 5 minutes
- [ ] Cloud Audit Logs -> GCS bucket `murmur-audit-logs` sink configured
- [ ] **trigger_ref experiment:**
  - Attempt: Configure Cloud Scheduler to propagate execution ID in structured log context
  - Verify: Does execution ID appear in the audit log entries of triggered actions?
  - If YES: `provenance_ingest.py` extracts it as trigger_ref
  - If NO: Implement fallback (temporal correlation: scheduled action within N seconds of Cloud Scheduler execution log entry)
  - Document: which approach works and why
- [ ] `src/ingest/fetch.py`: GCS fetch with pagination
- [ ] `src/ingest/provenance_ingest.py`: trigger_ref extraction + provenance_level assignment (WEAK for resolved, NONE otherwise)
- [ ] `ingest --gcs-bucket BUCKET` operational on real logs
- [ ] Parse rate measured on real logs: target >90%
- [ ] Billing budget alert configured
- [ ] e2-micro VM provisioned (pipeline not yet deployed to it)

### Gate

- Real GCP audit logs in DuckDB
- Parse rate >90% on real logs
- trigger_ref populated for Cloud Scheduler events (native or fallback)
- Manual inspection of 10+ parsed events confirms correctness
- provenance_level = WEAK for scheduled events, NONE for others

### Findings Log

_Updated as work progresses:_

---

## Files Created/Modified

| File | Purpose |
|---|---|
| `pyproject.toml` | Project config, dependencies |
| `sql/schema.sql` | DuckDB table definitions |
| `src/schema.py` | CanonicalEvent dataclass + enums |
| `src/cli.py` | CLI entry point |
| `src/ingest/fetch.py` | GCS fetch |
| `src/ingest/parser.py` | Audit log parser |
| `src/ingest/provenance_ingest.py` | trigger_ref + provenance_level |
| `src/ingest/dedup.py` | Event deduplication |
| `config/settings.py` | Centralized config |
| `config/known_initiators.json` | Cloud Scheduler/Build IDs |
| `data/fixtures/*.jsonl` | Sample event files |
| `tests/conftest.py` | Test fixtures |
| `tests/test_parser.py` | Parser tests |
