# Electrical core plan (phase 1)

Status: Built (awaiting review), 2026-11-11, with one open question (8, question 3). Approved 2026-11-10 (Justin answered section 7).
Date: 2026-11-10. Code checked at cactus branch `bootstrap`.
Branch for the work: `phase-1-electrical-core` (create from `bootstrap`, or from `main` once `bootstrap` is merged)
Depends on: phase 0 (bootstrap)

## 1. What the code says

1. cactus has an empty package and one import test. Dependencies: numpy and pvlib (pvlib 0.16.1 and numpy 2.5.4 resolved on Python 3.13).
2. IPV_Workbench built cell curves by running pvlib's Bishop model on whole-module parameters with a -15 V breakdown, then dividing voltage by the number of cells in series. Each cell therefore stopped at about -0.2 V and never reached breakdown. Shaded cells cost almost nothing (221 W of 225 W where the corrected model gives 147 W).
3. IPV_Workbench combined curves with `np.interp`, which repeats the end value when asked for a point outside a curve. That hid the error in finding 2.
4. IPV_Workbench clipped bypass voltage on the summed module voltage. With per-cell breakdown and 24 cells per diode group the effect is under 1 %, but it is still wrong for other group sizes.
5. No measured IV data and no earlier corrected implementation are available. Validation is against pvlib and analytic cases.
6. A throwaway prototype of the design below was run on 2026-11-10 with device D001. It reproduced pvlib's module maximum power from 144 cell curves to 0.01 % and produced the expected values in section 4.3. The prototype is saved as `docs/plans/electrical-core-prototype.py` for reference.

## 2. Critique

Risks, highest first:

1. The single-diode model with De Soto parameters gives infinite shunt resistance at zero irradiance, so the Bishop breakdown term vanishes and a dark cell could carry no reverse current at any voltage. The design fixes the voltage at the breakdown voltage for currents the sampled curve does not reach (section 3.2). This is a modelling choice and is stated in the code.
2. Curves are one-dimensional (one time step). Annual runs need the same operations over a time axis. The functions are written with numpy so that a time axis can be added in phase 4; speed for annual runs is not a goal of this phase.
3. An ideal bypass diode (a fixed voltage floor) ignores the diode's own curve and its heat. Accepted for yield work.

Cut: lookup tables of precomputed curves (phase 4 decides, with the error measured); the PVMismatch point-spacing code; any module- or string-level wiring logic (phase 2).

Defer: time axis; temperature model; inverter limits; module wiring templates (half-cut, shingled, thin film).

Keep: pvlib `calcparams_desoto` and `singlediode.bishop88` as the cell model.

## 3. Design

### 3.1 Representation

Every element (cell, diode group, module, string, array) is an `IVCurve`: a current array in increasing order and a voltage array of the same length, where voltage never increases with current. Series connection adds voltages at equal current. Parallel connection adds currents at equal voltage.

### 3.2 Cell curve

Module datasheet parameters are converted to one cell. For N_s cells in series and N_p in parallel: photocurrent, saturation current and the short-circuit temperature coefficient divide by N_p; series and shunt resistance multiply by N_p / N_s; the modified ideality factor `a_ref` divides by N_s. Breakdown voltage, factor and exponent are per cell and are not scaled.

The cell curve is sampled with `bishop88` over diode voltage from 0.97 of the breakdown voltage up to a forward voltage high enough to reach the most negative current requested, then interpolated onto the caller's current grid. For currents above the highest sampled current, voltage is set to the breakdown voltage. For currents below the lowest sampled current the function raises an error.

### 3.3 Combining

- Series: resample operands onto a common current grid covering the range they all share, add voltages. Raise an error if the shared range does not include zero current.
- Bypass: voltage floor at minus the diode voltage, applied to the group the diode spans.
- Parallel: build a voltage grid from the operands' own voltage samples inside the range they all share, read each operand's current at those voltages, add, and resample onto a uniform current grid. Flat parts of a curve (a bypass floor, the breakdown floor) are made invertible by adding a slope of 1e-9 V/A before reading current at a voltage.
- Maximum power point: largest current times voltage among points with both non-negative, refined with a parabola through the neighbouring points.

Rejected alternatives: storing curves as current on a voltage grid (series connection, the common case, would need inversion every time); solving voltage at a given current by root finding per cell (`bishop88_v_from_i`; slower and fragile near breakdown); porting PVMismatch's `calcSeries` (depends on clamped interpolation and an average short-circuit current grid).

## 4. Brief for the building session

### 4.1 Files to create or change

