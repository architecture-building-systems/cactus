"""Throwaway prototype for docs/plans/electrical-core.md (phase 1).

Reference only. It shows that the design in the plan works and where the
expected values in the plan's tests come from. It is not part of the package
and is not tested. The building session writes the package code and tests
from the plan's brief; where this file and the brief differ, the brief wins.
Delete this file when phase 1 is marked Done.

Run: uv run python docs/plans/electrical-core-prototype.py
"""

import numpy as np
from pvlib import pvsystem, singlediode

# IPV_Workbench device D001: module-level values, 72 cells in series, 2 in parallel.
MODULE = {
    "alpha_sc": 0.00034,
    "a_ref": 1.828557411,
    "I_L_ref": 11.34299391,
    "I_o_ref": 1.77e-11,
    "R_sh_ref": 767.4762928,
    "R_s": 0.202623823,
    "EgRef": 1.121,
    "dEgdT": -0.0002677,
}
N_SERIES, N_PARALLEL = 72, 2
BREAKDOWN = {
    "breakdown_voltage": -15.0,
    "breakdown_factor": 0.002,
    "breakdown_exp": 3.28,
}
SLOPE = 1e-9  # V/A, makes flat parts of a curve invertible


def to_cell(module, n_series, n_parallel):
    cell = dict(module)
    cell["I_L_ref"] /= n_parallel
    cell["I_o_ref"] /= n_parallel
    cell["alpha_sc"] /= n_parallel
    cell["R_s"] *= n_parallel / n_series
    cell["R_sh_ref"] *= n_parallel / n_series
    cell["a_ref"] /= n_series
    return cell


CELL = to_cell(MODULE, N_SERIES, N_PARALLEL)


