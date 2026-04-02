Generate a PR description for the current branch. Read:

1. `git log main..HEAD` — all commits on this branch
2. `git diff main...HEAD --stat` — files changed
3. The active sprint doc under `docs/sprints/` — hypothesis, deliverables, gate criteria
4. `LEARNINGS.md` — any relevant decisions or findings from this sprint
5. `CURRENT_STATE.md` — where we are in the project

Then write a PR description with these sections:

## What we set out to do

Natural language narrative (2-3 paragraphs, PM voice) explaining:
- What hypothesis this sprint/branch was testing
- Why it matters in the context of the larger product thesis
- What the expected outcome was going in

## What actually happened

Honest account of the build:
- What went as planned
- What surprised us or required adjustment
- Any design decisions made during implementation and why
- Findings that inform future sprints

## What changed

- Bullet list of concrete deliverables (files, modules, capabilities)
- Test count and coverage summary
- Any schema or interface contracts locked

## How to verify

- Step-by-step commands to validate the work locally
- What to look for in test output
- Any manual verification steps

## Gate status

Reference the sprint doc's gate criteria. For each criterion, state PASSED/FAILED/PARTIAL with one-line evidence.

## Review status

If a PR review has been completed (via `/pr-review` or manual review), add this section. If no review yet, omit it.

- **Review source** — who/what reviewed (Claude principal engineer, Copilot, peer, etc.)
- **Summary line** — e.g., "1 blocker, 4 warnings, 3 nits"
- **Addressed in this PR** — checklist of findings fixed, with commit SHA
- **Deferred** — checklist of findings tracked for later, with issue link and target sprint. For each: one-line description, file location, and why it's safe to defer.

This section serves double duty: it's the review paper trail for the PR, and it feeds `LEARNINGS.md` at session end (review findings that change how we build are worth capturing as learnings).

## What's next

One paragraph on what this unblocks and what the next sprint will build on top of.

---

Rules:
- **Lead with the goal and outcome, not the file list.** The first thing a reader should understand is *what this PR set out to achieve* and *whether it succeeded*. Code changes are supporting evidence. This applies to production and R&D alike — only chore/fix PRs should lead with the checklist.
- Write like a PM who understands the technical details, not like a commit log.
- Be honest about what went wrong or was harder than expected. This is a learning log, not a sales pitch.
- Reference specific files, test counts, and metrics — not vague claims.
- The title/summary should convey the outcome, not just the topic. Bad: "Add fetch pipeline". Good: "Fetch pipeline: GCS ingestion with checkpointing, 102 tests green".
- Do NOT auto-create the PR. Output the description so the user can review and edit before submission.
- Format the output as a markdown block the user can copy, or offer to create the PR with sign-off.

### R&D branches (`rd/` prefix)

R&D PRs are experiments — the **finding or verdict** is the primary deliverable, code is secondary.

- **"What actually happened"** → Lead with **the verdict in bold** — one sentence answering the hypothesis. Then the evidence: what data you collected, what you expected vs found, what assumptions broke. This is the most important section.
- **"What changed"** → Include R&D artifacts (reports, inspector output, agent configs) alongside code. A table with file + why is clearer than a bullet list.
- **"What's next"** → Focus on architecture implications. A finding that changes the system design matters more than the next ticket.
