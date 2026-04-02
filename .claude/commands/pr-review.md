You are a **principal engineer** reviewing this PR. Be thorough, opinionated, and direct. Flag real problems; don't nitpick for the sake of it. Your job is to catch what will hurt in production or confuse someone in 6 months.

Detect the current PR number and repo automatically:
```bash
PR_NUM=$(gh pr view --json number -q '.number')
REPO=$(gh repo view --json nameWithOwner -q '.nameWithOwner')
```

Execute steps 0-3 **in parallel** (they are independent). Then consolidate in steps 4-6.

---

## Step 0 — Diff Size Gate

```bash
DIFF_LINES=$(git diff main...HEAD | wc -l)
```

If the diff exceeds **500 lines**, pause and warn:
> This PR is [N] lines. Large PRs are hard to review thoroughly and more likely to hide bugs. Consider splitting into smaller, focused PRs.

Still proceed with the review, but note the size as a WARNING in findings.

---

## Step 1 — Static Analysis + Regression Check

Run locally and collect output:

```bash
uv run ruff check .
uv run bandit -r src/ -q
uv run pytest --tb=short -q
```

If ruff or bandit produce BLOCKER-level findings (errors, security issues), present them immediately. These must be fixed before proceeding to AI review.

If tests fail, note which tests and continue (AI review may explain why).

**Regression check:** Compare test count on this branch vs main:
```bash
BRANCH_TESTS=$(uv run pytest --collect-only -q 2>/dev/null | tail -1)
MAIN_TESTS=$(git stash -q 2>/dev/null; git checkout main -q && uv run pytest --collect-only -q 2>/dev/null | tail -1; git checkout - -q; git stash pop -q 2>/dev/null)
```

If tests were **removed** without explanation in the diff, flag as a WARNING. New code should not reduce test coverage.

If test count **increased**, verify the delta matches new test functions in the diff. A count increase that doesn't match explicit new tests may indicate unintentional fixture inclusion or silent mis-parsing (e.g., a recursive file discovery change picking up files that weren't previously included). Flag unexplained count changes as a WARNING.

---

## Step 2 — External Reviews (Copilot + Dependabot)

**2a. Request Copilot review and fetch comments:**

```bash
gh pr edit $PR_NUM --add-reviewer github/copilot
```

Wait ~30 seconds, then fetch all review comments:
```bash
# Copilot review body
gh api repos/$REPO/pulls/$PR_NUM/reviews --jq '.[] | select(.user.login == "copilot-pull-request-reviewer[bot]") | .body'

# Copilot inline comments
gh api repos/$REPO/pulls/$PR_NUM/comments --jq '.[] | select(.user.login == "copilot-pull-request-reviewer[bot]") | "**\(.path):\(.line // .original_line)** — \(.body)"'
```

If Copilot is unavailable or hasn't responded yet, note it and continue. This layer is optional.

**2b. Check Dependabot alerts:**

```bash
gh api repos/$REPO/dependabot/alerts --jq '.[] | select(.state == "open") | "[\(.security_advisory.severity)] \(.security_advisory.summary) — \(.dependency.package.name) (\(.dependency.package.ecosystem)) — \(.html_url)"'
```

If any open alerts exist, include them in the review output with severity. If the alert is relevant to this PR's changes, flag it as a WARNING.

---

## Step 3 — Claude Principal Engineer Review (run in parallel with steps 1-2)

Read:
1. `git diff main...HEAD` — full diff of all changes
2. The active sprint doc under `docs/sprints/` — hypothesis and gate criteria
3. `CLAUDE.md` — architecture, layering rules, design philosophy

Review through each lens. Check ALL of these:

**Architecture & Design:**
- Does this change align with the sprint hypothesis?
- Any layering violations? (e.g., world model importing from scoring)
- Are new modules/abstractions justified, or is this premature?
- Will this design hold at 10x scale, or is it a dead end?

**Correctness & Testing:**
- Missing tests for new or changed behavior?
- Edge cases not covered? (empty input, None values, boundary conditions)
- Are test assertions actually meaningful, or do they just check "no crash"?

**Security (OWASP lens):**
- Command injection? SQL injection? (especially raw string formatting in queries)
- Hardcoded secrets or credentials?
- Unsafe deserialization? Unvalidated input at system boundaries?

**Performance:**
- O(n^2) or worse algorithms hiding in loops?
- Unbounded queries without LIMIT?
- Missing indexes on columns used in WHERE clauses?
- Unnecessary full-table scans?

**Schema & Contracts:**
- Schema changes that could break downstream consumers?
- New fields that violate existing naming conventions?
- Type changes that affect serialization?

**Maintainability:**
- Dead code being committed?
- Duplicated logic that should be consolidated?
- What would confuse an engineer reading this 6 months from now?

For each finding, capture:
- **File:line** — exact location
- **Severity** — BLOCKER (must fix before merge) / WARNING (should fix) / NIT (style/preference)
- **Issue** — what's wrong, one sentence
- **Fix** — suggested resolution

---

## Step 4 — Present Consolidated Review

Merge findings from ALL sources into a single table, deduplicating where Claude and Copilot flagged the same issue. Credit the source(s).

| # | Finding | Severity | Source | Fix |
|---|---------|----------|--------|-----|
| ... | ... | ... | Claude / Copilot / Ruff / Bandit / Dependabot | ... |

Then:

### Static Analysis
[findings or "Clean"]

### Dependabot Alerts
[open alerts or "None"]

### Summary
- Total findings: [N] (X blockers, Y warnings, Z nits)
- Recommendation: APPROVE / REQUEST CHANGES / NEEDS DISCUSSION

---

## Step 5 — Post to GitHub

Present sign-off block:

```
HIGH PRIVILEGE ACTION — Sign-off required
Action: Post review to PR #[X]
Risk: Comments visible to anyone with repo access
Reversible: yes — delete comments via GitHub
Proceed? (yes / no / modify)
```

If approved, post a single review body (not inline comments — they error on position mismatches) via:
```bash
gh api repos/$REPO/pulls/$PR_NUM/reviews \
  -f event="COMMENT" \
  -f body="[full review body in markdown]"
```

Note: GitHub API rejects `REQUEST_CHANGES` on your own PR. Always use `COMMENT` event for self-authored PRs.

---

## Step 6 — Auto-Fix Offer

If any WARNINGs were found, offer:

> **[N] warnings found.** Want me to fix them on this branch before merge?

If the user accepts, fix all warnings, run tests to confirm green, commit, and push. Use a single commit with message: `Fix [N] review warnings: [brief list]`.
