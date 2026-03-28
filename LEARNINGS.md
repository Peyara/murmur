# Murmur — Learnings & Decisions Log

Newest entry at top. Historical record of what was decided, learned, and observed each session.

For current state / resume point, see `CURRENT_STATE.md`.

---

### 2026-03-28 — Production — Mini session: deploy maintainer service (Workflow 2)

**Session Summary**
- Mode: Production (mini session)
- Deployed Workflow 2 (maintainer) — separate Cloud Run service + SA, hourly scheduler trigger
- Generates SECRET (AddSecretVersion), IDENTITY (GenerateAccessToken), CONTROL (SetIamPolicy x2) events hourly
- PR #14 merged. Maintainer live and accumulating.

**Decisions**

| Decision | Alternatives considered | Why rejected |
|---|---|---|
| Separate maintainer service + SA | Add endpoint to existing worker | Need distinct actor for multi-actor baseline |
| GenerateAccessToken for IDENTITY zone | CreateServiceAccountKey + DeleteServiceAccountKey | Org policy blocks key creation (`constraints/iam.disableServiceAccountKeyCreation`) |
| IAM binding toggle (add + remove) for CONTROL zone | Permanent IAM changes | Idempotent, no drift |

**Findings**

| Finding | Impact | Action |
|---|---|---|
| Org policy blocks SA key creation in sandbox | Can't use CreateKey/DeleteKey for IDENTITY zone events | Adapted to GenerateAccessToken. May affect Sprint 1B attack scenarios — check if S01 needs adaptation. |
| Protobuf repeated fields don't support Python list operations | `policy.bindings.append(Binding(...))` fails | Use `.add()` method and set fields individually |
| Secret versions accumulate (~720/month from maintainer) | No cost but unbounded growth | Consider cleanup logic if needed later |

**CLAUDE.md Exceptions**
- "Tests before code" — no tests for deploy script/Flask app. One-off, validated by manual invocation.
- "Plan first" — informal plan in conversation. Mini session, small scope.

**Open Questions**
1. Org policy vs Sprint 1B attack scenarios — does S01 (key creation) need adaptation?
2. Update `known_initiators.json` with `maintenance-sa` before correlator runs on new data?
3. Secret version cleanup strategy — needed or leave indefinite?

---

### 2026-03-27 — Session-end meta-findings (Session C)

**CLAUDE.md Exceptions**
- "One feature per session" — bundled inspection + fixes + design discussion. R&D session, one-off.
- "Tests before code" — tests written alongside for small targeted fixes. R&D mode, one-off.
- "Plan first" — fixes executed without formal plan-approve. Agreed during brainstorm, small scope, one-off.