A reference prototype is in `docs/plans/electrical-core-prototype.py`. It works on plain arrays and has no input checks or `IVCurve` type. Use it to see the method and to check numbers; write the package code and tests from this brief, and follow the brief where the two differ. Do not import it from the package or the tests.

- `src/cactus/electrical/__init__.py`: exports the names in 4.2.
- `src/cactus/electrical/curve.py`: `IVCurve`, `series`, `parallel`, `bypass`, `max_power_point`.
- `src/cactus/electrical/cell.py`: `CellParameters`, `cell_parameters_from_module`, `cell_voltage_at_current`, `cell_curves`.
- `tests/electrical/test_cell.py`, `tests/electrical/test_curve.py`, `tests/electrical/conftest.py`.
- `AGENTS.md`: Layout section, and test names next to invariants 1, 2, 3, 4 and 8.
- `docs/plans/README.md`: status row.

### 4.2 Functions

Units: current A, voltage V, power W, irradiance W/m2, temperature degC, resistance ohm.

`IVCurve` (frozen dataclass): `current: np.ndarray`, `voltage: np.ndarray`, both 1-D float, equal length of at least 2. On creation check that current is strictly increasing and voltage never increases (allow 1e-9 V of numerical noise); raise `ValueError` otherwise.

`CellParameters` (frozen dataclass), all per cell: `I_L_ref`, `I_o_ref`, `R_s`, `R_sh_ref`, `a_ref`, `alpha_sc`, `EgRef = 1.121`, `dEgdT = -0.0002677`, `breakdown_voltage = -15.0`, `breakdown_factor = 0.002`, `breakdown_exp = 3.28`.

`cell_parameters_from_module(I_L_ref, I_o_ref, R_s, R_sh_ref, a_ref, alpha_sc, n_series, n_parallel, **other) -> CellParameters`: applies the scaling in 3.2. `other` passes through `EgRef`, `dEgdT` and the breakdown values unscaled. Raise `ValueError` if `n_series` or `n_parallel` is less than 1.

`cell_voltage_at_current(params, irradiance, temperature, current_grid, n_sample=400) -> np.ndarray` of shape `(n_cells, len(current_grid))`:
1. `irradiance` is a scalar or 1-D array; `temperature` is broadcast to it. Raise `ValueError` for negative irradiance or a current grid that is not strictly increasing.
2. Get the five single-diode values from `pvlib.pvsystem.calcparams_desoto`.
3. Let `i_neg = max(0, -current_grid[0])`. Highest diode voltage per cell: `nNsVth * log((IL + 1.05 * i_neg + 1e-12) / I0 + 1)`.
4. Diode voltage samples per cell: `n_sample // 2` points evenly spaced from `0.97 * breakdown_voltage` up to but not including 0, then `n_sample // 2` points from 0 to the highest diode voltage placed at `vd_max * (1 - (1 - u)**2)` for `u` evenly spaced in [0, 1].
5. `pvlib.singlediode.bishop88` with the breakdown values gives current and terminal voltage at those samples. Current decreases as diode voltage rises.
6. Interpolate terminal voltage onto `current_grid`. Above the highest sampled current use `breakdown_voltage`. Below the lowest sampled current raise `ValueError`.

`cell_curves(params, irradiance, temperature, current_grid) -> list[IVCurve]`: wraps the function above.

`bypass(curve, diode_voltage=0.5) -> IVCurve`: voltage replaced by `maximum(voltage, -diode_voltage)`. Raise `ValueError` if `diode_voltage` is negative.

`series(curves, n_points=600) -> IVCurve`: common grid is `linspace(lo, hi, n_points)` with `lo` the largest first current and `hi` the smallest last current of the operands. Raise `ValueError` if the list is empty or if not `lo <= 0 < hi`. Interpolate each operand's voltage onto the grid and add. One operand is returned unchanged.

`parallel(curves, n_points=600) -> IVCurve`: `v_lo` is the largest minimum voltage and `v_hi` the smallest maximum voltage of the operands; raise `ValueError` if `v_hi <= 0` or `v_lo >= v_hi`. Voltage grid: sorted unique values of every operand's voltages clipped to `[v_lo, v_hi]`. For each operand, make voltage strictly decreasing with `voltage - 1e-9 * (current - current[0])` and interpolate current at the voltage grid. Add the currents. Output current grid: `linspace(min, max, n_points)` of the summed current; output voltage: interpolate the voltage grid at those currents (add `1e-9 * index` to the summed current if needed to make it strictly monotonic before interpolating). One operand is returned unchanged.

