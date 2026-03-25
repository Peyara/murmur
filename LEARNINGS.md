# Murmur — Learnings & Decisions Log

Newest entry at top. Historical record of what was decided, learned, and observed each session.

For current state / resume point, see `CURRENT_STATE.md`.

---

### 2026-03-24 — Production — Sprint 0B-2: GCP provisioning + security hardlines + sandbox scripts

**Session Summary**
- Mode: Production
- Resolved prior auth blocker (new device, gcloud authenticated as samreen654@gmail.com). Installed uv, restored venv (84 tests green). Executed full GCP sandbox provisioning: 9 APIs enabled (revised list — dropped BigQuery/CloudBuild, added Compute/ArtifactRegistry), GCS bucket, audit log sink with SA permissions, Data Access audit logs enabled, 3 secrets, Cloud Run hello container, Cloud Scheduler job (every 5 min), $25 budget alert, e2-micro VM. All resources verified live. Audit logs confirmed flowing (9 files in bucket).
- Added security hardlines: .gitignore credential patterns, .env/.env.example config separation, gitleaks pre-commit hook, CLAUDE.md security rule, settings.py env var wiring.
- Created sandbox scripts: setup-sandbox.sh (idempotent, parameterized), teardown-sandbox.sh (with confirmation), sandbox-status.sh (on-demand health check). All auto-load .env.
- Branch `feat/security-hardlines-sandbox-scripts` pushed. PR not yet created — blocked on `gh auth login` on new device.
- Status: Branch pushed, PR pending.

**Decisions**

| Decision | Alternatives considered | Why rejected |
|---|---|---|
| Revised API list: drop BigQuery + CloudBuild, add Compute + ArtifactRegistry | Original 9 (with BQ + CloudBuild) | "Necessary and sufficient" — BQ not used (chose GCS sink), CloudBuild not needed for pre-built hello container. Compute needed for VM (was missing). ArtifactRegistry needed for Cloud Run image pulls. |
| .env + .gitignore + gitleaks (defense in depth) | .gitignore only; Terraform secrets | Multiple independent layers — any single layer failing doesn't expose secrets. Terraform overkill for one sandbox. |
| Shell scripts over Terraform for reproducibility | Terraform/OpenTofu; docs-only | One sandbox, ~10 resources. Terraform learning curve + state management not justified. Scripts double as bash learning material. Can graduate to Terraform later. |
| Scripts auto-load .env (SCRIPT_DIR-based) | Require `source .env &&` prefix | User would forget the prefix. Auto-loading is ergonomic and reliable. |
| sandbox-status.sh (on-demand) over monitoring agent | Persistent polling agent; GCP dashboard only | Polling agent generates its own audit logs (observer affects observed) and costs money. Dashboard requires context-switching. On-demand script is zero-cost. |
| settings.py reads env vars via os.environ.get() | python-dotenv; separate config loader | os.environ.get() is stdlib — no new dependency. Dataclass stays single source of truth. |

**CLAUDE.md Exceptions**
- No exceptions this session.

**Open Questions**
1. trigger_ref viability — sandbox is live, can now run the experiment (carried forward).
2. Parser redundant provenance logic (parser.py:165-167) — clean up (carried forward).
3. Signal normalization method — defer to Sprint 1 (carried forward).
4. EXFIL_RISK zone patterns — real GCP data now available for tuning (carried forward).
5. 2 remaining items on issue #2: EXFIL_RISK tuning (Sprint 0B), index planning (Sprint 1) (carried forward).
6. GitHub Dependabot alert (1 low severity) — check.
7. `gh auth login` — needed on new device to create PRs.

**CLAUDE.md Evolution Candidates**
1. "Scripts auto-load .env" — standard pattern for all future scripts. **watch**
2. "On-demand status scripts over persistent agents" — for sandbox observability. **watch**

---

### 2026-03-24 — Production — Sprint 0B-2: GCP sandbox provisioning plan (blocked on auth)