**Process Improvements**
- PR review caught a real bug (#3: `--sample` mis-parsing non-audit files). Test count changes should always be investigated, not just accepted.
- Silent configuration failures are production risks. The `service_worker_map` empty warning prevented a class of "everything looks fine but nothing works" bugs.

**CLAUDE.md Evolution Candidates**
- "Pipeline config must fail loudly when misconfigured" → **promote** (general principle)
- "Absence of expected metadata is an anomaly signal" → **watch** (may be too domain-specific)
- "PR review: investigate test count changes" → **promote** (generalizable)

**Design Decisions for Session D**
- Zone flux matrix hydration: tiered confidence (Cold/Warm/Calibrated) as primary mechanism
- Zero-baseline zone pairs: novelty scoring only, not sigma_coarse
- Deploy Workflow 2 (maintainer) before or alongside Session D for richer baseline
- No synthetic activity spike — sparsity is the signal, attack injection validates it

---

### 2026-03-27 — R&D — Session C: 24h real data inspection

**Session Summary**
- Mode: R&D + local
- Pulled 5 days of real GCS audit logs (3,415 entries, 166 files, 4.8MB) to local snapshot.
- Ran inspector (zero-knowledge structure discovery) and ingestion pipeline in parallel on real data.
- All 3 parsers at 100% parse rate. Correlation at 99.7% (1,509/1,513 worker events). 7 actors discovered.
- Full RD report: `docs/rd_reports/2026-03-27_session_c_24h_inspection.md`

**Decisions**

| Decision | Alternatives considered | Why rejected |
|---|---|---|
| Keep all 5 days of data (including deploy noise) | Filter to 24h window only | Deploy noise is a better stress test — validates layered scoring handles messy reality |
| LocalFetcher recursive by default | Flatten downloads / create adapter | Recursive is the correct behavior — GCS sink always uses nested paths |
| Don't parse stderr/varlog | Add parsers for all formats | No actor identity, no audit signal. Application-level logs. Low detection value. |
| Prioritize delegation chain extraction | Defer to Sprint 2+ | Delegation chain is a first-class anomaly signal for stolen credentials — needed for Sprint 1B attack injection |

**Findings**

| Finding | Impact | Action |
|---|---|---|
| `service_worker_map` silently empties without env vars | Pipeline produces 0 correlations with no error. Production risk. | Add startup validation. Priority 1 fix. |
| Delegation chain is an anomaly signal | Absence of `serverless-robot-prod` in worker events = stolen credential | Extract to CanonicalEvent. Priority 2. |
| 7 actors, not 6 | `service-agent-manager@system.gserviceaccount.com` does IAM_SET_POLICY | Add to infrastructure allow-list. |
| EXFIL_RISK zone completely empty | No baseline for exfil detection | Design decision: first-ever zone event = maximum novelty by definition? |
| system_event logs contain deploy metadata | 9 events with deployer identity, image hash, config changes | Add system_event parser for deploy detection. Priority 3. |
| Zone flux 57% sparse, dominated by SECRET<->DATA | Worker creates 2 zone pairs. Human creates 17. | Correct by design — sparse baseline means transitions are novel. |
| Inspector independently found scheduler->audit join key | Validates our correlation approach from first principles | Confidence boost. |
| Human user-agent has 113 variants vs worker's 1 | callerSuppliedUserAgent alone distinguishes human from automated | Free signal for actor fingerprinting. |

**Learning Loop**

1. **Assumed:** 6 actors, all formats parseable, env vars always available at runtime.
2. **Observed:** 7 actors, 3 additional log formats, silent failure without env vars.
3. **Broke:** Actor count assumption (minor). Silent correlation failure (major). All-formats-parseable (minor — correct rejection).
4. **Adapted:** Added startup validation to fix list. Delegation chain promoted from metadata to signal. system_event parser added to roadmap.
5. **Principles:** (a) Any configuration-dependent pipeline step must fail loudly when misconfigured, not silently degrade. (b) Absence of expected metadata (delegation chain) is itself an anomaly signal — model what should be present, not just what is present.
6. **Next time:** Source `.env` as part of the analysis script, not as a manual step. Consider a `murmur doctor` command that validates configuration completeness.

**Open Questions**
1. 25 medium-confidence correlations (0.50-0.89) — edge cases or systematic issue?
2. EXFIL_RISK baseline: synthesize during attack injection, or treat first-ever zone event as maximum novelty?
3. `ReplaceService` -> ACTION_MAP: add as `COMPUTE_UPDATE` or leave as OTHER?

---

### 2026-03-27 — Production — Sprint 1A Sessions A+B complete, 24h observation clock running

**Session-end meta-findings (covers both Sessions A+B)**

**CLAUDE.md Exceptions**
- "One feature per session" — bundled Sprint 1A foundation. One-off.
- "No real GCP IDs in source" — violated in Session B, caught in review, scrubbed. PreToolUse hook added.
- "Tests before code" — hydration tests written alongside. One-off.
- "PR review: independent opinion before Copilot" — drifted on PR #12. Must read diff first, form own view.

**Process Improvements**
- PreToolUse hook added to `~/.claude/settings.json` — scans git push diffs for sensitive patterns (emails, project IDs, API keys, SA keys, tokens). Blocks push if found.
- PR review must: read full diff → form opinion → THEN compare with Copilot. Not triage Copilot first.

**CLAUDE.md Evolution Candidates**
- "Never commit sensitive identifiers — use env var placeholders + PreToolUse hook" → **promote**
- "PR review: form independent opinion before reading Copilot" → **promote**
- "Baseline design must be observation-first, not invariant-first" → **watch** (already in Peyara standards)

---

### 2026-03-26 — Production — Sprint 1A Session B: activity generator deployed, correlation validated on real data

**Session Summary**
- Mode: Production
- Deployed real Cloud Run worker (reads secret + GCS input, writes GCS output) replacing hello-world container. Added hourly health check + daily cleanup scheduler jobs. Ran ad-hoc human activity.
- Validated end-to-end correlation on real GCP audit logs: 8/8 worker events correlated with confidence 0.9998-1.0. Causal chain Scheduler→CloudRun→AuditEvents proven working.
- 24h observation clock started: 2026-03-26T20:30 UTC.

**Decisions**

| Decision | Alternatives considered | Why rejected |
|---|---|---|
| Realistic baseline only — no manufactured invariant triggers | Hourly SA key creation to exercise INV_002 | Confirmation bias. Key creation belongs in Sprint 1B attack injection, not baseline. |
| Single worker SA for all endpoints (/, /health, /cleanup) | Separate SAs per endpoint | Realistic — health checks and cleanup run as the service, not as a different identity. |
| 3 endpoints on 1 Cloud Run service | 3 separate Cloud Run services | Simpler. Same SA, same permissions. Scheduler jobs target different URL paths. |

**Findings**

| Finding | Impact | Action |
|---|---|---|
| Correlation works on real data: 0.9998-1.0 confidence | Core thesis validated — causal chain reconstruction is feasible | 24h observation clock started |
| GCS sink batches hourly, ~15 min delivery delay after hour close | Worst-case detection latency is ~75 min | Fine for MVP signal validation. Production real-time needs Cloud Logging API (streaming). Track as architecture decision for post-MVP. |
| Hydration validator reports mismatch when deploy noise dominates | Human activity (deploy, manual commands) outnumbered 2 worker invocations | Self-resolves as worker invocations accumulate. Validator is working correctly — it needs more data. |
| Cloud Build deploy generates ~40 Docker-related audit events | One-time deploy noise. Introduces new SA (`serverless-robot-prod`) and methods (`Docker-*`) not in ACTION_MAP | These map to OTHER/DATA currently. Consider adding Docker-* to ACTION_MAP or excluding build artifacts. |
| Cloud Build API had to be enabled + default SA needed storage.admin | `--source` deploy requires Cloud Build + Artifact Registry permissions | One-time setup cost. Document in provisioning script. |
| `known_initiators.json` needed both real and fixture SAs | Updating to real SA broke fixture-based tests | Keep both entries. Test fixtures use placeholder SA, production uses real SA. |
| Worker produces SECRET→DATA→DATA→DATA per invocation | Only 2 zone types in regular flux. Zone diversity comes from human ad-hoc + future attacks. | Correct by design — realistic baseline is stable, not diverse. Diversity = anomaly signal. |
| `storage.objects.list` appears in worker flow (from `list_blobs()`) | GCS_LIST action now exercised in real data — Sprint 1A ACTION_MAP expansion was needed | Validated the ACTION_MAP expansion decision. |

**Open Questions**
1. Detection latency: GCS sink (batch) vs Cloud Logging API (streaming) — post-MVP architecture decision
2. Docker-* audit methods from Cloud Build — add to ACTION_MAP or filter?
3. `storage.buckets.getStorageLayout` appears in human commands — unmapped method, maps to OTHER
4. `google.logging.v2.LoggingServiceV2.ListLogEntries` — logging API read events from gcloud CLI, unmapped

---

### 2026-03-26 — Production — Sprint 1A Session A: ingestion foundation + hydration design

**Session Summary**
- Mode: Production
- Built multi-format ingestion pipeline: 3 parsers (audit, scheduler, Cloud Run), temporal-identity correlator, multi-prefix fetch pipeline, infrastructure tagging. 210 tests green (was 121).
- GCS sink expanded to capture all 3 log types. ACTION_MAP expanded from 13→22 entries.
- Identified cold start problem in correlator → designed hydration period as first-class Murmur concept.
- Key insight: Murmur is a self-learning system. The hydration period is the "observe before hypothesize" principle at the system level.

**Decisions**

| Decision | Alternatives considered | Why rejected |
|---|---|---|
| Expand GCS sink (not API fetcher) | Cloud Logging API fetcher | API adds runtime dep, pagination, rate limits. Sink reuses existing pipeline. |
| Scheduler/Cloud Run logs as correlation metadata, not CanonicalEvents | Parse into CanonicalEvents with new zone types | No natural actor-target-zone mapping; forces invented ActionTypes |
| Per-format wrapper parsers with common interface | Single integrated parser; registry dispatcher | 3 structurally different formats. Wrapper is independently testable. |
| Correlation confidence as composite (identity 0.4, URL 0.3, ambiguity 0.2, temporal 0.1) | Temporal-only; binary match/no-match | Temporal proximity is weakest signal — structural matches are deterministic, timing is noisy |
| Tag infrastructure, don't filter | Filter at ingestion; ignore | Filtering is lossy — need data for learning and auditing |
| Hydration period as design feature, not limitation | Skip observation, deploy with static rules | Static rules produce false positives. Self-learning requires observation period. |
| URL-match priority over temporal proximity in linker | Closest-in-time regardless of URL | PR review finding: contradicted own confidence model weights. |
| Bundle Session A in one PR | Split into multiple PRs | One-off — cohesive foundation, all changes tightly coupled. |

**Findings**

| Finding | Impact | Action |
|---|---|---|
| Cold start is narrow: only identity mapping (service→SA) needs config or learning | Correlator hop 1 (sched→cloudrun) is fully deterministic from first event | Built validate_service_worker_map() to verify config against observations |
| Hydration period is a first-class design concept | Investor-facing: time-to-value = deploy(1h) + hydrate(3x cadence) + baseline(24h) | Documented in CLAUDE.md and mvp_strategy.md |
| Murmur is self-learning: murmurs of today power Murmur of tomorrow | Architecture principle, not just implementation detail | Framed as continuous self-validation, not one-time configuration |
| PR review caught linker contradicting confidence model | URL-match was tie-breaker, should have been primary | Fixed before merge. Pattern: review catches design-intent drift. |

**CLAUDE.md Exceptions**
- "One feature per session" — bundled foundation. One-off.
- "Tests before code" — hydration tests written alongside, not strictly before. One-off (concept emerged from discussion).

**Open Questions**
1. Auto-discovery of service_worker_map (Sprint 2-3) — how many observation cycles needed for confident auto-mapping?
2. Self-learning parser (Sprint 2-3) — config-driven parser from inspector+agent pipeline. Issue to be created.
3. Correlation confidence weights need calibration against real latency distributions (Session C)
4. Schema migration for existing DuckDB files — track for pre-production (Sprint 3)
5. EXFIL_RISK pattern tuning — still pending from issue #2
6. known_initiators.json needs real scheduler SA from deployed environment

**CLAUDE.md Evolution Candidates**
- "Review warnings fixed in-PR before merge" — **watch**
- "PR notes lead with goal/outcome narrative" — **watch** (validated in pr-notes skill)

---

### 2026-03-26 — R&D — trigger_ref experiment + inspector + standards v2.0

**Session Summary**
- Mode: R&D
- Ran the critical trigger_ref experiment: no native per-execution correlation ID in GCP audit logs. Temporal-identity correlation across 3 log streams is the mechanism (MEDIUM confidence). Built cloud-agnostic log inspector + custom Claude Code agent. Cascaded 5 broken assumptions across all sprint specs + MVP strategy. Codified 3 new R&D disciplines in peyara-standards v2.0.
- Status: Sprint 0B COMPLETE. PR #10 merged. All docs updated. Ready for Sprint 1.

**Decisions**

| Decision | Alternatives considered | Why rejected |
|---|---|---|
| Multi-log ingestion (3 streams) | Audit-log-only + API on-demand; audit only | API adds runtime dep. Audit-only misses scheduler + Cloud Run signals. |
| Temporal-identity correlation for trigger_ref | Native field; trace-based; IP-based | Field doesn't exist. Trace doesn't propagate (1/80). IP varies. |
| Cloud-agnostic inspector (statistical) | Hardcoded GCP field checklist | Fragile, repeats "model before observe" mistake. |
| Custom Claude Code agent for interpretation | Anthropic SDK; slash command | SDK = unnecessary dep. Slash command = wrong isolation. Agent = right pattern. |
| Observation-first validation | Hypothesis-confirming (design tests for invariants) | Confirmation bias. Build landscapes, not test cases. |
| Peyara-standards v2.0 | Keep findings project-specific | Principles generalize: observe first, no bias, learning loops. |

**CLAUDE.md Exceptions**
- "One feature per session" — R&D cascade, each piece followed from prior discovery. One-off.
- "Tests before code" — Inspector is an R&D discovery tool. Inline validation tests added after. One-off.
- "Never push to main" — Doc-only handoff files, per convention. One-off.

**Self-Reflection Findings (Learning Loop)**

Six specific findings abstracted into reusable principles:

| # | Finding | Principle |
|---|---|---|
| 1 | Should have looked at real logs before writing fixtures | **Ground truth before modeling.** Sample real data before fixtures/schemas. |
| 2 | Parse rate was misleading (100% rate, 66% → OTHER) | **Measure what matters.** Metrics must map to actual outcomes. |
| 3 | Inspector should have preceded parser | **Discovery before implementation.** Tools to see before tools to act. |
| 4 | Sandbox doesn't produce diverse signals | **Validate test environment against hypothesis.** Don't defer "generate data" as fallback. |
| 5 | Multi-log constraint enables trace-based correlation | **Constraints contain upgrade paths.** Ask what it enables, not just prevents. |
| 6 | Agent pattern discovered accidentally | **Match reasoning layer to context.** Dev-time → agent. Runtime → SDK. |

**Meta-principle:** Observe → hypothesize → model. We inverted it (model → hypothesize → observe) and paid for it.

**Confirmation bias catch:** We designed a synthetic workload that produces exactly the patterns our invariants check for — circular validation. Reframed Sprint 1 to observation-first: deploy workload, run inspector, observe landscape, THEN evaluate invariants against reality. Include unstructured human activity. Name blind spots.

**Findings**

| Finding | Impact | Action |
|---|---|---|
| trigger_ref (metadata field) does not exist in real GCP audit logs | Entire provenance enrichment pipeline built against phantom field | Temporal-identity correlation is the design. Sprint 1 builds correlate.py. |
| Scheduler + Cloud Run invocations are NOT audit logs | 3 separate log streams with different structures, not in GCS sink | Multi-log ingestion required. Sprint 1 ingestion foundation block. |
| GCP has 3 log formats (protoPayload, jsonPayload, httpRequest) | Parser handles only protoPayload | Multi-format dispatcher needed in Sprint 1. |
| 66% of real audit log entries map to OTHER | Zone flux matrix skewed, invariants won't fire on real data | ACTION_MAP expansion is prerequisite for Sprint 1 hypothesis. |
| Logging SA meta-logs are 31% of entries | Infrastructure noise dominates flux matrix | Keep in dataset, system must handle gracefully. |
| root_trigger_id exists on Compute Engine ops | Proof GCP CAN propagate trigger IDs, just not for Scheduler | Notes trace-based correlation as an upgrade path. |
| Sandbox is quiet after provisioning | Sprint 1B validation is vacuously true without injected activity | Day 0 activity generator added to Sprint 1. |

**Open Questions**
1. Multi-format parser architecture (dispatcher vs single module) — Sprint 1 design decision.
2. correlation_confidence as a CanonicalEvent field — Sprint 1 design decision.
3. Sink expansion vs Cloud Logging API fetcher — Sprint 1 design decision.
4. EXFIL_RISK pattern tuning — still pending from issue #2.
5. inspect-interpret agent permissionMode — verify acceptEdits resolves Bash access.

**CLAUDE.md Evolution Candidates**
1. "Observe before hypothesize" — **done** (peyara-standards v2.0).
2. "No confirmation bias" — **done** (peyara-standards v2.0).
3. "Learning loop" — **done** (peyara-standards v2.0).
4. "Session-start assumption check" — **done** (peyara-standards v2.0).
5. "PR notes lead with goal/outcome" — **done** (pr-notes skill).
6. "RD reports as lab notebooks" — **watch**.
7. "Custom agents for dev-time reasoning" — **watch**.
8. "Objectivity over agreement" — **done** (peyara-standards, collaboration section). Challenge own proposals, stress-test convergence, no echo chambers.

---

### 2026-03-25 — Production — GCSFetcher + CLI consolidation (PR #9)

**Session Summary**
- Mode: Production
- Built GCSFetcher + SingleFileFetcher, unified all 4 CLI ingest paths (`--sample`, `--file`, `--local-dir`, `--gcs-bucket`) through `fetch_and_ingest()`, eliminated `_ingest_file` duplication. Fixed 3 deferred PR #7 nits. PR #9 opened, 4-layer review (0 blockers, 3 warnings, 3 nits), all warnings fixed in-PR. 118 tests green (was 103).
- Status: Complete. PR #9 open, all findings resolved. Ready to merge + trigger_ref experiment next session.

**Decisions**

| Decision | Alternatives considered | Why rejected |
|---|---|---|
| Route all CLI ingest paths through `fetch_and_ingest` | Keep `_ingest_file` for `--file`; route only new paths | Partial consolidation leaves duplication. Audit log files are KB-range. |
| `SingleFileFetcher` as BlobSource wrapper | `LocalFetcher(parent_dir)` with filter; call `_ingest_content` directly | Parent dir ingests all files. Direct call bypasses checkpointing. |
| Lazy import for google.cloud.storage | Module-level import; try/except optional import | Module-level breaks `import src.ingest.fetch` without GCS SDK — LocalFetcher unusable in dev/test. |
| File mtime in `--file` source_id | No mtime (dedup only); hash of file contents | No mtime blocks re-ingestion after edits. Hash requires reading entire file upfront. |
| `click.UsageError` for mutual exclusivity | `click.echo` + `sys.exit(1)` | sys.exit bypasses Click error formatting. UsageError is idiomatic. |
| `click.Path(file_okay=False)` on `--local-dir` | Rely on `LocalFetcher` ValueError | Click should catch at boundary — cleaner errors, fails before DB connection. |
| Patch `google.cloud.storage.Client` in tests | Patch module; `patch.dict(sys.modules)` | Namespace package has no `storage` attribute until imported. `.Client` works. |
| Fix all warnings in-PR (single commit) | Defer to fix branch | All small, related to this PR. No reason to defer. |

**CLAUDE.md Exceptions**
- No exceptions this session.

**Findings**

| Finding | Impact | Action |
|---|---|---|
| Module-level import of optional dep breaks unrelated code paths | GCSFetcher import would make LocalFetcher unusable without GCS SDK | Fixed — lazy import inside `__init__`. Pattern: always lazy-import optional heavy dependencies. |
| `google.cloud` is a namespace package — can't patch it directly | `patch("google.cloud.storage")` raises `AttributeError` | Fixed — patch `google.cloud.storage.Client` instead. |
| `gh pr edit` blocked by Projects Classic deprecation | GraphQL mutation fails with exit code 1 | Workaround: use REST API `gh api repos/.../pulls/N -X PATCH -F body=@file`. |
| Routing `--file` through checkpointing changes re-run behavior | Old: re-parse + dedup. New: checkpoint blocks re-processing | Fixed — include file mtime in source_id so changed files bypass checkpoint. |
| All 103 existing tests passed without modification after consolidation | Validates BlobSource abstraction is behavior-preserving | No action needed — good design signal. |

**Open Questions**
1. trigger_ref viability — Sprint 0B critical experiment, pipeline ready (carried forward).
2. Signal normalization method — defer to Sprint 1 (carried forward).
3. EXFIL_RISK zone patterns — tune with real GCP data (carried forward).
4. 2 remaining items on issue #2: EXFIL_RISK tuning (Sprint 0B), index planning (Sprint 1) (carried forward).
5. Stale .pyc causing phantom test failures — watch for recurrence (carried forward).
6. `gh pr edit` blocked by Projects Classic deprecation — REST API workaround works.

**CLAUDE.md Evolution Candidates**
1. "REST API fallback when `gh pr edit` fails on Projects Classic deprecation" — **watch**.
2. "Lazy imports for optional heavy dependencies" — **watch** (pattern emerged twice: GCS SDK).

---

### 2026-03-24 — Production — Fix deferred review nits PR #6 + PR #7 (PR #8)

**Session Summary**
- Mode: Production
- Fixed 9 deferred review nits from PRs #6 and #7 on `fix/pr6-pr7-review-nits` branch. 7 shell script/env fixes, 1 LocalFetcher `is_dir()` validation + test, 1 parser provenance cleanup (removed redundant CLOUD_SCHEDULER assumption). PR #8 created, reviewed (0 blockers, 0 warnings, 2 nits), squash merged. 103 tests green.
- Status: Complete. All deferred nits resolved. Main up to date.

**Decisions**

| Decision | Alternatives considered | Why rejected |
|---|---|---|
| Fix 8 of 11 nits now, defer 3 to GCSFetcher | Fix all 11; defer all | 3 nits (click.Path, mutual exclusivity, _ingest_content duplication) naturally belong to GCSFetcher CLI work. Fixing now creates throwaway code. |
| Include parser provenance cleanup in fix branch | Keep separate; defer again | Carried 4 sessions. Small change, same scope. No reason to keep deferring. |
| Remove CLOUD_SCHEDULER assumption, keep WEAK level | Remove both; keep both | WEAK is correct (trigger_ref = weak provenance). CLOUD_SCHEDULER is wrong (could be Cloud Build). Enrichment handles classification. |
| Remove unwired env vars from .env.example | Wire into scripts; leave as docs | Scripts derive via gcloud. Wiring adds complexity. Misleading examples confuse users. |
| Two-step bucket deletion (objects then bucket) | Single rm -r; add --force | `gcloud storage rm -r` can fail to delete the bucket itself. Two-step is reliable. |
| Single commit for all 9 fixes | One per fix | All from same review, related scope. Single atomic commit cleaner. |

**CLAUDE.md Exceptions**
- No exceptions this session.

**Findings**

| Finding | Impact | Action |
|---|---|---|
| Copilot didn't respond to PR #8 review request within 30s | Review proceeded without Copilot layer | Non-blocking — Copilot is optional layer. May respond later. |
| Audit log check logic duplicated across setup + status scripts | Maintenance burden if check logic changes | Acceptable for independent scripts — NIT, no action. |
| Parser tests didn't assert provenance_source at all | Made CLOUD_SCHEDULER removal safe — no test updates needed | Good: enrichment tests cover source classification thoroughly. |

**Open Questions**
1. trigger_ref viability — Sprint 0B critical experiment, pipeline ready (carried forward).
2. Signal normalization method — defer to Sprint 1 (carried forward).
3. EXFIL_RISK zone patterns — tune with real GCP data (carried forward).
4. 2 remaining items on issue #2: EXFIL_RISK tuning (Sprint 0B), index planning (Sprint 1) (carried forward).
5. 3 deferred PR #7 nits — click.Path constraints, mutual exclusivity, _ingest_content duplication — fix with GCSFetcher.
6. Stale .pyc causing phantom test failures — watch for recurrence (carried forward).

**CLAUDE.md Evolution Candidates**
1. "Batch related nits into single fix branch + single commit" — **watch**.

---

### 2026-03-24 — Production — Sprint 0B-3: fetch pipeline + checkpointing (PR #7)

**Session Summary**
- Mode: Production
- Merged PR #6 (security hardlines, from prior session). Built, reviewed, and merged PR #7: fetch pipeline with BlobSource protocol, LocalFetcher, DuckDB checkpointing, `--local-dir` CLI option, `ingest_checkpoints` schema table. Dismissed Dependabot alert #1 (Pygments ReDoS, no fix available). 4-layer PR review: 3 warnings fixed, 4 nits deferred. 102 tests green (up from 84).
- Status: Complete. Both PRs merged. Main up to date.

**Decisions**

| Decision | Alternatives considered | Why rejected |
|---|---|---|
| BlobSource as Protocol (structural typing) | ABC; mock GCS SDK directly | ABC adds unnecessary inheritance. SDK mocks are brittle. Protocol gives clean seam + substitutability. |
| LocalFetcher first, defer GCSFetcher | Build both together; skip local | Building both adds dep before needed. Skipping local means no test-friendly implementation. |
| DB-based checkpoints (`ingest_checkpoints` table) | File-based; no checkpoint | File can drift from DB. No checkpoint = wasteful re-ingestion. DB keeps all state in one place. |
| Lexicographic blob ordering for checkpoint | Timestamp-based; sequence number | GCS sink blob names sort lexicographically by date. No extra parsing needed. |
| Accept both `.json` and `.jsonl` in LocalFetcher | `.json` only; configurable | `.json` only skips existing fixtures. Configurable is over-engineering. |
| `--local-dir` as new CLI option (not replacing `--file`) | Replace `--file`; add `--gcs-bucket` now | Replacing breaks existing usage. `--gcs-bucket` requires new dep — separate concern. |
| Dismiss Dependabot alert (not fix) | Pin Pygments; ignore | No fixed version exists. Dismiss with rationale is correct. |
| Keep feature branches after merge | Delete with `--delete-branch` | User preference — learnings on each branch worth revisiting. |

**CLAUDE.md Exceptions**
- No exceptions this session.

**Findings**

| Finding | Impact | Action |
|---|---|---|
| Stale `.pyc` caused phantom test failure | `test_all_10_tables_created` appeared to fail despite correct source. Clearing `__pycache__` resolved. | Watch — if recurs, add cache cleanup to pre-test workflow. |
| `known_initiators` loaded but unused in `--local-dir` CLI path | Wasted work, confusing code | Fixed in review — moved loading into only branches that use `_ingest_file`. |
| `_ingest_content` (fetch.py) duplicates `_ingest_file` (cli.py) | Two parse→enrich→insert loops | Deferred — consolidate when `--file` deprecated in favor of `--local-dir`. |
| Copilot and Claude converge again | 1 of 6 Copilot comments matched Claude finding (`.jsonl` extension) | Pattern holds from PR #6. Convergence = high confidence signal. |

**Open Questions**
1. trigger_ref viability — fetch pipeline ready, run experiment next session (carried forward).
2. Parser redundant provenance logic (parser.py:165-167) — clean up (carried forward).
3. Signal normalization method — defer to Sprint 1 (carried forward).
4. EXFIL_RISK zone patterns — real GCP data now available for tuning (carried forward).
5. 2 remaining items on issue #2: EXFIL_RISK tuning (Sprint 0B), index planning (Sprint 1) (carried forward).
6. 4 deferred review nits from PR #7 — fix when adding `--gcs-bucket`.
7. 7 deferred Copilot nits from PR #6 — fix on `fix/` branch.
8. Stale `.pyc` causing phantom test failures — watch for recurrence.

**CLAUDE.md Evolution Candidates**
1. "Clear `__pycache__` when schema/test renames cause phantom failures" — **watch**.

---

### 2026-03-24 — Production — PR #6 merge + session handoff

**Session Summary**
- Mode: Production
- Generated PR description for PR #6 (`feat/security-hardlines-sandbox-scripts`). Merged PR #6 to main (squash merge, feature branch deleted). Resolved merge conflicts in session handoff files.
- Status: Complete. PR #6 merged. Main branch up to date.

**Decisions**

| Decision | Alternatives considered | Why rejected |
|---|---|---|
| Squash merge for PR #6 | Regular merge (preserve 2 commits) | 2 commits are one logical unit (initial + review fixes). Clean main history. Consistent with Sprint 0A merge precedent. |
| Stash-then-merge to handle dirty working tree | Commit handoff files first; checkout --force | Committing would create noise. Force checkout loses changes. Stash is the standard pattern. |
| Resolve stash conflicts with `--theirs` (main's version) | Manual conflict resolution | Handoff files are overwritten by `/session-end` anyway. No content to preserve. |

**CLAUDE.md Exceptions**
- No exceptions this session.

**Open Questions**
1. trigger_ref viability — sandbox is live, can now run the experiment (carried forward).
2. Parser redundant provenance logic (parser.py:165-167) — clean up (carried forward).
3. Signal normalization method — defer to Sprint 1 (carried forward).
4. EXFIL_RISK zone patterns — real GCP data now available for tuning (carried forward).
5. 2 remaining items on issue #2: EXFIL_RISK tuning (Sprint 0B), index planning (Sprint 1) (carried forward).
6. GitHub Dependabot alert (1 low severity) — check (carried forward).
7. 7 remaining Copilot nits on PR #6 — fix on `fix/` branch before next sprint (carried forward).

**CLAUDE.md Evolution Candidates**
- No candidates this session.

---

### 2026-03-24 — Production — Sprint 0B-2: PR review, skill updates, peyara-standards install

**Session Summary**
- Mode: Production
- Unblocked `gh` CLI auth (was already authenticated as Peyara on this device). Created PR #6 for security hardlines + sandbox scripts branch. Ran 4-layer PR review (Claude principal engineer + Copilot). Claude found 2 warnings, 12 nits. Copilot generated 11 inline comments. After deduplication: 4 unique warnings, 9 nits. Fixed all 4 warnings on branch (--no-allow-unauthenticated, mktemp+trap, gitleaks extend default rules, .pre-commit-config.yaml). Pushed fix commit.
- Updated `/pr-review` skill in peyara-standards: added principal engineer persona, Copilot comment fetching, Dependabot alert check, diff size gate (>500 lines), regression check (test count vs main), auto-fix offer. Created PR #3, merged.
- Ran `install.sh` on this device — all peyara-standards slash commands now symlinked to `~/.claude/commands/` (`/pr-review`, `/pr-notes`, `/session-end`, `/update-readme`).
- Status: PR #6 open with review fixes applied. 7 Copilot nits remaining (non-blocking). Ready to merge.

**Decisions**

| Decision | Alternatives considered | Why rejected |
|---|---|---|
| `--no-allow-unauthenticated` for Cloud Run | Keep `--allow-unauthenticated`; add comment explaining | Undermines the OIDC provenance experiment (trigger_ref). Auth required so scheduler identity appears in audit logs. |
| `mktemp` + `trap` for IAM policy temp file | Keep fixed `/tmp/` path; pipe directly | Fixed path risks clobbering/exposure on concurrent runs. Piping complex JSON through set-iam-policy is fragile. mktemp+trap is the standard pattern. |
| `[extend] useDefault = true` in gitleaks config | Add explicit `[[rules]]`; leave as-is | Without extend or rules, gitleaks scans nothing. Extend is one line and gets all default rules. |
| `.pre-commit-config.yaml` for gitleaks hook | Document manual `gitleaks detect` command; defer | Hook is defense-in-depth. Without it, gitleaks config exists but never runs automatically. |
| Fix warnings before merge, defer nits | Fix everything; defer everything | Warnings are real gaps (public endpoint, no scanning rules). Nits are cosmetic. Splitting keeps PR review focused. |
| Squash merge for peyara-standards PR | Regular merge | Single-file change, one logical unit. Clean history. |

**CLAUDE.md Exceptions**
- No exceptions this session.

**Findings**

| Finding | Impact | Action |
|---|---|---|
| `install.sh` had never been run on this device | All custom slash commands (`/pr-review`, `/pr-notes`, `/session-end`) were unavailable | Ran install.sh — now symlinked. Add to new-device setup checklist. |
| Copilot and Claude converge on same findings | 4 of 11 Copilot comments matched Claude warnings exactly | Convergence = high confidence. Deduplication in consolidated review table is the right pattern. |
| Copilot reviews are available ~30s after requesting | Can fetch inline comments via `gh api` | Built into updated `/pr-review` skill. |
| gitleaks pre-commit hook ran on first commit after adding `.pre-commit-config.yaml` | Confirmed working — scanned and found 0 leaks | Defense-in-depth layer is live. |

**Open Questions**
1. trigger_ref viability — sandbox is live, can now run the experiment (carried forward).
2. Parser redundant provenance logic (parser.py:165-167) — clean up (carried forward).
3. Signal normalization method — defer to Sprint 1 (carried forward).
4. EXFIL_RISK zone patterns — real GCP data now available for tuning (carried forward).
5. 2 remaining items on issue #2: EXFIL_RISK tuning (Sprint 0B), index planning (Sprint 1) (carried forward).
6. GitHub Dependabot alert (1 low severity) — check.
7. 7 remaining Copilot nits on PR #6 — fix before or after merge.

**CLAUDE.md Evolution Candidates**
1. "Run `install.sh` on new device" — add to project onboarding checklist. **promote**
2. "Deduplicate review findings across sources" — built into `/pr-review` skill. **done**

---

### 2026-03-24 — Production — Sprint 0B-2: GCP sandbox provisioning plan (blocked on auth)

**Session Summary**
- Mode: Production
- Planned GCP sandbox provisioning for Sprint 0B-2. Drafted 10-step infrastructure plan: project creation, API enabling, GCS bucket, audit log sink, Data Access logs, secrets, Cloud Run, Cloud Scheduler, billing alert, e2-micro VM. Plan approved. User created GCP account (<operator-email>), billing, and murmur-sandbox project in console. No infrastructure commands executed — blocked on gcloud CLI auth (currently authenticated as <operator-corp-email>, not <operator-email>).
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
7. gcloud auth — need to authenticate as <operator-email> before running any provisioning commands.

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