`max_power_point(curve) -> tuple[float, float, float]` (current, voltage, power): consider only points with current >= 0 and voltage >= 0. If none has positive power return `(0.0, 0.0, 0.0)`. Otherwise take the point of largest power; if both neighbours are also valid, fit a parabola to power against voltage through the three points, and if it opens downward with its peak between them, return the peak voltage, the curve's current at that voltage and the parabola's peak power.

No function may call `np.interp` in a way that lets it repeat an end value silently, except the breakdown rule in step 6, which is commented where it is used.

### 4.3 Tests to write first

Fixture `d001_module` in `conftest.py` (IPV_Workbench device D001, a 144 half-cell mono-Si module): `I_L_ref=11.34299391`, `I_o_ref=1.77e-11`, `R_s=0.202623823`, `R_sh_ref=767.4762928`, `a_ref=1.828557411`, `alpha_sc=0.00034`, `n_series=72`, `n_parallel=2`. Fixture `cell` is `cell_parameters_from_module` of it. Fixture `grid` is `np.linspace(-3.0, 9.0, 600)`. All cases at 25 degC unless stated. "Unshaded substring" is 72 cells at 1000 W/m2 in three groups of 24, each group bypassed, in series.

| Test | Set-up | Expected |
|---|---|---|
| `test_cell_scaling` | `cell` fields | `I_L_ref` 5.671496955, `I_o_ref` 8.85e-12, `R_s` 0.202623823/36, `R_sh_ref` 767.4762928/36, `a_ref` 1.828557411/72, `alpha_sc` 0.00017; relative 1e-12 |
| `test_cell_matches_pvlib` | one cell at 1000 | maximum power within 0.05 % of `pvlib.singlediode.bishop88_mpp` for the same cell values (3.1321 W); voltage at zero current within 1e-3 V of 0.6903 |
| `test_cell_reaches_breakdown` (invariant 8) | one cell at 1000 | minimum voltage on `grid` below -13 V |
| `test_dark_cell_is_finite` | one cell at 0 | all values finite; voltage at the last grid point equals -15.0 |
| `test_input_errors` | negative irradiance; a current grid that is not strictly increasing | each raises `ValueError` |
| `test_wide_negative_grid_is_finite` | one cell at 1000 on `np.linspace(-50.0, 9.0, 600)` | all values finite; voltage at the first grid point above the voltage at zero current |
| `test_series_identity` (invariant 3) | 10 identical cells in series | voltage equals 10 times one cell's voltage on the same grid, absolute 1e-9 |
| `test_parallel_identity` (invariant 3) | 3 unshaded substrings in parallel | maximum power within 0.02 % of 3 times one substring; current at maximum power within 0.1 % of 3 times |
| `test_module_matches_pvlib` | 2 unshaded substrings in parallel | maximum power within 0.05 % of `bishop88_mpp` on the module-level values (451.03 W) |
| `test_bypass_per_group` (invariant 1) | substring with the first cell at 200 | maximum power between 0.650 and 0.660 of the unshaded substring (147.6 W of 225.5 W); the first group's voltage is never below -0.5 |
| `test_no_bypass_reverse_bias` | 24 cells in series, first at 0, no bypass | minimum voltage of the series below -14 V; the shaded cell's curve reaches -15.0 |
| `test_power_bound` (invariant 4) | 50 substrings with cell irradiance drawn from `default_rng(0).uniform(0, 1100, 72)` | each substring's maximum power is at most the sum of its cells' maximum powers plus 1e-6 |
| `test_unequal_parallel_strings` | strings of 4 and 11 unshaded substrings in series, the two strings in parallel | maximum power between 0.53 and 0.58 of 15 times one substring |
| `test_equal_parallel_strings` | five strings of 10 | ratio within 0.1 % of 1 |
| `test_series_of_parallel` | two tiers in series, each tier two unshaded substrings in parallel | maximum power within 0.05 % of 4 times one substring |
| `test_series_needs_shared_range` (invariant 2) | two curves whose current ranges do not both include zero | `series` raises `ValueError` |
| `test_ivcurve_validation` | current not increasing; voltage increasing; unequal lengths | each raises `ValueError` |
| `test_mpp_of_dead_curve` | curve with all voltages <= 0 | `(0.0, 0.0, 0.0)` |

### 4.4 Out of scope

Module wiring templates, strings, converters, warnings about unequal strings (phase 2). Time series. Temperature models. Reading device tables or any file. Plotting. Performance tuning beyond using numpy arrays.

### 4.5 Finished means

All tests in 4.3 exist and pass with the stated tolerances unchanged; `uv run ruff check` and `uv run ruff format --check` pass; `AGENTS.md` is updated; the build report in section 8 is filled in; the work is committed on `phase-1-electrical-core`.

