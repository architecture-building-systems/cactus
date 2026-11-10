# Migration from IPV_Workbench to CACTUS

Status: Approved (phase order approved by Justin 2026-11-10; phase 0 done on branch `bootstrap`; each later phase has its own plan)
Date: 2026-11-10. Code checked at IPV_Workbench `v1_dev` 2c5486b and cactus `main` cc3e927.

Detail behind the findings is in the claude.ai Project "CACTUS": `claude/ipv-workbench-review-2026-11-10.md` and `claude/shade-happens-review-2026-11-10.md`.

## 1. What the code says

1. IPV_Workbench is about 7,000 lines with no tests or packaging. Roughly half is dead or unreachable.
2. Its cell curves cannot go into reverse bias. The -15 V breakdown voltage is applied to the whole module's parameters and the result is divided by the number of cells in series, so each cell stops at about -0.2 V. A shaded cell then costs almost nothing. Checked with device D001 and the Workbench's own `circuits.py`: 72 cells in 3 diode groups, one cell at 200 W/m2, gives 221 W of an unshaded 225 W, where per-cell breakdown gives 147 W. This is the largest electrical error found.
2a. Its electrical assembly clips bypass voltage on the summed module voltage, not per diode group. With per-cell breakdown and 24 cells per group this changes the result by under 1 % (146.3 W against 147.4 W); the first toy case, with 20 synthetic cells per group, showed 5.5 %.
3. A corrected `circuits.py` was written in an earlier session but cannot be found. It has to be rebuilt.
4. Cell temperature is capped at 40 degC by the lookup range, solar position is computed in UTC, and the thin-film path appears broken.
5. In the last real use (`26_shade_happens`), the Workbench was used only up to module IV curves. Topology was built in ad-hoc scripts from Excel grid maps, with strings of unequal length in parallel and a cross-tied model that had almost no effect.
6. Students use Rhino 8, which runs CPython 3.9. CACTUS targets Python 3.13, so Grasshopper components cannot import the library; they exchange files with it.

## 2. Critique

Risks, highest first:

1. The electrical core is rebuilt from principles with no surviving reference implementation. Mitigation: tests written first from analytic identity cases, and a comparison against an independent tool where one installs on Python 3.13.
2. There is no reference case. Mitigation: build three (section 3.4) before trusting any annual number.
3. End-to-end as the first release is a large scope for one developer. Mitigation: each phase ends in something runnable and tested; front-end work comes after the library can run a case from files.
4. The Grasshopper panelizer is a binary file that has not been reviewed. Its plugin dependencies and output structure are known only from the pickle it writes.

Cut: reproducing Workbench numbers; the `old_solver` and `old_sample` code; the config file that is rewritten on disk to hold state; per-hour storage of full IV curves for every module.

Defer: a custom design GUI; a panelizer that does not need Rhino; inverter efficiency curves and DC wiring loss; tree-carbon utilities.

Keep (rebuild and test, do not copy): single-diode cell curves via pvlib (De Soto parameters, Bishop reverse bias); the series and parallel assembly approach from PVMismatch (BSD-3, attribution retained); the Radiance 2-phase command sequence; effective irradiance (front cover loss, Martin-Ruiz); the device table and the cell, diode and submodule maps; the simple PVWatts-style model as a cross-check.

## 3. Design

### 3.1 Shape

A headless library that runs a case from files, with front ends attached through a written file format. Grasshopper is the first front end and writes the layout file. Nothing in the library imports Rhino.

### 3.2 Topology as data

One description of the circuit: a tree of series and parallel connections, with cross ties, bypass and blocking diodes, and converter placement. The electrical solve and the component count for carbon and cost both read it. The library warns on parallel strings of unequal module count, series modules of different current class, and strings outside a converter's voltage window.

### 3.3 Data

Arrays (modules x time x cells) in place of nested dicts. A layout file in an open, versioned format in place of the pickle. Every result set records the library version and inputs.

### 3.4 Reference cases

- R1, cell and module: analytic identities and single-module partial shading with hand-checkable diode behaviour.
- R2, small array: a synthetic array of about a dozen modules with one shaded region, small enough to reason about every string.
- R3, facade: the `26_shade_happens` building, re-run from its stored Radiance results and panelizer export, with corrected topology.

Rejected alternatives: a full custom design GUI first (rebuilds 3D geometry authoring, most work for least research value); staying Grasshopper-only (core stays untestable and tied to Rhino); fixing IPV_Workbench in place (Justin chose a clean break).

## 4. Phased plan

| Phase | Work | Files | Tests |
|---|---|---|---|
| 0 | Bootstrap: AGENTS.md, CLAUDE.md, ADR-000, plans, pyproject for uv and Python 3.13, empty package | repo root, `docs/` | package imports |
| 1 | Electrical core: cell IV curve; series assembly with per-group bypass and fold kept; parallel assembly; maximum power point | `src/cactus/electrical/` | invariants 1 to 4; R1 |
| 2 | Topology as data, checks, converters | `src/cactus/topology/` | invariant 7; R2 |
| 3 | Data model, layout file format, one-off reader for the legacy panelizer pickle | `src/cactus/model/`, `src/cactus/io/` | round trip of a legacy export |
| 4 | Effective irradiance and cell temperature; sensor-to-cell mapping; R3 re-run from stored Radiance results | `src/cactus/irradiance/`, `src/cactus/thermal/` | invariants 5 and 6; R3 against the simple model |
| 5 | Radiance 2-phase runner | `src/cactus/irradiance/` | one surface against stored results |
| 6 | Command-line entry point; Grasshopper components that write the layout file and call it | `src/cactus/cli.py`, `grasshopper/` | end-to-end run by a student on a new building |
| 7 | Analysis layer: yield, carbon, payback, figures | `src/cactus/analysis/` | R3 tables |
| 8 | Panelizer without Rhino for flat rectangular surfaces | later plan | |

First release is end-to-end, so it follows phase 6. Module names are proposals and are fixed in each phase's own plan.

## 5. Cross-repo asks

- IPV_Workbench: archive on GitHub with a README line pointing to cactus (Justin, needed).
- `26_shade_happens`: read-only source of R3 inputs (needed). Nothing is written there.

## 6. ADR outline

To be written when the work they describe lands:

- ADR-001: headless library with a file contract; Grasshopper as first front end; no Rhino import in the library.
- ADR-002: clean break from IPV_Workbench; no numerical compatibility.
- ADR-003: topology as one description shared by the electrical solve and component counting.

## 7. Decisions and questions

Decisions (Justin, 2026-11-10):

- The corrected `circuits.py` is lost; rebuild it.
- Rhino is acceptable as the design front end for now because students have licences; the Rhino requirement should go away later.
- Published Workbench results do not need to stay reproducible.
- No reference case exists; develop one.
- First release is end-to-end.
- CACTUS is one repo; IPV_Workbench is frozen and archived.
- Python 3.13.
- The SBE25 paper is published and is not revisited. Its in-house converter carbon figures are specific to that paper and are not carried over.
- Series-parallel means series strings connected in parallel.
- A corrected re-run of `26_shade_happens` is the first end-to-end validation case, using its existing geometry and Radiance results.

- Students use Rhino 8.
- No measured module IV data is available; phase 1 is validated against analytic cases and pvlib.
- Distribution name is `solar-cactus` (`cactus` is taken on PyPI); import name stays `cactus`.
- Phase order approved. Development is done by separate building sessions from plans prepared here (see `README.md` in this folder).

Open questions: none. Questions for each phase are in that phase's plan.
