"""Cell parameters and cell curves (plan docs/plans/electrical-core.md, 4.3 and 10.5)."""

import dataclasses

import numpy as np
import pytest
from pvlib import pvsystem, singlediode

from cactus.electrical import (
    bypass,
    cell_current_grid,
    cell_curves,
    cell_voltage_at_current,
    current_grid,
    max_power_point,
    parallel,
    series,
)

BREAKDOWN = {
    "breakdown_voltage": -15.0,
    "breakdown_factor": 0.002,
    "breakdown_exp": 3.28,
}


def desoto(params, irradiance, temperature=25.0):
    return pvsystem.calcparams_desoto(
        irradiance,
        temperature,
        alpha_sc=params.alpha_sc,
        a_ref=params.a_ref,
        I_L_ref=params.I_L_ref,
        I_o_ref=params.I_o_ref,
        R_sh_ref=params.R_sh_ref,
        R_s=params.R_s,
        EgRef=params.EgRef,
        dEgdT=params.dEgdT,
    )


def test_cell_scaling(cell):
    rel = 1e-12
    assert cell.I_L_ref == pytest.approx(5.671496955, rel=rel)
    assert cell.I_o_ref == pytest.approx(8.85e-12, rel=rel)
    assert cell.R_s == pytest.approx(0.202623823 / 36, rel=rel)
    assert cell.R_sh_ref == pytest.approx(767.4762928 / 36, rel=rel)
    assert cell.a_ref == pytest.approx(1.828557411 / 72, rel=rel)
    assert cell.alpha_sc == pytest.approx(0.00017, rel=rel)


def test_cell_matches_pvlib(cell, grid):
    (curve,) = cell_curves(cell, 1000.0, 25.0, grid)
    p_ref = float(singlediode.bishop88_mpp(*desoto(cell, 1000.0), **BREAKDOWN)[2])
    assert p_ref == pytest.approx(3.1321, abs=1e-4)
    assert max_power_point(curve)[2] == pytest.approx(p_ref, rel=5e-4)
    v_oc = np.interp(0.0, curve.current, curve.voltage)
    assert v_oc == pytest.approx(0.6903, abs=1e-3)


def test_cell_reaches_breakdown(cell, grid):
    """Invariant 8: a lit cell's curve reaches its breakdown region."""
    v = cell_voltage_at_current(cell, 1000.0, 25.0, grid)[0]
    assert v.min() < -13.0


def test_dark_cell_is_finite(cell, grid):
    v = cell_voltage_at_current(cell, 0.0, 25.0, grid)[0]
    assert np.all(np.isfinite(v))
    assert v[-1] == -15.0


def test_input_errors(cell, grid):
    with pytest.raises(ValueError):
        cell_voltage_at_current(cell, -1.0, 25.0, grid)
    bad_grid = np.array([0.0, 1.0, 1.0, 2.0])
    with pytest.raises(ValueError):
        cell_voltage_at_current(cell, 1000.0, 25.0, bad_grid)


def test_wide_negative_grid_is_finite(cell):
    wide = current_grid(-50.0, 9.0, 600)
    v = cell_voltage_at_current(cell, 1000.0, 25.0, wide)[0]
    assert np.all(np.isfinite(v))
    assert v[0] > np.interp(0.0, wide, v)


def test_no_bypass_reverse_bias(cell, grid):
    irradiance = np.full(24, 1000.0)
    irradiance[0] = 0.0
    curves = cell_curves(cell, irradiance, 25.0, grid)
    string = series(curves)
    assert string.voltage.min() < -14.0
    assert curves[0].voltage.min() == -15.0


# Addendum A (plan section 10.5): grids and dark cells.

V_OC_CELL = 0.69029


def at_zero_current(curve):
    return float(np.interp(0.0, curve.current, curve.voltage))


def module_values(module, irradiance):
    return pvsystem.calcparams_desoto(
        irradiance,
        25.0,
        alpha_sc=module["alpha_sc"],
        a_ref=module["a_ref"],
        I_L_ref=module["I_L_ref"],
        I_o_ref=module["I_o_ref"],
        R_sh_ref=module["R_sh_ref"],
        R_s=module["R_s"],
        EgRef=1.121,
        dEgdT=-0.0002677,
    )


