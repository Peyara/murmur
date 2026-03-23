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

- [x] `pyproject.toml` with `uv`: Python 3.11+, duckdb, numpy, pytest, click
- [x] `sql/schema.sql`: all DuckDB table definitions (events, sanctioned_patterns, actor_windows, zone_flux_windows, edges_window, closure_state, opening_closing_pairs, risk_scores, policy_suggestions, candidate_patterns)
- [x] `src/schema.py`: CanonicalEvent dataclass with all fields + enums (action_type, target_zone, provenance_level, actor_type, etc.)
- [x] `data/fixtures/`: 3 sample JSONL files:
  - `normal_scheduled.jsonl` — Cloud Scheduler triggers normal-worker (6 events)
  - `key_secret_attack.jsonl` — key creation + secret access sequence (6 events)
  - `quiet_window.jsonl` — minimal/no activity (1 event)
- [x] `src/ingest/parser.py`: GCP audit log JSON -> CanonicalEvent for all 13 action types (14 GCP method mappings)
- [x] `src/ingest/dedup.py`: idempotent event_id from deterministic hash of (ts, actor_id, methodName, resource, insertId)
- [x] `src/cli.py`: `init-db`, `ingest --sample`, `ingest --file PATH`
- [x] `config/settings.py`: all configurable parameters centralized (window_size, thresholds, GCS bucket, exfil_risk_patterns, etc.)
- [x] `tests/conftest.py`: DuckDB in-memory fixture, sample event factory
- [x] Unit tests: 70 tests total
  - Parser: 14 action type mapping + 13 field extraction + 5 edge case + 3 EXFIL_RISK zone = 35 tests
  - Schema: 20 tests (table creation, existence, PK, dataclass, enums)
  - Dedup: 7 tests (deterministic ID, duplicate rejection, field verification)
  - CLI: 8 tests (init-db, ingest --sample, ingest --file)

### Gate: PASSED

`pytest` green (70 tests). `ingest --sample` populates DuckDB with 13 events. All 14 GCP method mappings (13 action types) parse correctly.

### Findings Log

- **EXFIL_RISK zone is resource-path-derived, not action-type-derived.** No GCP method maps directly to EXFIL_RISK. Parser checks bucket name prefixes (`external-*`, `public-*`) + configurable patterns in settings.py. Will need tuning with real GCP data in 0B.
- **Hatchling build backend requires explicit package path.** `src/` layout needs `[tool.hatch.build.targets.wheel] packages = ["src", "config"]` in pyproject.toml.
- **14 GCP method patterns -> 13 action types.** IAM_SET_POLICY has 2 sources (iam.googleapis.com, cloudresourcemanager.googleapis.com). IAM_IMPERSONATE has 2 (GenerateAccessToken, GenerateIdToken). Parser uses ordered list with substring matching — more specific patterns checked first.

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