Optional cross-check, reported but not required: try `uv run --with pvmismatch python -c "import pvmismatch"`. If it imports on Python 3.13, compare one partially shaded 72-cell substring and record both numbers in the build report. Do not add it as a dependency.

## 5. Cross-repo asks

None.

## 6. ADR outline

ADR-004 (write when this is reviewed): curves are voltage sampled on a current grid; cells are computed from per-cell parameters with breakdown per cell; voltage is fixed at the breakdown voltage beyond the sampled current range; ideal bypass diode.

## 7. Questions for Justin

All answered 2026-11-10.

1. Is the "fold" in series curves from the earlier `circuits.py` notes real? Justin: not sure, probably produced by the old code. Decision: use the current grid as designed. If a fold shows up in measured data later, reopen this.
2. Ideal bypass diode with a 0.5 V drop: Justin chose yes.
3. Reverse-bias defaults (-15 V per cell, factor 0.002, exponent 3.28): Justin chose yes.
4. A fully dark cell held at the breakdown voltage for any current it cannot otherwise carry: Justin chose yes.
5. Save the prototype next to the plan: Justin chose yes.

## 8. Build report

- Date, model, branch, last commit: 2026-11-11, Claude Opus 5.5 (configured `claude-opus-5-5`) in Cowork. Branch `phase-1-electrical-core`, created from `main` at ce99def (bootstrap already merged in PR #1). The build is one commit on that branch; its hash is in `git log`.
- What was built: `src/cactus/electrical/` (`__init__.py`, `curve.py`, `cell.py`) with every name in 4.2; `tests/electrical/` (`conftest.py`, `test_cell.py`, `test_curve.py`) with all 18 tests in 4.3, written first and seen failing (collection error, module missing) before the code existed. `AGENTS.md` Layout and invariants 1, 2, 3, 4, 8 updated; `docs/plans/README.md` row updated.
- Numbers measured (25 degC): cell Pmp 3.13196 W (pvlib `bishop88_mpp` 3.13213 W, -0.005 %); cell Voc 0.69029 V; cell minimum voltage on `grid` -13.60 V; unshaded substring 225.501 W; module (two substrings in parallel) 450.988 W vs pvlib 451.03 W (-0.009 %); one cell at 200 W/m2: ratio 0.6547 (147.6 W); strings of 4 and 11 in parallel: 0.5517; five strings of 10: 0.99997; two tiers of two: 0.99997; three substrings in parallel: 0.99997. All agree with the prototype output.
- Deviations from the brief:
  1. `IVCurve` also rejects non-finite values and arrays that are not 1-D. The brief lists only monotonicity and length checks.
  2. `parallel([])` raises `ValueError`, matching `series([])`. The brief states this only for `series`.
  3. `max_power_point` reads the current at the parabola's peak by interpolating between the three points used for the fit, not over the whole curve. Same value; it avoids interpolating over flat parts of a curve. It also skips the parabola when the three voltages are equal.
  4. Reverse-bias diode-voltage samples use `np.linspace(0.97 * breakdown_voltage, 0, n_sample // 2, endpoint=False)` as the brief says; the prototype used `n_sample // 2 - 1` points. No measurable effect on the numbers above.
  5. `test_no_bypass_reverse_bias` sits in `test_cell.py`; the brief does not assign tests to files.
- Checks run, on Python 3.13.18 in the cloud container with `UV_PROJECT_ENVIRONMENT` outside the repo (pvlib 0.16.1, numpy 2.5.4):
  - `uv sync`: `Resolved 21 packages`, `Checked 20 packages`
  - `uv run pytest -q`: `19 passed in 1.26s` (first commit); `21 passed in 1.48s` after the two tests from questions 1 and 2
  - `uv run ruff check`: `All checks passed!`
  - `uv run ruff format --check`: `13 files already formatted`
  - Not run: the same checks on Justin's Mac (macOS `.venv`), and nothing was run in the device shell (Python 3.10, no pvlib).
- Optional PVMismatch cross-check: `pvmismatch` 4.1 imports on Python 3.13 (with a SyntaxWarning in its docstrings). Module `STD72` (three bypassed groups of 24), bypass -0.5 V, first cell at 0.2 suns. With PVMismatch's default cell: 241.0 W unshaded, 206.0 W shaded, ratio 0.855 (its default reverse-bias parameters differ). With an approximate D001 mapping (one diode, `Isat2_T0=0`, `Isat1_T0=8.85e-12`, `Isc0_T0=5.6715`, per-cell `Rs`, `Rsh`, `aRBD=0.002`, `bRBD=0`, `VRBD=-15`, `nRBD=3.28`): 228.3 W unshaded, 152.0 W shaded, ratio 0.666, against cactus 225.5 W, 147.6 W, 0.655. The mapping is not exact: PVMismatch fixes the diode ideality at 1 (D001 cell `a_ref` 0.02540 V vs thermal voltage 0.02569 V) and uses Isc rather than IL. Not added as a dependency.
- Questions back to planning:
  1. Answered (Justin, 2026-11-11): add a full-curve parallel identity test, relative tolerance 1e-3. Added as `test_parallel_identity_full_curve`: three unshaded substrings in parallel, current at 200 voltages from 0 to 0.99 of the substring's open-circuit voltage against 3 times the substring current. Largest measured error 0.049 % (8 mA).
  2. Answered (Justin, 2026-11-11): yes. Added `test_parallel_needs_shared_range`: all voltages <= 0, voltage ranges [2, 3] V and [0, 1] V that do not overlap, and an empty list each raise `ValueError`.
  3. Answered by addendum A (section 10), 2026-11-11. Found after the first build: a fully dark cell's voltage at 0 A is not defined. De Soto parameters give infinite shunt resistance at 0 W/m2, so every reverse voltage from 0 to -14.55 V carries about 0 A, and interpolation on `grid` returns -11.1 V where about 0 V is right. A 24-cell series with one dark cell then reads 4.76 V at 0 A instead of about 16 V; a bypass does not hide it. Maximum power is unaffected (substring with one dark cell: 147.64 W on 600 and on 6000 points). Justin chose option (a) on 2026-11-11: compute cells below a minimum irradiance (0.1 W/m2 proposed) at that minimum so the shunt stays finite. Tried and taken back out, not committed: with the floor, the dark cell's whole curve from open circuit to breakdown fits inside about 5 mA, narrower than the 20 mA spacing of `grid`, so 0 A still interpolates to -10.6 V (24-cell string 5.24 V). Measured with the floor: 6000-point grid gives 0.423 V (string 16.30 V); `grid` with 0 A added gives 0.456 V (string 16.33 V). Planning needs to decide: (i) whether the floor is kept and at what value, and (ii) how the current grid resolves a dark cell near 0 A (always include 0 A and each cell's photocurrent, a finer grid near zero, or another method), including the grids `series` and `parallel` build. Test drafted for this: dark cell voltage at 0 A in [0, 0.6903) V, and the 24-cell string with one dark cell above 23 x 0.6903 V at 0 A.
  4. Answered by addendum A (section 10). Related to 3: for a dark cell `bishop88` returns many nearly equal currents on the reverse branch, so `np.interp` gets sample currents that may not be strictly increasing, and its result there is not guaranteed. The fix chosen for 3 should cover this.
- Notes on things seen but not changed:
  1. `bishop88` at irradiance 0 runs with infinite shunt resistance. A run with warnings turned into errors (`python -W error`) at 0 W/m2 and 500 W/m2, 75 degC, raised nothing.
  2. A dark cell's sampled curve ends at about 0 A (risk 1 in section 2: the Bishop term vanishes), so on `grid` it steps from +0.54 V at -0.015 A to -15.0 V at +0.005 A. See question 3.
  3. `test_power_bound` takes most of the test time (50 x 72 cells); fine for now.

## 9. Review of the build (planning session, 2026-11-11)

Checked at `phase-1-electrical-core` be7ca3a. Tests re-run on Python 3.13.18 in the cloud container: 21 passed, ruff clean.

- Deviations 1 to 5 are all kept. 1 and 2 add input checks the brief should have listed. 3 gives the same value and avoids interpolating across flat parts of a curve. 4 follows the brief. 5 is file placement.
- The measured numbers match the plan's expected values and the prototype.
- Findings beyond the build report:
  1. **The current grid is fixed in amps, so accuracy falls with irradiance.** On the test fixture grid (-3 to 9 A, 600 points) a three-string array with 15 % cell-to-cell variation is off by 0.07 % at 1000 W/m2, 0.4 % at 300, 2.5 % at 100 and 5.5 % at 30, against a 12000-point grid. With the grid scaled to the largest photocurrent the error is 0.07 % at every level. This matters more than the dark cell for facades, which spend many hours at 100 to 300 W/m2. Fixed by addendum A.
  2. `_current_at_voltage` adds a slope of 1e-9 V/A to make voltage invertible, but `IVCurve` allows upward noise of 1e-9 V. On a small grid (low light) the slope is smaller than the noise and `np.interp` can receive voltages that are not monotonic. Fixed by addendum A.
  3. `parallel` uses only the voltage range all operands share and says nothing when that cuts off part of a curve. If the true maximum power point lies above the shared range the result is silently low. Not seen in the tests (the 4-and-11 case has its optimum inside the range). Deferred to phase 2, where grids are chosen: check that an array's maximum power point is not at the upper edge of the shared range.
  4. `cell_voltage_at_current` loops over cells in Python. Fine now; phase 4 has to remove the loop for annual runs.

## 10. Addendum A: grids and dark cells

Status: Approved (Justin, 2026-11-11) and built; see the second build report entry in 10.7
Resolves build report questions 3 and 4 and review findings 1 and 2. Work continues on `phase-1-electrical-core`.

### 10.1 What was measured

All with device D001 at 25 degC, on a copy of be7ca3a with the changes below applied.

| Case | As built | With the changes |
|---|---|---|
| Dark cell, voltage at 0 A | -11.12 V | 0.000 V |
| 24 cells in series, one dark, voltage at 0 A | 4.76 V | 15.877 V (23 x 0.69029) |
| Substring, one dark cell, voltage at 0 A | 37.90 V | 49.010 V (71 x 0.69029) |
| Substring, one dark cell, maximum power | 147.638 W | 147.638 W |
| Unshaded substring, maximum power | 225.5011 W | 225.5014 W |
| Module (two substrings in parallel) | 450.9882 W | 450.9892 W |
| Strings of 4 and 11 in parallel, ratio | 0.55170 | 0.55167 |
| All 21 existing tests, tolerances unchanged | pass | pass |

What fixes what:

- Voltage at 0 A is fixed by having 0 A as a point in every grid, and by nothing else. A minimum-irradiance floor alone leaves it at -10.6 V; 0 A in the grid alone gives 0.000 V.
- The floor is still needed for question 4: without it a dark cell's sampled currents are not strictly increasing.
- A floor on irradiance gives a dark cell 0.456 V at open circuit (a module at night would show about 33 V). A floor on shunt resistance only keeps photocurrent at zero and gives 0.000 V.
- Results do not depend on the floor value: 0.001, 0.01, 0.1 and 1 W/m2 give the same maximum power and open-circuit voltage to four decimals.

### 10.2 Decisions

a. **Floor.** Keep a floor at 0.1 W/m2, applied to the shunt resistance only: `rsh = min(rsh, R_sh_ref * 1000 / 0.1)`. Photocurrent stays as De Soto gives it. (Justin's option (a) applied the floor to irradiance for all parameters; question 1 in 10.6.)

b. **Grids.**
1. One function, `current_grid(lo, hi, n_points)`, builds every current grid. It returns exactly `n_points` values and contains 0.0 A whenever the range spans zero. `series` and `parallel` use it.
2. `cell_voltage_at_current` raises `ValueError` for a grid that spans zero without containing 0.0.
3. A second function, `cell_current_grid(params, irradiance, temperature, n_points)`, sets the range from the largest photocurrent of the cells passed: from -0.5 to 1.6 times that current (the same proportions as the -3 to 9 A fixture at 1000 W/m2). Callers use it for the cells of one assembly at one time step.

c. **Cost.**
- Maximum power changes by at most 3 parts in 100,000 in the existing cases (table above).
- The grid length stays fixed at `n_points`, so arrays keep the shape (time, points) in phase 4. A scaled grid is one fixed set of points multiplied by one number per time step.
- No extra points are added, so run time is unchanged (0.17 s for an 18-module array with 2592 cells).
- `parallel` still builds a voltage grid whose length varies. That was already the part phase 4 has to redesign; this addendum does not change it.

Rejected alternatives:

- Floor on irradiance for all parameters: invents photocurrent in the dark; no benefit over the shunt-only floor.
- No floor, strictness forced by adding a tiny ramp to the sampled currents: hides a model limit instead of stating it.
- Adding each cell's photocurrent to the grid as an extra point: resolves every step exactly, but the grid length then depends on the shading pattern, which rules out a (time, points) array in phase 4.
- Finer spacing near zero (geometric or squared): once the grid is scaled it resolves only currents that carry almost no power, and it takes points away from the region of the maximum power point. Not measured; rejected on that reasoning.
- More points on the fixed grid: 1200 points halves the error but does not remove the dependence on irradiance.

### 10.3 Files to change

- `src/cactus/electrical/curve.py`: add `current_grid`; add private `_strictly_decreasing`; change `series`, `parallel`, `_current_at_voltage`; remove `SLOPE`.
- `src/cactus/electrical/cell.py`: add `MIN_SHUNT_IRRADIANCE`, `cell_current_grid`; change `cell_voltage_at_current`.
- `src/cactus/electrical/__init__.py`: export `current_grid` and `cell_current_grid`.
- `tests/electrical/conftest.py`: fixture `grid` becomes `current_grid(-3.0, 9.0, 600)`.
- `tests/electrical/test_cell.py`: `test_wide_negative_grid_is_finite` uses `current_grid(-50.0, 9.0, 600)`; new tests below.
- `tests/electrical/test_curve.py`: new tests below.
- `AGENTS.md`: Layout line for the two new functions; invariant 2 gains the new test names.

### 10.4 Functions

`current_grid(lo, hi, n_points=600) -> np.ndarray`: raise `ValueError` if `n_points < 3` or not `lo < hi`. If `lo < 0 < hi`: `n_neg = min(n_points - 2, max(1, round((n_points - 1) * -lo / (hi - lo))))`; result is `linspace(lo, 0, n_neg, endpoint=False)` followed by `linspace(0, hi, n_points - n_neg)`. Otherwise `linspace(lo, hi, n_points)`.

`_strictly_decreasing(values) -> np.ndarray`: `m = np.minimum.accumulate(values)`; `step = 4 * np.finfo(float).eps * max(1.0, max(abs(m)))`; return `m - step * np.arange(m.size)`.

`_current_at_voltage(curve, v_grid)`: `strict = _strictly_decreasing(curve.voltage)`; clip `v_grid` to `[strict[-1], strict[0]]`; interpolate current at those voltages. (The clip moves a value by at most `600 * step`; it is not an extrapolation.)

`series`: unchanged except the grid is `current_grid(lo, hi, n_points)`.

`parallel`: unchanged up to the summed current `total`. Then `falling = _strictly_decreasing(total)`; `grid = current_grid(falling[-1], falling[0], n_points)`; voltage is `np.interp(grid, falling[::-1], v_grid[::-1])`.

`MIN_SHUNT_IRRADIANCE = 0.1` (W/m2), module constant in `cell.py` with a comment giving the reason.

`cell_voltage_at_current`: three changes.
1. Raise `ValueError` if `R_sh_ref` is not finite and positive.
2. Raise `ValueError` if `grid[0] < 0 < grid[-1]` and 0.0 is not an element of the grid.
3. After `calcparams_desoto`: `rsh = np.minimum(rsh, params.R_sh_ref * 1000.0 / MIN_SHUNT_IRRADIANCE)`. After reversing the sampled arrays: raise `ValueError` if the sampled current is not strictly increasing.

`cell_current_grid(params, irradiance, temperature, n_points=600) -> np.ndarray`: photocurrent of each cell from `calcparams_desoto`; `i_ref = max(largest photocurrent, 1e-3 * params.I_L_ref)`; return `current_grid(-0.5 * i_ref, 1.6 * i_ref, n_points)`. Same input checks on irradiance as `cell_voltage_at_current`.

### 10.5 Tests to write first

Fixtures as in 4.3, with `grid = current_grid(-3.0, 9.0, 600)`. "Voltage at 0 A" is `np.interp(0.0, curve.current, curve.voltage)`. Cell open-circuit voltage is 0.69029 V.

| Test | Set-up | Expected |
|---|---|---|
| `test_current_grid` | `current_grid(-3.0, 9.0, 600)` | 600 values, strictly increasing, first -3.0, last 9.0, exactly one value equal to 0.0, 150 values below zero |
| `test_current_grid_one_sided` | `current_grid(0.0, 9.0, 10)` and `current_grid(1.0, 2.0, 5)` | equal to `np.linspace` of the same arguments |
| `test_current_grid_errors` | `n_points=2`; `lo == hi`; `lo > hi` | each raises `ValueError` |
| `test_grid_spanning_zero_must_contain_zero` (invariant 2) | `cell_voltage_at_current` with `np.linspace(-3.0, 9.0, 600)` | raises `ValueError` |
| `test_dark_cell_at_zero_current` | one cell at 0 W/m2 on `grid` | voltage at 0 A within 1e-6 V of 0.0 |
| `test_string_with_dark_cell_open_circuit` | 24 cells in series, first at 0, others 1000, no bypass | voltage at 0 A within 1e-3 V of 23 times the lit cell's voltage at 0 A (15.877 V) |
| `test_substring_with_dark_cell` | substring, first cell at 0 | voltage at 0 A within 0.01 V of 49.010; maximum power within 0.1 % of 147.64 W |
| `test_combined_grids_contain_zero` | `series` of 10 cells; `parallel` of 3 unshaded substrings; `series` of two such parallels | each result's current has exactly one value equal to 0.0 and 600 values |
| `test_night` | substring with all 72 cells at 0, on `cell_current_grid` of those cells; and two such in parallel | `max_power_point` is `(0.0, 0.0, 0.0)` for both; substring voltage at 0 A within 1e-6 V of 0.0; no error raised |
| `test_low_irradiance_sweep_runs` (question 4) | one cell at each of 0, 1e-6, 0.05, 0.1, 1 W/m2 and each of -20, 25, 85 degC, on `grid` | no error; every voltage array finite and never increasing |
| `test_infinite_shunt_rejected` | `dataclasses.replace(cell, R_sh_ref=float("inf"))` at 1000 W/m2 | raises `ValueError` |
| `test_cell_current_grid` | cell at 100 W/m2 | first value -0.28357485, last 0.90743951 (relative 1e-8), one value equal to 0.0; for three cells at 0 W/m2: first -0.0028357485, last 0.0090743951 |
| `test_low_light_accuracy` | substring with irradiance `default_rng(0).uniform(70.0, 100.0, 72)`, built on `cell_current_grid(..., 600)` and again with 6000 points everywhere | maximum power on 600 points within 0.1 % of the 6000-point value (16.290 W against 16.288 W) |
| `test_uniform_low_light_matches_pvlib` | unshaded substring at 100, 30 and 10 W/m2 on `cell_current_grid` | maximum power within 0.05 % of half of `bishop88_mpp` on the module-level values (21.352, 6.076, 1.920 W) |

`test_parallel_identity_full_curve` has its own copy of the old slope helper; leave it as it is (it is test code and still valid).

Out of scope: the check in review finding 3; removing the Python loop over cells; any change to `n_sample`.

Finished means: the 21 existing tests pass with tolerances unchanged, the 14 tests above pass, ruff is clean, `AGENTS.md` is updated, and a second entry is added to the build report.

### 10.6 Questions for Justin

All answered 2026-11-11.

1. Floor on shunt resistance only, instead of on irradiance for all parameters: Justin accepted.
2. Include the scaled grid (`cell_current_grid`) in this fix: Justin chose yes.
3. A grid that spans zero without containing 0.0 raises an error: Justin chose yes.
4. Defer the silent voltage-range restriction in `parallel` (review finding 3) to the phase 2 plan: Justin chose yes.

### 10.7 Build report, addendum A

- Date, model, branch: 2026-11-11, planning session (Claude Fable 5.2 in Cowork), branch `phase-1-electrical-core`, one commit after be7ca3a; its hash is in `git log`. Justin chose to have this session apply the fix because the changes were already written and measured for the addendum.
- What was built: everything in 10.3 and 10.4. The 14 tests in 10.5 (16 test cases, because `test_uniform_low_light_matches_pvlib` runs at three irradiances). The tests fail against be7ca3a (import error for `current_grid`) and pass with the change.
- Deviations from the addendum:
  1. `cell.py` gained a private helper `_single_diode_values` so that `cell_current_grid` and `cell_voltage_at_current` share the irradiance checks and the De Soto call.
  2. In `cell.py` the grid function is imported as `build_current_grid`, because `cell_voltage_at_current` and `cell_curves` already have a parameter named `current_grid`.
  3. `AGENTS.md` also gained a Don't line about building grids with `np.linspace` or a fixed range in amps.
- Existing tests: unchanged except the `grid` fixture and the wide grid in `test_wide_negative_grid_is_finite`, which now use `current_grid`. No expected value or tolerance was changed.
- Checks run, on Python 3.13.18 in the cloud container with `UV_PROJECT_ENVIRONMENT` outside the repo (pvlib 0.16.1, numpy 2.5.4):
  - `uv run pytest -q`: `37 passed in 1.59s`; also passes with `python -W error -m pytest`
  - `uv run ruff check`: `All checks passed!`
  - `uv run ruff format --check`: `12 files already formatted`
  - Not run: the same checks on Justin's Mac.
- Numbers measured: as in the table in 10.1. Array error against a 12000-point grid with the scaled grid: 0.07 % (15 % cell-to-cell variation) and 0.03 % (shaded blocks) at 1000, 300, 100, 30 and 10 W/m2.
- Carried to phase 2: review finding 3 (check that an array's maximum power point is not at the upper edge of the voltage range `parallel` used). Carried to phase 4: the Python loop over cells, and the variable-length voltage grid inside `parallel`.
