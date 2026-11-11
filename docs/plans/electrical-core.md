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
  3. Open, blocking the dark-cell fix. Found after the first build: a fully dark cell's voltage at 0 A is not defined. De Soto parameters give infinite shunt resistance at 0 W/m2, so every reverse voltage from 0 to -14.55 V carries about 0 A, and interpolation on `grid` returns -11.1 V where about 0 V is right. A 24-cell series with one dark cell then reads 4.76 V at 0 A instead of about 16 V; a bypass does not hide it. Maximum power is unaffected (substring with one dark cell: 147.64 W on 600 and on 6000 points). Justin chose option (a) on 2026-11-11: compute cells below a minimum irradiance (0.1 W/m2 proposed) at that minimum so the shunt stays finite. Tried and taken back out, not committed: with the floor, the dark cell's whole curve from open circuit to breakdown fits inside about 5 mA, narrower than the 20 mA spacing of `grid`, so 0 A still interpolates to -10.6 V (24-cell string 5.24 V). Measured with the floor: 6000-point grid gives 0.423 V (string 16.30 V); `grid` with 0 A added gives 0.456 V (string 16.33 V). Planning needs to decide: (i) whether the floor is kept and at what value, and (ii) how the current grid resolves a dark cell near 0 A (always include 0 A and each cell's photocurrent, a finer grid near zero, or another method), including the grids `series` and `parallel` build. Test drafted for this: dark cell voltage at 0 A in [0, 0.6903) V, and the 24-cell string with one dark cell above 23 x 0.6903 V at 0 A.
  4. Related to 3: for a dark cell `bishop88` returns many nearly equal currents on the reverse branch, so `np.interp` gets sample currents that may not be strictly increasing, and its result there is not guaranteed. The fix chosen for 3 should cover this.
- Notes on things seen but not changed:
  1. `bishop88` at irradiance 0 runs with infinite shunt resistance. A run with warnings turned into errors (`python -W error`) at 0 W/m2 and 500 W/m2, 75 degC, raised nothing.
  2. A dark cell's sampled curve ends at about 0 A (risk 1 in section 2: the Bishop term vanishes), so on `grid` it steps from +0.54 V at -0.015 A to -15.0 V at +0.005 A. See question 3.
  3. `test_power_bound` takes most of the test time (50 x 72 cells); fine for now.