**Session Summary**
- Mode: Production
- Planned GCP sandbox provisioning for Sprint 0B-2. Drafted 10-step infrastructure plan: project creation, API enabling, GCS bucket, audit log sink, Data Access logs, secrets, Cloud Run, Cloud Scheduler, billing alert, e2-micro VM. Plan approved. User created GCP account (samreen654@gmail.com), billing, and murmur-sandbox project in console. No infrastructure commands executed — blocked on gcloud CLI auth (currently authenticated as shamreen.iram@lightbird.ai, not samreen654@gmail.com).
- Status: Blocked. Resume by authenticating gcloud, then execute plan steps 1-10.

**Decisions**

| Decision | Alternatives considered | Why rejected |
|---|---|---|
| us-central1 for all resources | us-east1, northamerica-northeast1 | Cheapest, broadest service availability. No data residency requirement. |
| GCS sink (not BigQuery) for audit logs | BigQuery export | GCS matches fetch.py design (file-based ingestion). Simpler. BQ adds unnecessary complexity at this stage. |
| Hello container first for Cloud Run | Custom secret-reading container from start | Avoids blocking on container build. Validates scheduler wiring first. Swap later. |
| $25 budget alert via console | gcloud billing budgets API | Console is faster for one-time setup. Billing budgets API is complex for no benefit. |
| `-sandbox` suffix on GCS bucket name | Plain `murmur-audit-logs` | Bucket names are globally unique. Suffix reduces collision risk. |
| Separate scheduler-sa service account | Default compute SA | Principle of least privilege. Dedicated SA for scheduler -> Cloud Run invocation. |

**CLAUDE.md Exceptions**
- No exceptions this session.

**Open Questions**
1. trigger_ref viability — Sprint 0B critical experiment (carried forward, still untested).
2. Parser redundant provenance logic (parser.py:165-167) — clean up in 0B-2 (carried forward).
3. Signal normalization method — defer to Sprint 1 (carried forward).
4. Sandbox activity diversity — may need manual activity generation (carried forward).
5. EXFIL_RISK zone patterns — tune with real GCP data (carried forward).
6. 2 remaining items on issue #2: EXFIL_RISK tuning (Sprint 0B), index planning (Sprint 1) (carried forward).
7. gcloud auth — need to authenticate as samreen654@gmail.com before running any provisioning commands.

**CLAUDE.md Evolution Candidates**
1. "Interactive infra provisioning as guided walkthrough" — separate browser steps from CLI steps in plans. **watch**

---

### 2026-03-23 — Production — Sprint 0B-1: dedup fix + provenance enrichment

**Session Summary**
- Mode: Production
- Built Sprint 0B-1: dedup race condition fix (ON CONFLICT DO NOTHING), provenance enrichment pipeline (`provenance_ingest.py`), CLI wiring (parse -> enrich -> insert), known_initiators.json populated. 14 new tests (84 total). 4-layer PR review (Claude + Copilot). PR #5 opened, reviewed, merged.
- Status: Complete. PR #5 merged to main.

**Decisions**

| Decision | Alternatives considered | Why rejected |
|---|---|---|
| ON CONFLICT DO NOTHING + RETURNING for dedup | Keep SELECT-then-INSERT; INSERT OR IGNORE | TOCTOU race. DuckDB uses ON CONFLICT syntax. RETURNING gives signal without extra round-trip. |
| Provenance enrichment as separate module | Extend parser; merge into dedup | Parser should be self-contained (no config deps). Dedup is about idempotency, not classification. |
| `dataclasses.replace()` for immutable enrichment | Mutate in place; create from scratch | Mutation = side effects. From-scratch loses fields. `replace()` is the standard pattern. |
| Session scope: 0B-1 only (dedup + provenance) | Full 0B; 0B-1 + 0B-2 code only | One feature per session. Fetch.py is a separate feature with own dependency. |
| BlobSource protocol for fetch.py (decided for 0B-2) | Mock GCS SDK | Protocol = clean seam + local dev mode. SDK mocks are brittle. |
| DB-based checkpoints (decided for 0B-2) | File-based | DB keeps all state in one place. File can drift. |
| Fix row-ordering test in-PR | Defer | One-line fix. Both Claude and Copilot flagged it independently. |

**CLAUDE.md Exceptions**
- No exceptions this session.

