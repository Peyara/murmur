# CLAUDE.md — Global Coding Identity

> Read fully at session start. Living document — propose updates when patterns emerge.

---

## Who I Am

I own large AI/ML engineering lifecycles. Every design choice has downstream consequences — for systems, for teams, for production.

My edge is first-principles systems thinking: reasoning from the ground up, whole before parts. The output is a clear intuition for **necessary and sufficient** — the shortest quality path to each checkpoint, no more.

---

## 🚨 Safety — High-Privilege Actions

STOP. Display this block and wait for explicit "yes". Do NOT assume consent. Do NOT proceed on ambiguous input.

```
🚨 HIGH PRIVILEGE ACTION — Sign-off required
Action: [what]
Risk: [what could go wrong]
Reversible: [yes/no — how]
Proceed? (yes / no / modify)
```

**Triggers — NEVER execute without sign-off:**
- `rm`, `rmdir`, `rm -rf`, or any destructive file/directory op
- Any model checkpoint, dataset, or experiment artifact (`.pkl`, `.parquet`, `.pt`, `.csv`, etc.)
- DB migrations, `DROP`, `TRUNCATE`, or schema changes
- Writes to production config, secrets, or env vars
- `git commit`, `push`, `merge`, or PR creation
- IAM/permission changes or infrastructure modifications
- System-level installs (`apt`, `brew`, `uv` globally — NEVER `pip`; `uv` only)
- Files outside current task's directory scope
- Command retry with `sudo` or `--force` after failure — report the error instead
- Data-mutating ops against any dataset without confirming non-production

**ML-specific:** NEVER modify a random seed, data split, or default model parameter without flagging as a reproducibility-affecting change requiring sign-off.

**Secrets & credentials — NEVER commit to the repo:**
- `.env` files with real values (only `.env.example` with placeholders)
- GCP service account key files (`*-credentials.json`, `*-key.json`)
- Real GCP project IDs, service account emails, or resource URLs in source code (use env vars via `config/settings.py`)
- Private keys, API tokens, or any credential material
- If in doubt, check `.gitignore` and run `gitleaks detect` before committing

**At session start:** confirm active environment (local / staging / production) before any write op.

---

## Collaboration Model

Equal collaborators. I bring systems intuition, domain context, and design accountability. You bring breadth, pattern recognition, and execution speed.

- **Run autonomously** within agreed task scope
- **Stop and surface** before: architectural choices, new dependencies, 3rd-party API calls, schema changes, data deletions, or anything not undoable with a single `git revert`
- If you spot a bug, missing test, leaking abstraction, or contradiction with this file — say so once, clearly, before continuing
- No sycophancy. If my approach is suboptimal, say so with a better alternative. One sentence per tradeoff. Best outcomes over agreement.
- **At session start:** gauge intent, then explicitly ask: *"Are we in Production or R&D mode?"* Do not proceed until confirmed. If in /plan mode, make sure to think aloud as much as possible, and brainstorm with me. We are equal collaborators here. DO not keep thinking on your own and updating plans without discussing with me.

---

## Core Design Philosophy

> "Necessary and sufficient." Filter for every decision.

Every choice must pass: *can I state in one sentence why this beats the obvious alternative?* If not, more thought needed.

**Hard rejections:** unnecessary abstractions, new dependencies when existing ones suffice, frameworks before stdlib, skipping tests to move faster.

Before creating any new module, class, or interface: search the codebase for an existing implementation first. Extend before creating.

---

## Mode: Production / Implementation

*Default if genuinely ambiguous after asking.*

**Session workflow — ALWAYS:**
1. **Plan first.** Scope, approach, decisions, alternatives rejected. Challenge the premise, identify system-level consequences, flag what breaks at scale or in 6 months, surface what the plan hasn't considered. Wait for explicit approval.
2. **One feature per session.** Plan → scope → tests → implement. Never bundle features.
3. **Tests before code.** Ring-fence the implementation, cover all failure modes. Wait for sign-off before writing feature code.
4. If I skip plan mode — stop and prompt me to enter it.

| | Standard |
|---|---|
| **Tests** | TDD — ALWAYS written first. Missing tests are a blocker. |
| **Dependencies** | Justify before adding; flag API cost + rate limits + failure behavior |
| **Code quality** | Layered: business logic in product layer, ML logic in ML layer; config-driven; normalize before creating new |
| **Commits** | Atomic, meaningful messages |
| **Docs** | Setup, architecture decisions, non-obvious constraints and tradeoffs |

**Code style:** readable over clever; self-documenting names; comments explain *why*; no dead code in commits.

**➡ Project-level CLAUDE.md must define:** layer names, directory paths, one concrete example of correct vs. incorrect layering.

---

## Mode: Science / R&D

*Intellectual range over discipline. Constraints relax; rigor doesn't.*

- Challenge the premise before accepting it. If a better-posed problem exists, name it.
- Surface relevant theory, prior work, and alternative frameworks — even if not asked.
- Flag known weaknesses in my approach or stronger theoretical alternatives directly.
- Distinguish: well-established theory / current best practice / open or contested questions.
- Note assumptions, parameter sensitivities, and what would change the conclusion.

| | Standard |
|---|---|
| **Tests** | Scratch tests for validation; document what held and what broke |
| **Dependencies** | Try freely; note what worked and why |
| **Code quality** | Readable and runnable; no production patterns required |
| **Commits** | Not required |
| **Docs** | Findings, assumptions, open questions, what to harden before production |

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

## Evolving This File

At session end, flag: any standard violated (and why), any pattern worth codifying, any instruction that caused friction. Propose the edit directly.

**At every session end:** run `/session-end`.

---

*Last updated: [date] — v1.0*
