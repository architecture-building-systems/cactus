# ADR-000: Working method

**Date:** 2026-11-10
**Status:** Accepted

## Context

CACTUS replaces IPV_Workbench, which had about 7,000 lines of Python, no tests, no packaging and no record of why things were built the way they were. A review on 2026-11-10 found errors that changed published numbers. Development is by Justin McCarty working with Claude as pair programmer, across sessions that do not share memory.

## Decision

Context is kept in layers, each with one job:

- `AGENTS.md`: identity, commands, layout, invariants, contracts, Don't list. `CLAUDE.md` contains only `@AGENTS.md`.
- `.claude/rules/<area>.md`: conventions for one area of the code, added only when the convention exists in the code.
- `docs/decisions/`: decision records, written only when a decision chooses between real alternatives, constrains future work, or changes a contract.
- `docs/plans/<slug>.md`: one plan per feature, with its status in the header and Justin's choices recorded with dates.
- claude.ai Project "CACTUS", `claude/dev-context.md`: how Justin works, environment quirks and a short dated state log.
- GitHub issues: every open item.

Each session reads the layers it needs before planning, presents a plan with numbered questions, waits for approval, builds, verifies, and records. The code is trusted over the documents; when they disagree, the document is fixed in the same change. A physical invariant in `AGENTS.md` is not considered in force until a test guards it.

## Consequences

A new session can start from the repo and the Project brief without the previous conversation. Decisions can be revisited with their reasons in view. The cost is a small amount of writing per feature, and the layers go stale if they are not updated with the code.

Rejected alternatives: a single growing notes file (facts drift and duplicate); relying on commit history alone (does not record alternatives that were rejected); relying on chat memory (not shared between sessions or people).
