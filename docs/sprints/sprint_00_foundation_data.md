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

- [x] GCP sandbox project created
- [x] APIs enabled: Cloud Run, Secret Manager, Cloud Logging, Cloud Scheduler, IAM, BigQuery
- [x] Resources provisioned (secrets, Cloud Run, Cloud Scheduler, VM, budget alert)
- [x] Cloud Audit Logs -> GCS bucket sink configured
- [x] **trigger_ref experiment:** COMPLETE — no native per-execution correlation ID exists. See `docs/rd_reports/2026-03-25_trigger_ref_discovery.md` for full findings. Verdict: composite temporal-identity correlation (MEDIUM confidence).
- [x] `src/ingest/fetch.py`: GCS fetch with BlobSource protocol, checkpointing (PR #7, #9)
- [x] `src/ingest/provenance_ingest.py`: trigger_ref extraction + provenance_level assignment (WEAK for resolved, NONE otherwise)
- [x] `ingest --gcs-bucket BUCKET` operational on real logs (PR #9)
- [x] Parse rate measured on real logs: **100%** (80/80 entries). Action type coverage: 34% (53/80 fall to OTHER — unmapped methods)
- [x] Billing budget alert configured ($25 via console)
- [x] e2-micro VM provisioned
- [x] `src/ingest/inspector.py`: cloud-agnostic log structure/pattern/correlation discovery
- [x] `.claude/agents/inspect-interpret.md`: custom agent for agentic log interpretation

### Gate: PASSED (with caveats)

- [x] Real GCP audit logs in DuckDB
- [x] Parse rate >90% on real logs (100% parse rate, 34% action type coverage)
- [x] trigger_ref experiment complete — **verdict: no native ID, use temporal correlation** (fallback mechanism documented, implementation deferred to Sprint 1)
- [x] Manual inspection of 15+ parsed events confirms correctness
- [ ] provenance_level = WEAK for scheduled events — **deferred**: requires multi-log correlation module (Sprint 1)

**Gate caveat:** The trigger_ref experiment revealed that scheduler/Cloud Run invocation logs are NOT audit logs. Achieving WEAK provenance for scheduled events requires ingesting 3 log streams (not just audit logs) and a correlation step. This is Sprint 1 scope, not Sprint 0B. Sprint 0B proved the mechanism is viable and documented the architecture needed.

### Findings Log

- **Dedup race condition fixed (issue #2).** Replaced SELECT-then-INSERT with `INSERT INTO ... ON CONFLICT (event_id) DO NOTHING RETURNING event_id`. DuckDB supports ON CONFLICT + RETURNING — returns the row if inserted, None if conflicted. Atomic, no TOCTOU race.
- **Provenance enrichment is a two-factor check.** trigger_ref presence grants WEAK level, but provenance_source requires actor identity match against known_initiators. Worker SAs that inherit trigger_ref from a scheduler get WEAK/UNKNOWN (not CLOUD_SCHEDULER) — correct, since they aren't the initiator.
- **Parser's basic provenance is a reasonable default.** Parser sets WEAK + CLOUD_SCHEDULER whenever trigger_ref is present (parser.py:165-167). Enrichment step refines provenance_source based on actor identity. Both layers are needed: parser for self-contained parsing, enrichment for classification.
- **84 tests green** (was 70 in Sprint 0A). +1 dedup, +10 provenance, +2 CLI provenance verification, +1 from prior review fix.
- **trigger_ref does NOT exist in real GCP audit logs.** 0 occurrences in 80 entries. `metadata.trigger_ref` was our invention in fixtures. Real correlation requires temporal-identity matching across 3 separate log streams.
- **GCP has 3 fundamentally different log structures** (protoPayload for audit logs, jsonPayload for scheduler, httpRequest for Cloud Run). Multi-format parser dispatcher needed.
- **Cloud Scheduler and Cloud Run invocations are separate from Cloud Audit Logs.** Different logNames, different structure, not captured by audit log sink. Architecture must handle multi-log ingestion.
- **Parse rate 100%, action type coverage 34%.** 53/80 entries map to OTHER. 9 unmapped real methods found (storage.objects.list, secretmanager operations, Cloud Run deploy, Compute instances).
- **118 tests green** (was 84). Full R&D report: `docs/rd_reports/2026-03-25_trigger_ref_discovery.md`.

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
| `tests/test_dedup.py` | Dedup tests |
| `tests/test_provenance_ingest.py` | Provenance enrichment tests |
| `tests/test_cli.py` | CLI tests |
| `tests/test_schema.py` | Schema tests |
