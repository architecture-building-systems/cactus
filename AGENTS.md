# CACTUS

Comprehensive Assessment and Computational Toolset for Urban Solar. A Python library for designing and simulating building-integrated photovoltaic arrays: irradiance on cells, cell IV curves from a single-diode model, electrical assembly of cells into modules, strings and arrays with mismatch, and yield and carbon analysis. Users are Justin McCarty and students at ETH Zurich (Architecture and Building Systems). Remote: `architecture-building-systems/cactus`. Distribution name `solar-cactus`, import name `cactus`. Not yet released.

Related repo: `IPV_Workbench` is the PhD-era predecessor. It is frozen and archived. It is a source of ideas and input data, not of code to copy: it has known errors (see the two review documents listed below).

## Where context lives

| What | Where |
|---|---|
| Identity, commands, layout, invariants, Don't list | this file |
| Decisions, with alternatives and consequences | `docs/decisions/NNN-*.md` |
| Feature plans, their status, and how a plan is handed to a session to build | `docs/plans/` (index and hand-off procedure in `docs/plans/README.md`) |
| Conventions for one area of code | `.claude/rules/<area>.md` (none yet; add when a convention exists in the code) |
| How Justin works, environment quirks, state log | claude.ai Project "CACTUS", `claude/dev-context.md` |
| Review of IPV_Workbench and of the `26_shade_happens` study | claude.ai Project "CACTUS", `claude/ipv-workbench-review-2026-11-10.md` and `claude/shade-happens-review-2026-11-10.md` |
| Open items | GitHub issues |

A fact has one home. Other places link to it.

## Commands

Python 3.13, managed with uv.

```
uv sync                 # create the environment and install dependencies
uv run pytest           # tests
uv run ruff check       # lint
uv run ruff format      # format
```

When working from a shell that is not Justin's Mac (for example a Linux sandbox), do not create `.venv/` inside the repo. Set `UV_PROJECT_ENVIRONMENT` to a path outside it.

## Layout

```
src/cactus/                    the library
src/cactus/electrical/curve.py IVCurve (voltage on a current grid); current_grid, series, parallel, bypass, max_power_point
src/cactus/electrical/cell.py  CellParameters, module-to-cell conversion, cell_current_grid, cell curves (pvlib De Soto + Bishop)
tests/                         pytest tests (tests/electrical/ for the electrical core)
docs/decisions/                decision records
docs/plans/                    plans
```

Pipeline so far: module datasheet values -> `cell_parameters_from_module` -> `cell_current_grid` -> `cell_curves` -> `bypass`/`series`/`parallel` -> `max_power_point`.

The planned modules and the order they are built in are in `docs/plans/migration.md`. Update this section when a module lands.

## Invariants

These must hold once the electrical core exists. Each gets a test when the code that it constrains is written; add the test name next to the invariant at that point.

1. Bypass diodes act on the group of cells they span. Voltage is clipped per group inside the series sum, never on the summed voltage of a module or string. Test: `tests/electrical/test_curve.py::test_bypass_per_group`.
2. No silent clamping or extrapolation when curves are combined. If one curve does not cover the current (series) or voltage (parallel) range needed, the code raises an error. Every current grid contains 0 A, and the grid for a set of cells is sized to their largest photocurrent (`cell_current_grid`), so open-circuit voltage and low-light power are not lost between grid points. Tests: `tests/electrical/test_curve.py::test_series_needs_shared_range`, `::test_parallel_needs_shared_range`, `::test_combined_grids_contain_zero`, `tests/electrical/test_cell.py::test_grid_spanning_zero_must_contain_zero`, `::test_low_light_accuracy`.
3. Identity cases: N identical cells in series under uniform conditions give N times the cell voltage at every current; N identical strings in parallel give N times the string current at every voltage. Tests: `tests/electrical/test_curve.py::test_series_identity`, `::test_parallel_identity`, `::test_parallel_identity_full_curve`.
4. The power of any assembly never exceeds the sum of the maximum powers of its parts. Test: `tests/electrical/test_curve.py::test_power_bound`.
5. Solar position is computed with time-zone-aware timestamps.
6. The cell temperature range of any lookup or interpolation covers the temperatures that the temperature model can produce. Out-of-range input raises an error; it is not clamped silently.
7. One description of the electrical topology drives both the electrical solve and the count of components used for carbon and cost.
8. Datasheet parameters given for a whole module are converted to one cell before a cell curve is computed, and the reverse breakdown voltage applies per cell. A lit cell's curve must reach its breakdown region (IPV_Workbench applied the -15 V breakdown to the whole module, which limited each cell to about -0.2 V and hid most mismatch loss). Test: `tests/electrical/test_cell.py::test_cell_reaches_breakdown`.

## Contracts

None yet. When Grasshopper or any other front end exchanges files with the library, the file format is defined here (or linked from here) and both sides change together.

## Releases

Not defined yet.

## Architecture Decision Records

Write a record in `docs/decisions/` only if the decision (a) chooses between real alternatives that someone could revisit, (b) constrains future work, or (c) changes a contract. Everything else goes in the commit message. Use the next free number. When a record replaces an older one, update the older record's status. Format:

```
# ADR-NNN: Short title
**Date:** YYYY-MM-DD
**Status:** Proposed | Accepted | Superseded by ADR-NNN

## Context
## Decision
## Consequences        (end with "Rejected alternatives:" and why)
## Implementation      (optional, dated)
```

## Don't

- Don't copy code from `IPV_Workbench` without checking it against the review documents. Rebuild and test instead.
- Don't try to reproduce `IPV_Workbench` numbers. Justin chose a clean break (2026-11-10); corrected results are expected to differ.
- Don't exchange data with front ends as Python pickles.
- Don't put strings of unequal module count in parallel, or modules of different current class in series, without the library warning about it.
- Don't replace a wrong input with a default and continue. Raise an error.
- Don't build a current grid with `np.linspace` or with a fixed range in amps. Use `cell_current_grid` for cells and `current_grid` elsewhere.
- Don't hardcode personal absolute paths.
- Don't edit before a plan is agreed. Present a plan with numbered questions and wait.
- Don't commit unless Justin asks.