def substring_on(cell, irradiance, grid, n_points=600):
    curves = cell_curves(cell, irradiance, 25.0, grid)
    groups = [bypass(series(curves[g * 24 : (g + 1) * 24], n_points)) for g in range(3)]
    return series(groups, n_points)


def test_grid_spanning_zero_must_contain_zero(cell):
    """Invariant 2: open-circuit voltage is never interpolated across a step."""
    with pytest.raises(ValueError):
        cell_voltage_at_current(cell, 1000.0, 25.0, np.linspace(-3.0, 9.0, 600))


def test_dark_cell_at_zero_current(cell, grid):
    (dark,) = cell_curves(cell, 0.0, 25.0, grid)
    assert at_zero_current(dark) == pytest.approx(0.0, abs=1e-6)


def test_string_with_dark_cell_open_circuit(cell, grid):
    irradiance = np.full(24, 1000.0)
    irradiance[0] = 0.0
    curves = cell_curves(cell, irradiance, 25.0, grid)
    lit = at_zero_current(curves[1])
    assert lit == pytest.approx(V_OC_CELL, abs=1e-4)
    assert at_zero_current(series(curves)) == pytest.approx(23 * lit, abs=1e-3)


def test_substring_with_dark_cell(substring):
    irradiance = np.full(72, 1000.0)
    irradiance[0] = 0.0
    shaded = substring(irradiance)
    assert at_zero_current(shaded) == pytest.approx(49.010, abs=0.01)
    assert max_power_point(shaded)[2] == pytest.approx(147.64, rel=1e-3)


def test_night(cell):
    dark = np.zeros(72)
    night = substring_on(cell, dark, cell_current_grid(cell, dark, 25.0))
    assert max_power_point(night) == (0.0, 0.0, 0.0)
    assert at_zero_current(night) == pytest.approx(0.0, abs=1e-6)
    assert max_power_point(parallel([night, night])) == (0.0, 0.0, 0.0)


def test_low_irradiance_sweep_runs(cell, grid):
    """Build report question 4: sampled currents stay strictly increasing."""
    for temperature in (-20.0, 25.0, 85.0):
        for irradiance in (0.0, 1e-6, 0.05, 0.1, 1.0):
            v = cell_voltage_at_current(cell, irradiance, temperature, grid)[0]
            assert np.all(np.isfinite(v))
            assert np.all(np.diff(v) <= 1e-9)


def test_infinite_shunt_rejected(cell, grid):
    no_shunt = dataclasses.replace(cell, R_sh_ref=float("inf"))
    with pytest.raises(ValueError):
        cell_voltage_at_current(no_shunt, 1000.0, 25.0, grid)


def test_cell_current_grid(cell):
    g = cell_current_grid(cell, 100.0, 25.0)
    assert g.size == 600
    assert g[0] == pytest.approx(-0.28357485, rel=1e-8)
    assert g[-1] == pytest.approx(0.90743951, rel=1e-8)
    assert np.count_nonzero(g == 0.0) == 1
    dark = cell_current_grid(cell, np.zeros(3), 25.0)
    assert dark[0] == pytest.approx(-0.0028357485, rel=1e-8)
    assert dark[-1] == pytest.approx(0.0090743951, rel=1e-8)


def test_low_light_accuracy(cell):
    irradiance = np.random.default_rng(0).uniform(70.0, 100.0, 72)
    coarse = substring_on(cell, irradiance, cell_current_grid(cell, irradiance, 25.0))
    fine_grid = cell_current_grid(cell, irradiance, 25.0, 6000)
    fine = substring_on(cell, irradiance, fine_grid, 6000)
    p_fine = max_power_point(fine)[2]
    assert p_fine == pytest.approx(16.288, abs=0.005)
    assert max_power_point(coarse)[2] == pytest.approx(p_fine, rel=1e-3)


@pytest.mark.parametrize(
    ("irradiance", "expected"), [(100.0, 21.352), (30.0, 6.076), (10.0, 1.920)]
)
def test_uniform_low_light_matches_pvlib(cell, d001_module, irradiance, expected):
    uniform = np.full(72, irradiance)
    sub = substring_on(cell, uniform, cell_current_grid(cell, uniform, 25.0))
    p_ref = float(singlediode.bishop88_mpp(*module_values(d001_module, irradiance))[2])
    assert p_ref / 2 == pytest.approx(expected, abs=1e-3)
    assert max_power_point(sub)[2] == pytest.approx(p_ref / 2, rel=5e-4)
