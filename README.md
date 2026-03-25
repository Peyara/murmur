# Murmur

An always-on cloud security engine that detects coordinated adversarial activity in GCP environments using physics-informed signals and provenance subtraction.

## Status

**Sprint 0A (Foundation & Data Pipeline): Complete** — local data pipeline operational. Parser, schema, dedup, CLI, 70 tests green.

**Sprint 0B (GCP Provisioning): In progress** — GCP sandbox live, GCSFetcher + CLI consolidated (PR #9 merged), trigger_ref experiment underway. 118 tests green.

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
murmur ingest --local-dir DIR    # Ingest all JSON/JSONL from a directory
murmur ingest --gcs-bucket NAME  # Ingest from a GCS bucket (requires google-cloud-storage)
murmur inspect DIR               # Run cloud-agnostic log inspector on raw log files
uv run pytest -v                 # Run 118 tests
```

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

## Project Structure

```
murmur/
  src/
    schema.py                    # CanonicalEvent dataclass, 8 enums, 25 fields
    cli.py                       # Click CLI: init-db, ingest, inspect
    ingest/
      parser.py                  # GCP audit log JSON -> CanonicalEvent (14 method mappings)
      dedup.py                   # SHA-256 event_id, idempotent INSERT OR IGNORE
      fetch.py                   # BlobSource protocol, LocalFetcher, GCSFetcher, checkpointing
      provenance_ingest.py       # trigger_ref extraction + provenance_level assignment
      inspector.py               # Cloud-agnostic log structure/pattern/correlation discovery
      inspector_agent.py         # Agentic interpretation layer (prompt builder for LLM analysis)
  sql/
    schema.sql                   # All 10 DuckDB tables (events populated, rest ready)
  config/
    settings.py                  # Centralized config: thresholds, weights, patterns
    known_initiators.json        # Cloud Scheduler/Build IDs
  data/
    fixtures/                    # 3 sample JSONL files (normal, attack, quiet)
  tests/                         # 118 tests: schema, parser, dedup, CLI, provenance, fetch
  docs/
    mvp_strategy.md              # Architecture, sprint plan, MVP scope
    sprints/                     # Per-sprint specs with deliverables and gates
    rd_reports/                  # R&D investigation reports (lab notebooks)
    ui/                          # Dashboard concept (Pulse, Flow Map, Lineage)
  scripts/                       # GCP sandbox provisioning, teardown, status
  .claude/agents/                # Custom Claude Code agents (see Agents section)
  .github/workflows/ci.yml      # pytest on PR to main (Python 3.11 + 3.12)
  pyproject.toml                 # uv-managed: duckdb, numpy, click, pytest
```

## Current Capabilities

- **Parse** GCP Cloud Audit Log JSON into typed CanonicalEvents across 6 trust zones
- **Map** 14 GCP API methods to 13 action types (IAM, secrets, KMS, storage, compute)
- **Classify** resources into EXFIL_RISK zone based on configurable bucket name patterns
- **Deduplicate** events via deterministic content hashing (ON CONFLICT DO NOTHING)
- **Fetch** from GCS buckets with incremental checkpointing, or from local directories/files
- **Enrich** provenance: trigger_ref extraction + actor identity matching against known initiators
- **Inspect** raw log files with cloud-agnostic structure discovery, pattern detection, temporal clustering, and cross-log correlation analysis
- **Store** in DuckDB with schema supporting all downstream layers (world model, scoring, provenance, policy)

Not yet built: windowing, zone flux matrix, physics signals, invariants, provenance matching, scoring, policy, dashboard.

## Roadmap

| Sprint | Focus | Status |
|--------|-------|--------|
| 0A: Foundation | Schema, parser, dedup, CLI | Complete |
| 0B: GCP Provisioning | Sandbox, GCS fetch, trigger_ref experiment | In progress |
| 1: Core Detection | Zone flux, sigma_coarse, invariants, basic fusion | Not started |
| 2: Attack Robustness | Parameterized attack generator, signal validation | Not started |
| 3: Provenance + Closure | Full provenance subtraction, closure signals, policy | Not started |
| 4: Dashboard (parallel) | Pulse, Flow Map, Lineage views | Not started |

## Agents

Murmur uses [Claude Code custom agents](https://docs.anthropic.com/en/docs/claude-code/sub-agents) for agentic analysis steps that require LLM reasoning on top of deterministic pipeline output. Agent definitions live in `.claude/agents/`.

### Available Agents

| Agent | Purpose | When to Use |
|-------|---------|-------------|
| `inspect-interpret` | Interprets log inspector output: field mappings, correlation strategy, provenance assessment, trigger_ref verdict | After running `murmur inspect` on raw logs from a new environment, or when validating correlation mechanisms against real data. Reads the deterministic output + raw log samples, produces structured recommendations. |

### How Agents Fit the Pipeline

```
Raw logs  -->  murmur inspect DIR       (deterministic: structure, patterns, clusters)
          -->  @inspect-interpret        (agentic: reasoning, field mapping, recommendations)
          -->  Human reviews findings    (decision: update parser, correlation strategy)
          -->  murmur ingest ...         (deterministic: parse, enrich, store)
```

The deterministic layer (`inspector.py`) does the heavy lifting: schema discovery, cardinality analysis, temporal clustering, cross-log correlation detection. The agentic layer (`inspect-interpret`) reasons about what the patterns mean and produces actionable recommendations for the security monitoring pipeline.

### Invoking Agents

```bash
# From Claude Code chat — @-mention:
> @inspect-interpret analyze data/raw_inspection/

# From CLI — run entire session as this agent:
claude --agent inspect-interpret

# List all available agents:
claude agents
```

## Development

```bash
uv sync                          # Install deps
uv run pytest -v                 # Run 118 tests
uv run pytest -v -k "parser"     # Run specific tests
```

**Branch naming:** `build/`, `feat/`, `fix/`, `chore/` prefixes. Branch from `main`. Never push directly to `main`.

**CI:** GitHub Actions runs pytest on Python 3.11 and 3.12 for all PRs to `main`.

**TDD:** Tests written before implementation. Missing tests are a blocker.

**R&D reports:** Investigation findings live in `docs/rd_reports/` — freeform lab notebooks that go beyond the structured decision log (`LEARNINGS.md`).

## Standards

This project is built and maintained under Peyara engineering standards — a structured methodology for AI-assisted development covering session handoff, hypothesis-driven sprint phasing, TDD discipline, and living documentation. Standards are maintained at the Peyara organization level.
