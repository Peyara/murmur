# CLAUDE.md — Murmur Project

> Project-specific context. Global standards inherited from `Peyara/CLAUDE.md`.

---

## Project Context: Murmur

- **Stack:** Python 3.11+, DuckDB (embedded), GCP Cloud Audit Logs, FastAPI + React + D3.js (UI)
- **Package manager:** uv (NEVER pip)
- **Layers and paths:**
  - Infrastructure: `sql/`, `config/`, `murmur.service`
  - Ingestion: `src/ingest/` (fetch, parser, provenance_ingest, dedup)
  - World Model: `src/world/` (windowing, zone flux graph, EMA baseline)
  - Provenance: `src/provenance/` (patterns, trigger chain, signature stub, residual risk, discovery)
  - Scoring: `src/score/` (invariants, novelty, physics, closure, fusion)
  - Policy: `src/policy/` (state vector, risk energy, shadow bandit)
  - Presentation: `src/report/` (FastAPI API, React+D3 dashboard)
  - Validation: `tests/`, `data/benchmark/`, `data/fixtures/`
- **Correct layering:** `src/score/fusion.py` imports from `src/provenance/residual.py` (scoring calls provenance). `src/provenance/` imports from `src/world/` (provenance reads world model).
- **Incorrect layering:** `src/world/graph.py` importing from `src/score/` (world model must not depend on scoring). `src/ingest/` importing from `src/provenance/` (ingestion feeds provenance, not the reverse).
- **Experiment artifacts:** `data/benchmark/` (frozen scenarios), `data/fixtures/` (sample JSONL)
- **Docs:** `docs/` — strategy, sprint specs, UI concept. `docs/sprints/` — one spec per sprint.

---

## Hydration / Onboarding — Self-Learning Architecture

Murmur is a **self-learning system**. The murmurs of today power the Murmur of tomorrow. It requires a **hydration period** when onboarding to a new platform — this is by design, not a limitation.

The system must observe a platform's actors, services, temporal cadences, and causal patterns before it can correlate and score with confidence. Skipping observation produces false positives. The hydration period is the cost of accuracy at steady state.

**During hydration, Murmur:**
- Ingests and parses all log streams (multi-format)
- Discovers service-to-identity mappings via `validate_service_worker_map()`
- Estimates job cadences from scheduler execution history
- Builds baseline zone flux and actor patterns
- Runs in observation mode — no alerts, no scoring, only learning

**Hydration is complete when:**
- All configured services have confirming observations (identity mapping validated)
- Cadence estimated for all recurring jobs
- >= 1 full cycle of each temporal pattern observed

**Minimum hydration:** ~3x the longest job cadence (15 min for 5-min jobs, 3h for hourly, 3 days for daily).

**Onboarding timeline (investor pitch):**
| Phase | Duration | Output |
|-------|----------|--------|
| Deploy | ~1 hour | Logs flowing |
| Hydrate | 3x longest cadence | Identity mappings, cadence estimates |
| Baseline | 24-48h | Zone flux baseline, scoring calibration |
| Operational | Ongoing | Alerts, provenance, risk scores |

Typical GCP environment (5-min scheduled + hourly maintenance): **operational in ~25h.**

This is the "observe before hypothesize" principle at the system level. It's also what makes Murmur self-maintaining — it continuously validates its own assumptions against new observations, flagging drift without human intervention.

---

## Implementation Communication Protocol

At each **sprint milestone** (logical unit of work completed, e.g., "parser done", "invariants implemented", "attack generator producing trajectories"):

1. **ELI10:** Explain what was just built/validated as if explaining to a 10-year-old. Use analogies. No jargon.
2. **First Principles:** Explain from physics or systems-thinking perspective WHY this approach — what property of the system makes this the right design.
3. **Finding:** What did we learn or validate? Did any assumption hold or break? What surprised us?
4. **Plan Update:** Update the relevant sprint doc under `docs/sprints/` with progress, findings, and any adjustments to next steps.

Skip this protocol for trivial edits (formatting, config, comments). Apply it for anything that changes detection logic, signals, architecture, or validates/invalidates a hypothesis.

---

## Living Plan Discipline

The sprint docs under `docs/sprints/` are living documents. After completing each substep within a sprint:
- Mark the substep as done
- Record validated/invalidated hypotheses
- Note any scope adjustments for remaining substeps
- Flag surprises or blockers

The goal: anyone reading the sprint doc can see exactly where we are, what we've learned, and what's next.

---

## Secrets & Credentials

- `.env` files with real values: NEVER commit (only `.env.example` with placeholders)
- GCP service account key files (`*-credentials.json`, `*-key.json`): NEVER commit
- Real GCP project IDs, service account emails, or resource URLs in source code: use env vars via `config/settings.py`
- If in doubt, check `.gitignore` and run `gitleaks detect` before committing

## GCP Platform Constraints

- **GCS audit log sink exports hourly**, not real-time. Ingestion polling loops must account for 1-2 hour latency. Design pattern: execute actions first, then batch-observe after the hourly boundary.
- **SA key creation may be blocked** by org policy (`iam.disableServiceAccountKeyCreation`). Use `--impersonate-service-account` as alternative for testing.

---

*Last updated: 2026-04-05 — v2.1*