**Open Questions**
1. trigger_ref viability — Sprint 0B critical experiment (carried forward).
2. Parser redundant provenance logic (parser.py:165-167) — simplify in 0B-2.
3. Signal normalization method — defer to Sprint 1 (carried forward).
4. Sandbox activity diversity (carried forward).
5. EXFIL_RISK patterns — tune with real GCP data (carried forward).
6. 2 remaining items on issue #2: EXFIL_RISK tuning (Sprint 0B), index planning (Sprint 1). Dedup race now FIXED.

**CLAUDE.md Evolution Candidates**
1. "Review findings convergence as validation" — when multiple reviewers flag same issue, fix in-PR not defer. **watch**
2. "Enrichment as a pipeline step pattern" — parse -> enrich -> insert is clean and reusable. **watch** for Sprint 1.

---

### 2026-03-23 — Production — Sprint 0A review follow-ups (fix branch)

**Session Summary**
- Mode: Production
- Addressed 4 of 7 Sprint 0A review follow-ups from issue #2 on `fix/sprint-0a-review-followups` branch. Fixed mutable default arg (`parser.py`), documented SHA truncation rationale (`dedup.py`), wrapped CLI connections in try/finally (`cli.py`), added debug logging for unmapped GCP methods (`parser.py`). PR #4 reviewed (0 findings), merged. Codified fix branch standard in peyara-standards (PR #1, merged). Commented on issue #2 referencing PR #4.
- Status: Complete. Ready for Sprint 0B.

**Decisions**

| Decision | Alternatives considered | Why rejected |
|---|---|---|
| Fix branch for review follow-ups, not direct to main | Direct to main; bundle with Sprint 0B | Direct-to-main violates gated workflow. Bundling mixes concerns. |
| 4 items in one commit | One commit per fix | All small, related, from same review. Single atomic commit cleaner. |
| `logger.debug` not `logger.warning` for unmapped methods | warning, info | Unmapped methods expected in normal operation. Debug is correct severity. |
| Codify fix branch standard in peyara-standards | Murmur only; no codification | Generalizable pattern. peyara-standards is canonical source via symlink. |
| Leave issue #2 open with comment | Close entirely | 3 of 7 items still unresolved. |

**CLAUDE.md Exceptions**
- No exceptions this session.

**Open Questions**
1. trigger_ref viability — Sprint 0B critical experiment (carried forward).
2. EXFIL_RISK patterns — prefix-based approach vs real GCP naming (carried forward).
3. Dedup strategy — INSERT OR IGNORE vs upsert (carried forward).
4. Peyara-standards repo structure — is `peyara/CLAUDE.md` the right path or should it be root?

**CLAUDE.md Evolution Candidates**
1. "Review follow-ups on fix branches" — **done** (codified in peyara-standards v1.4).
2. "Single commit for small related fixes from same review" — **watch**.
3. "Symlinked peyara-standards as source of truth" — **watch** (document when second project joins).

