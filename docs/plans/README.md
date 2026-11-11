# Plans

One file per piece of work. Status values: Draft, Approved, In progress, Built (awaiting review), Done, Dropped.

| Plan | Status | Branch | Notes |
|---|---|---|---|
| [migration.md](migration.md) | Approved | | Order of work to a first end-to-end release. Phase 0 done. |
| [electrical-core.md](electrical-core.md) | Approved | `phase-1-electrical-core` | Phase 1. Ready for a building session. Reference prototype: `electrical-core-prototype.py`. |

## How work is split between sessions

Planning sessions (the more capable, more expensive model) review code, make design decisions and write plans. Building sessions (a cheaper model) carry out one approved plan each. A plan is written so that the building session has no design decision left to make.

A plan is ready to hand off when its status is Approved, every question in it is answered, and it has a section "Brief for the building session" that lists the files to create, the functions with their inputs and outputs, the tests with expected values, what is out of scope, and what "finished" means. New plans start from [TEMPLATE.md](TEMPLATE.md).

## Starting a building session

Open a new session with the cactus folder connected and paste this, with the plan file name filled in:

```
Use the agent-pair-dev skill, work loop. In the cactus repo read AGENTS.md,
docs/plans/README.md and docs/plans/<plan>.md, then build that plan and nothing else.
Work on the branch named in the plan. Follow the section "Rules for a building session"
in docs/plans/README.md. When finished, fill in the plan's "Build report" and stop.
```

## Rules for a building session

1. Read `AGENTS.md`, this file and the plan before touching anything. Check `git status` and `git log` first; if the repo is not in the state the plan's header describes, stop and say so.
2. Build only what the plan's brief lists. Anything else that looks wrong goes into the build report as a note, not into the code.
3. Write the tests in the brief first, see them fail, then write the code.
4. Do not make design decisions. If the plan is silent, contradicts the code, or a test's expected value cannot be met, stop work on that item, record the question under "Questions back to planning" in the build report, and carry on with items that do not depend on it. Do not change an expected value or loosen a tolerance to make a test pass.
5. Do not copy code from IPV_Workbench.
6. Before finishing, run `uv sync`, `uv run pytest`, `uv run ruff check` and `uv run ruff format --check`, and paste the summary lines into the build report. Say which checks were not run and why.
7. Update `AGENTS.md` (Layout, and the test name next to each invariant the work now guards) in the same change.
8. Commit to the plan's branch only. Do not merge to `main` and do not push unless Justin asks.
9. Set the plan's status to "Built (awaiting review)", update the table above, and add one dated line to the state log in the claude.ai Project brief `claude/dev-context.md`.

## Review and close

Justin, or a planning session, reads the build report, answers any questions back, and either marks the plan Done and merges the branch, or returns it with notes. A decision record is written at that point if the ADR test in `AGENTS.md` is met. A plan that came back with open questions gets them answered in the plan itself, dated, before a second building session starts.
