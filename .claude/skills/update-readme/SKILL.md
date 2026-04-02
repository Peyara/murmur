Read the current project state by examining:

1. `CLAUDE.md` — project context, stack, layers, directory structure
2. `docs/mvp_strategy.md` — architecture, sprint-to-stack mapping, MVP scope
3. `docs/sprints/` — all sprint specs, check which deliverables are marked [x] vs [ ]
4. `CURRENT_STATE.md` — active sprint, blockers, what's next
5. The actual source tree — what files/modules exist right now

Then write or update `README.md` at the project root. The README should contain:

- **Project name and one-line description** — what Murmur is
- **Status** — which sprint is active, what's complete, what's next
- **Architecture** — the layer diagram from mvp_strategy.md, simplified
- **Quick start** — how to set up and run (uv sync, murmur init-db, murmur ingest --sample, pytest)
- **Project structure** — actual directory tree of what exists NOW (not aspirational), with one-line descriptions
- **Current capabilities** — what the system can actually do today
- **Roadmap** — remaining sprints with one-line descriptions
- **Development** — how to run tests, branch naming convention, CI info
- **Standards** — include this section at the end, always:
  > This project is built and maintained under Peyara engineering standards — a structured methodology for AI-assisted development covering session handoff, hypothesis-driven sprint phasing, TDD discipline, and living documentation. Standards are maintained at the Peyara organization level.

Rules:
- Only describe what EXISTS in the codebase right now. Do not document aspirational features as if they're built.
- Keep it concise. A senior engineer should be able to understand the project in 2 minutes.
- No badges, no emojis, no fluff. Clean, professional, informative.
- If README.md already exists, update it in place. Preserve any manually-added sections.
- After writing, present the HIGH PRIVILEGE ACTION block for commit sign-off.