**Late-session Additions**
- User flagged that safety sign-off block was being skipped in favor of informal questions. Saved feedback memory (`feedback_safety_signoff.md`). No CLAUDE.md change needed — rules are clear, behavior drifted.
- User established hard rule: never push directly to main (except session-end handoff files). Codified in peyara-standards v1.5 (PR #2). Saved feedback memory (`feedback_never_push_main.md`).

---

### 2026-03-23 — Production — Sprint 0A PR review, merge, and close

**Session Summary**
- Mode: Production
- Ran 4-layer PR review on PR #1 (static analysis, Copilot [unavailable], Claude principal engineer review). Found 1 blocker + 4 warnings + 3 nits. Fixed blocker (.DS_Store). Created sprint review issue #2 with 7 follow-up items. Updated PR notes with review status. Updated pr-notes skill. Merged PR #1 to main (squash).
- Status: Complete. Sprint 0A merged. Ready for Sprint 0B.

**Decisions**

| Decision | Alternatives considered | Why rejected |
|---|---|---|
| COMMENT review (not REQUEST_CHANGES) | REQUEST_CHANGES | GitHub rejects requesting changes on own PR |
| Single review body, not inline diff comments | Inline per-finding | GitHub position-based comments errored (422). Single body is reliable. |
| Sprint review issue (#2) with checkboxes | Individual issues per finding; no tracking | Individual too granular for 7 small items. No tracking = write-only review comments. |
| Squash merge for sprint branches | Regular merge (preserve 9 commits) | 9 commits are implementation steps, not independently meaningful. Clean main history. |
| Review status as standard section in pr-notes skill | Keep review separate from PR notes | Review findings are part of "what happened" — PR description incomplete without them. |

**CLAUDE.md Exceptions**
- "One feature per session" — session covered review + fix + issue + learnings + skill update + merge. All part of one workflow (closing Sprint 0A). One-off.
- "Tests before code" — .DS_Store fix is a .gitignore edit, not code. One-off.

**Open Questions**
1. trigger_ref viability — Sprint 0B critical experiment.
2. EXFIL_RISK patterns — will prefix-based approach work with real GCP bucket naming?
3. Dedup strategy — INSERT OR IGNORE sufficient, or need upsert for event correction?
4. Copilot reviewer unavailable on repo — worth enabling?

**CLAUDE.md Evolution Candidates**
1. "PR review → sprint review issue → LEARNINGS.md" as standard sprint close — **promote**
2. Squash merge as default for sprint branches — **watch**
3. Self-review limitation note in pr-review skill — **promote** to skill update

---

### 2026-03-23 — Production — Sprint 0A build + PR review

**Session Summary**
- Mode: Production
- Built Sprint 0A foundation data pipeline: schema, parser, dedup, CLI. TDD throughout. 71 tests green.
- PR #1 submitted, reviewed (Claude principal engineer, 4-layer), blocker fixed, merged prep complete.
- Sprint review issue #2 created with 7 follow-up items for Sprint 0B/1.

**Implementation Findings**

| Finding | Impact | Action |
|---|---|---|
| EXFIL_RISK zone is resource-path-derived, not action-type-derived | No GCP method maps directly to EXFIL_RISK — parser checks bucket name prefixes + configurable patterns | Patterns need tuning with real GCP data in Sprint 0B |
| 14 GCP method patterns map to 13 action types | IAM_SET_POLICY has 2 sources, IAM_IMPERSONATE has 2 — parser uses ordered substring matching | More specific patterns checked first to avoid mis-classification |
| Hatchling + `src/` layout requires explicit package config | `[tool.hatch.build.targets.wheel] packages = ["src", "config"]` needed in pyproject.toml | Note for any future Peyara projects using same layout |

**PR Review Findings**

| Finding | Severity | Disposition |
|---|---|---|
| `.DS_Store` committed — macOS binary tracked in VCS | BLOCKER | Fixed in `8588940` |
| SELECT-then-INSERT race in dedup under concurrent ingestion | WARNING | Deferred — safe at single-process scope. Fix with `INSERT OR IGNORE` when concurrency arrives (#2) |
| `_floor_to_window` default arg captured at import time | WARNING | Deferred — settings effectively constant now. Quick fix in Sprint 0B (#2) |
| SHA-256 truncated to 128 bits without documentation | WARNING | Deferred — collision risk negligible at scale. Document rationale in Sprint 0B (#2) |
| `conn.close()` not reached on unexpected exceptions in CLI | WARNING | Deferred — wrap in `try/finally` in Sprint 0B (#2) |
| Unknown GCP methods silently fall back to DATA zone | NIT | Add logging when fallback hits, Sprint 0B (#2) |
| No indexes beyond primary keys on events table | NIT | Plan indexes alongside Sprint 1 windowing queries (#2) |

**Process Learnings**
- PR review as a sprint gate works well — caught a real blocker (.DS_Store) and surfaced 6 items that would have been invisible debt.
- Creating a sprint review issue (#2) with checkboxes gives follow-up items a home. Without it, PR review comments are write-only — nobody goes back to check them.
- `pr-notes` skill updated to include a "Review status" section as standard. Review findings that change how we build should flow into LEARNINGS.md.

**Open Questions**
1. trigger_ref viability — still the Sprint 0B critical experiment.
2. EXFIL_RISK patterns — will current prefix-based approach work with real GCP bucket naming conventions?
3. Dedup strategy — is `INSERT OR IGNORE` sufficient or do we need upsert semantics for event correction?

---

### 2026-03-22 — R&D — Session handoff setup

**Late addition:** Established session handoff mechanism.

- `CURRENT_STATE.md` — snapshot resume point, overwritten each session end. Answers: "what sprint, what's blocked, what files to read, what to do next." ~20 lines.
- `LEARNINGS.md` (this file, renamed from DECISIONS.md) — historical append-only log. Decisions, findings, open questions, evolution candidates.
- SessionStart hook — reminds Claude to read CURRENT_STATE.md and active sprint doc at session start.
- session-end protocol updated to include CURRENT_STATE.md update as a step.

These do NOT overlap. CURRENT_STATE.md points to LEARNINGS.md for history; LEARNINGS.md points to CURRENT_STATE.md for current state.

---

### 2026-03-22 — R&D — MVP plan critique, revised scope, project documentation setup

**Session Summary**
- Mode: R&D
- Reviewed and critiqued original MVP plan (murmur_platform_vision.docx + murmur_v0_mvp.docx). Identified 6 critical bugs and 10 major issues. Brainstormed revised MVP scope, causal phasing, and UI vision. Produced full project documentation.
- Built: CLAUDE.md project context + workflow protocols, PostToolUse hook, docs/mvp_strategy.md, 4 sprint specs (sprint_00-03), UI concept doc (Pulse + Flow Map + Lineage), post-MVP roadmap. Memory files for future sessions.
- Status: Complete. Ready to begin Sprint 0 in next session.

**Decisions**

| Decision | Alternatives considered | Why rejected |
|---|---|---|
| Defer Track B (RL/LLM adversarial sim) to post-MVP; replace with parameterized attack generator | Keep full Track B in MVP; Defer entirely with no replacement | Full Track B is a standalone research project premature without validated signals. No replacement means circular validation. Parameterized generator covers strategy diversity in 3-4 days. |
| Phase 2 (attack robustness) before Phase 3 (provenance) | Provenance first; Interleave them | If physics signals don't generalize, provenance on broken signals is wasted. Attack corpus feeds provenance testing. |
| sigma_relative / EMA as side exploration, not MVP-critical | Include in MVP; Exclude entirely | EMA has cold-start deadlock. Core signals carry the load. Try post-MVP, integrate if it adds value. |
| FastAPI + React + D3.js for dashboard (not Streamlit) | Streamlit + CSS; Decide later | Investor demo needs animated Pulse + Flow Map views requiring canvas/SVG. Streamlit can't do this. |
| UI as parallel Sprint 4 (from Sprint 1 gate) | UI last; UI interspersed | Parallel allows scaffold with mock data, progressive integration. |
| Coverage as confidence modifier, not score multiplier | Keep original amplify formula; Remove entirely | Amplifying on low coverage creates FP. Removing loses info. Confidence modifier preserves signal without distortion. |
| Incident discount conditional on provenance | Blanket 0.7; No discount | Blanket rewards attackers in incident chaos. No discount penalizes responders. Conditional is correct. |
| Normalize fusion signals before weighting | Raw weights | Signals have different scales. Raw weights meaningless without normalization. |
| 6 scenarios in Sprint 1, expand to 18 in Sprint 3 | Full 18 from start | If signals misbehave, 18 scenarios all need fixing. Start small, validate, expand. |
| Provenance layer in own directory src/provenance/ | Under src/world/ (original) | Violates plan's own 5-layer architecture. |

**CLAUDE.md Exceptions**
- "Plan first, wait for approval" — wrote plan before brainstorming. User corrected. Behavior adjusted. Already addressed in CLAUDE.md update.
- "One feature per session" — session covered plan + docs + config setup. Justified for R&D session 0.

**Open Questions**
1. trigger_ref viability: does GCP propagate Cloud Scheduler execution IDs into triggered action audit logs?
2. Signal normalization method: z-score or [0,1]? Decide when real distributions observed.
3. Sandbox activity diversity: will murmur-sandbox produce enough cross-zone events?
4. docx/pdf conversion pipeline for final deliverables.
5. Hook activation may need /hooks reload or session restart.

**CLAUDE.md Evolution Candidates**
1. "Hypothesis-driven phasing" as R&D pattern — watch
2. "Sprint docs as living documents" — watch
3. Persistent mode field in project CLAUDE.md — watch
