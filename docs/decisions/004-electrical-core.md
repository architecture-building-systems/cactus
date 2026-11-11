# ADR-004: Electrical core — IV curves as voltage on a current grid

**Date:** 2026-11-11
**Status:** Accepted

## Context

IPV_Workbench ran pvlib's Bishop model on whole-module parameters with a -15 V breakdown and divided voltage by the number of cells, so each cell stopped at about -0.2 V and never reached breakdown. It combined curves with `np.interp`, which repeats end values outside a curve and hid that error. A module with one cell at 200 W/m2 gave 221 W of 225 W; the corrected model gives 147.6 W. The phase 1 review then found that a current grid fixed in amps (-3 to 9 A, 600 points) lost accuracy as irradiance fell (2.5 % at 100 W/m2, 5.5 % at 30), and that a fully dark cell's voltage at 0 A was undefined (-11.1 V where about 0 V is right). Plan: `docs/plans/electrical-core.md`, sections 3 and 10.

## Decision

1. Every element (cell, bypassed group, module, string, array) is an `IVCurve`: voltage sampled on an increasing current grid, voltage never increasing with current. Series adds voltages at equal current; parallel adds currents at equal voltage.
2. Datasheet parameters for a whole module are converted to one cell before a curve is computed (photocurrent, saturation current and the Isc temperature coefficient divided by N_p; series and shunt resistance multiplied by N_p / N_s; `a_ref` divided by N_s). Breakdown voltage, factor and exponent are per cell and are not scaled. Defaults: -15 V, 0.002, 3.28.
3. A cell curve is sampled with pvlib `bishop88` (De Soto parameters) from 0.97 of the breakdown voltage to a forward voltage that reaches the lowest current requested. For currents above the sampled range voltage is fixed at the breakdown voltage; below it the code raises an error. Combining curves never clamps or extrapolates: a series or parallel without a shared range that covers what is needed raises an error.
4. Bypass diodes are ideal with a 0.5 V drop and clip voltage per group they span, inside the series sum.
5. Every current grid is built by `current_grid` and contains 0.0 A whenever its range spans zero. A cell grid that spans zero without containing 0.0 raises an error.
6. The grid for the cells of one assembly at one time step is sized by `cell_current_grid` to their largest photocurrent: -0.5 to 1.6 times that current, a fixed number of points (default 600).
7. Shunt resistance is capped at its value at 0.1 W/m2 (`MIN_SHUNT_IRRADIANCE`): `rsh = min(rsh, R_sh_ref * 1000 / 0.1)`. Photocurrent stays as De Soto gives it, so a dark cell carries no current and reads 0 V at open circuit. A non-finite reference shunt resistance raises an error.

## Consequences

The 72-cell substring matches pvlib to 0.01 % (module 450.989 W against 451.03 W), one cell at 200 W/m2 costs a third of the substring's power as expected, and a dark cell gives 0.000 V at 0 A. With the scaled grid an array is within 0.07 % of a 12000-point reference at every irradiance from 1000 to 10 W/m2, at the same run time as before. Results do not depend on the shunt floor value between 0.001 and 1 W/m2. Grid length is fixed, so phase 4 can hold curves as (time, points) arrays.

Costs and limits: results differ from IPV_Workbench and published Workbench numbers (accepted clean break). Parallel connection uses only the voltage range all operands share and does not yet check that the maximum power point lies inside it (phase 2). `parallel` builds a voltage grid of varying length and `cell_voltage_at_current` loops over cells in Python; both must change for annual runs (phase 4). The bypass diode has no curve of its own.

Rejected alternatives:

- Current on a voltage grid: series connection, the common case, would need inversion every time.
- Root finding per cell (`bishop88_v_from_i`): slower and fragile near breakdown.
- Porting PVMismatch's `calcSeries`: depends on clamped interpolation and a grid based on average short-circuit current.
- A fixed grid in amps, or more points on it: accuracy still depends on irradiance.
- Adding each cell's photocurrent to the grid: exact steps, but grid length depends on the shading pattern, which rules out (time, points) arrays.
- Finer spacing near zero current: once scaled, it only resolves currents that carry almost no power and takes points from the maximum power region.
- Floor on irradiance for all parameters: invents photocurrent in the dark (a module at night would read about 33 V).
- No floor, with a small ramp forced on sampled currents: hides a model limit instead of stating it.

## Implementation (2026-11-11)

`src/cactus/electrical/curve.py` and `cell.py`, merged to `main` in PR #2 (commits bdaaa1b, be7ca3a, e016aad). Guarded by invariants 1 to 4 and 8 in `AGENTS.md`; 37 tests.
