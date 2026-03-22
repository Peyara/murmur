# Murmur — Learnings & Decisions Log

Newest entry at top. Historical record of what was decided, learned, and observed each session.

For current state / resume point, see `CURRENT_STATE.md`.

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