def cell_voltage_at_current(cell, irradiance, temperature, grid, n_sample=400):
    """Voltage of each cell on a shared current grid, shape (n_cells, len(grid))."""
    irradiance = np.atleast_1d(np.asarray(irradiance, float))
    temperature = np.broadcast_to(np.asarray(temperature, float), irradiance.shape)
    values = pvsystem.calcparams_desoto(irradiance, temperature, **cell)
    il, i0, rs, rsh, nvth = (
        np.broadcast_to(np.asarray(x, float), irradiance.shape) for x in values
    )
    i_neg = max(0.0, -grid[0])
    vd_max = nvth * np.log((il + 1.05 * i_neg + 1e-12) / i0 + 1.0)
    u = np.linspace(0, 1, n_sample // 2)
    reverse = 0.97 * BREAKDOWN["breakdown_voltage"] * (1 - u)[:-1]
    out = np.empty((irradiance.size, grid.size))
    for k in range(irradiance.size):
        forward = vd_max[k] * (1 - (1 - u) ** 2)
        vd = np.concatenate([reverse, forward])
        i, v, _ = singlediode.bishop88(
            vd, il[k], i0[k], rs[k], rsh[k], nvth[k], **BREAKDOWN
        )
        # Current falls as diode voltage rises, so reverse both for np.interp.
        # right=: above the highest sampled current the cell sits at its breakdown voltage.
        out[k] = np.interp(
            grid, i[::-1], v[::-1], left=np.nan, right=BREAKDOWN["breakdown_voltage"]
        )
    if np.isnan(out).any():
        raise ValueError("current grid extends below the sampled cell curve")
    return out


def bypass(voltage, diode_voltage=0.5):
    return np.maximum(voltage, -diode_voltage)


def series(curves, n_points=600):
    lo = max(c[0][0] for c in curves)
    hi = min(c[0][-1] for c in curves)
    if not lo <= 0 < hi:
        raise ValueError("operands share no current range around zero")
    grid = np.linspace(lo, hi, n_points)
    return grid, sum(np.interp(grid, c[0], c[1]) for c in curves)


def current_at_voltage(current, voltage, v_grid):
    strict = voltage - SLOPE * (current - current[0])
    return np.interp(v_grid, strict[::-1], current[::-1])


def parallel(curves, n_points=600):
    v_lo = max(c[1].min() for c in curves)
    v_hi = min(c[1].max() for c in curves)
    if v_hi <= 0 or v_lo >= v_hi:
        raise ValueError("operands share no voltage range above zero")
    v_grid = np.unique(np.concatenate([np.clip(c[1], v_lo, v_hi) for c in curves]))
    total = sum(current_at_voltage(c[0], c[1], v_grid) for c in curves)
    grid = np.linspace(total.min(), total.max(), n_points)
    x = total[::-1] + SLOPE * np.arange(total.size)
    return grid, np.interp(grid, x, v_grid[::-1])


def max_power_point(current, voltage):
    valid = (current >= 0) & (voltage >= 0)
    power = np.where(valid, current * voltage, 0.0)
    k = int(np.argmax(power))
    if power[k] <= 0:
        return 0.0, 0.0, 0.0
    if 0 < k < power.size - 1 and valid[k - 1] and valid[k + 1]:
        x, y = voltage[k - 1 : k + 2], power[k - 1 : k + 2]
        a = np.polyfit(x, y, 2)
        if a[0] < 0:
            v_peak = -a[1] / (2 * a[0])
            if x.min() <= v_peak <= x.max():
                i_peak = np.interp(v_peak, voltage[::-1], current[::-1])
                return float(i_peak), float(v_peak), float(np.polyval(a, v_peak))
    return float(current[k]), float(voltage[k]), float(power[k])


def substring(irradiance, grid):
    """72 cells in three bypassed groups of 24, in series."""
    v = cell_voltage_at_current(CELL, irradiance, 25.0, grid)
    return grid, sum(bypass(v[g * 24 : (g + 1) * 24].sum(axis=0)) for g in range(3))


def main():
    grid = np.linspace(-3.0, 9.0, 600)
    pmp = lambda curve: max_power_point(*curve)[2]

    v_cell = cell_voltage_at_current(CELL, [1000.0], 25.0, grid)[0]
    cell_values = pvsystem.calcparams_desoto(1000.0, 25.0, **CELL)
    ref_cell = float(singlediode.bishop88_mpp(*cell_values, **BREAKDOWN)[2])
    print(f"cell Pmp {pmp((grid, v_cell)):.5f} W, pvlib {ref_cell:.5f} W")
    print(
        f"cell Voc {np.interp(0, grid, v_cell):.5f} V, minimum voltage {v_cell.min():.2f} V"
    )

    full = substring(np.full(72, 1000.0), grid)
    module_values = pvsystem.calcparams_desoto(1000.0, 25.0, **MODULE)
    ref_module = float(singlediode.bishop88_mpp(*module_values)[2])
    module = parallel([full, full])
    print(f"unshaded substring Pmp {pmp(full):.2f} W")
    print(f"module Pmp {pmp(module):.2f} W, pvlib on module values {ref_module:.2f} W")

    for shade in (500.0, 200.0, 0.0):
        g = np.full(72, 1000.0)
        g[0] = shade
        print(
            f"one cell at {shade:.0f}: ratio to unshaded {pmp(substring(g, grid)) / pmp(full):.4f}"
        )

    g = np.full(24, 1000.0)
    g[0] = 0.0
    v = cell_voltage_at_current(CELL, g, 25.0, grid)
    print(f"24 cells, one dark, no bypass: minimum voltage {v.sum(axis=0).min():.1f} V")

    def string(n):
        return series([full] * n) if n > 1 else full

    for lengths in ([4, 11], [10] * 5, [4, 4, 4, 4, 4, 10, 11, 11, 11, 11]):
        array = parallel([string(n) for n in lengths])
        print(
            f"strings {lengths} in parallel: ratio {pmp(array) / (sum(lengths) * pmp(full)):.4f}"
        )

    tier = parallel([full, full])
    print(
        f"two tiers of two in series: ratio {pmp(series([tier, tier])) / (4 * pmp(full)):.5f}"
    )

    rng = np.random.default_rng(0)
    worst = 0.0
    for _ in range(50):
        g = rng.uniform(0, 1100, 72)
        v = cell_voltage_at_current(CELL, g, 25.0, grid)
        parts = sum(pmp((grid, v[k])) for k in range(72))
        worst = max(worst, pmp(substring(g, grid)) / parts)
    print(f"largest assembly / sum of parts over 50 random substrings: {worst:.4f}")


if __name__ == "__main__":
    main()
