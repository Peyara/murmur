You are closing this session. Execute the following steps in order. Do not skip any.

---

## Step 1 — Session Summary

Write a concise summary of this session:
- Mode: Production / R&D
- What was built, explored, or decided
- Where things stand at close (complete / partial / blocked)

---

## Step 2 — Decisions Log

For every non-trivial decision made this session, capture:

| Decision | Alternatives considered | Why rejected |
|---|---|---|
| | | |

A decision is non-trivial if: it involved a tradeoff, it could have gone a different way, or a future engineer would benefit from knowing why this path was chosen.

---

## Step 3 — CLAUDE.md Exceptions

List every instance where a CLAUDE.md standard was not followed.
For each: name the standard, state why it was not followed, and recommend: **promote exception to CLAUDE.md / one-off / revert before next session**.

If none: state explicitly "No exceptions this session."

---

## Step 4 — Open Questions

List unresolved questions, ambiguities, or deferred decisions that the next session should pick up.
If none: state explicitly "No open questions."

---

## Step 5 — CLAUDE.md Evolution Candidates

List any pattern, preference, or standard that emerged this session that is not yet in CLAUDE.md but should be considered.
For each: state the observation and recommend **promote / watch / discard**.

If none: state explicitly "No candidates this session."

---

## Step 6 — Write to LEARNINGS.md

Append the full output of Steps 1–5 to `LEARNINGS.md` under a new entry:

```
### [TODAY'S DATE] — [MODE] — [ONE LINE SUMMARY]
```

Newest entry at the top, below the header.
If `LEARNINGS.md` does not exist, create it with the header:

```markdown
# [Project Name] — Learnings & Decisions Log

Newest entry at top. Historical record of what was decided, learned, and observed each session.

For current state / resume point, see `CURRENT_STATE.md`.

---
```

---

## Step 6.5 — Peyara Standards Audit

Review the full session for patterns worth standardizing across all Peyara projects. For each candidate, classify:

- **SKILL**: Repeatable action sequence (like /pr-notes, /update-readme)
- **HOOK**: Automated behavior on a trigger (like PostToolUse)
- **GLOBAL_CLAUDE**: Directive that applies to all projects (like think-aloud)
- **TEMPLATE**: Reusable project scaffold file
- **NONE**: Project-specific, not worth generalizing

For each non-NONE candidate, present:

```
STANDARDS CANDIDATE — Sign-off required
What: [description]
Type: [SKILL / HOOK / GLOBAL_CLAUDE / TEMPLATE]
Where: [file path in peyara-standards repo]
Proposed content: [summary or full text]
Why: [what makes this generalizable beyond this project]
Approve? (yes / no / modify)
```

If approved: write to `~/Desktop/Peyara/peyara-standards/`, commit, and push.
If no candidates: state "No standards candidates this session."

---

## Step 7 — Update CURRENT_STATE.md

Overwrite `CURRENT_STATE.md` with a fresh snapshot (~20-30 lines):
- Active Sprint — name and status
- Last Completed Milestone — what and when
- Open Blockers / Questions — numbered list
- Files to Read for Context — pointers to sprint doc, strategy doc, learnings
- What To Do Next — concrete next action for the next session

If `CURRENT_STATE.md` does not exist, create it.

---

## Step 8 — Flag CLAUDE.md Edits

If any Evolution Candidates from Step 5 are recommended **promote**, output a proposed diff to CLAUDE.md now.
Wait for explicit approval before applying.
