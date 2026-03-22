# Murmur

An always-on cloud security engine that detects coordinated adversarial activity in GCP environments using physics-informed signals and provenance subtraction.

## Status

**Sprint 0A (Foundation & Data Pipeline): Complete** — local data pipeline operational. Parser, schema, dedup, CLI, 70 tests green.

**Sprint 0B (GCP Provisioning): Not started** — requires GCP sandbox setup and trigger_ref experiment.

## Architecture

```
PRESENTATION    FastAPI + React + D3.js                          [Sprint 4]
POLICY          risk_energy(), shadow suggestions                [Sprint 3]
SCORING         Invariants, physics signals, closure, fusion     [Sprint 1-3]
PROVENANCE      Pattern registry, trigger chain, residual risk   [Sprint 1-3]
WORLD MODEL     15-min windowing, 6x6 zone flux matrix           [Sprint 1]
INGESTION       GCS fetch, parser, trigger_ref, dedup            [Sprint 0] <-- here
INFRASTRUCTURE  GCP Sandbox, DuckDB, systemd, e2-micro VM       [Sprint 0]
```

## Quick Start

```bash
uv sync                          # Install dependencies
murmur init-db                   # Create DuckDB with all 10 tables
murmur ingest --sample           # Parse and load 13 sample events
murmur ingest --file PATH        # Ingest a single JSONL file
uv run pytest -v                 # Run 70 tests
```

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

## Project Structure

```
murmur/
  src/
    schema.py                    # CanonicalEvent dataclass, 8 enums, 25 fields
    cli.py                       # Click CLI: init-db, ingest
    ingest/
      parser.py                  # GCP audit log JSON -> CanonicalEvent (14 method mappings)
      dedup.py                   # SHA-256 event_id, idempotent INSERT OR IGNORE
  sql/
    schema.sql                   # All 10 DuckDB tables (events populated, rest ready)
  config/
    settings.py                  # Centralized config: thresholds, weights, patterns
    known_initiators.json        # Cloud Scheduler/Build IDs (populated in Sprint 0B)
  data/
    fixtures/                    # 3 sample JSONL files (normal, attack, quiet)
  tests/                         # 70 tests: schema, parser, dedup, CLI
  docs/
    mvp_strategy.md              # Architecture, sprint plan, MVP scope
    sprints/                     # Per-sprint specs with deliverables and gates
    ui/                          # Dashboard concept (Pulse, Flow Map, Lineage)
  .github/workflows/ci.yml      # pytest on PR to main (Python 3.11 + 3.12)
  pyproject.toml                 # uv-managed: duckdb, numpy, click, pytest
```

## Current Capabilities

- **Parse** GCP Cloud Audit Log JSON into typed CanonicalEvents across 6 trust zones
- **Map** 14 GCP API methods to 13 action types (IAM, secrets, KMS, storage, compute)
- **Classify** resources into EXFIL_RISK zone based on configurable bucket name patterns
- **Deduplicate** events via deterministic content hashing
- **Store** in DuckDB with schema supporting all downstream layers (world model, scoring, provenance, policy)
- **Extract** trigger_ref from log metadata (basic; full provenance resolution in Sprint 0B)

Not yet built: windowing, zone flux matrix, physics signals, invariants, provenance matching, scoring, policy, dashboard.

## Roadmap

| Sprint | Focus | Status |
|--------|-------|--------|
| 0A: Foundation | Schema, parser, dedup, CLI | Complete |
| 0B: GCP Provisioning | Sandbox, GCS fetch, trigger_ref experiment | Not started |
| 1: Core Detection | Zone flux, sigma_coarse, invariants, basic fusion | Not started |
| 2: Attack Robustness | Parameterized attack generator, signal validation | Not started |
| 3: Provenance + Closure | Full provenance subtraction, closure signals, policy | Not started |
| 4: Dashboard (parallel) | Pulse, Flow Map, Lineage views | Not started |

## Development

```bash
uv sync                          # Install deps
uv run pytest -v                 # Run tests
uv run pytest -v -k "parser"     # Run specific tests
```

**Branch naming:** `build/`, `feat/`, `fix/`, `chore/` prefixes. Branch from `main`.

**CI:** GitHub Actions runs pytest on Python 3.11 and 3.12 for all PRs to `main`.

**TDD:** Tests written before implementation. Missing tests are a blocker.

## Standards

This project is built and maintained under Peyara engineering standards — a structured methodology for AI-assisted development covering session handoff, hypothesis-driven sprint phasing, TDD discipline, and living documentation. Standards are maintained at the Peyara organization level.
