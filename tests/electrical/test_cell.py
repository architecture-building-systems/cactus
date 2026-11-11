"""Cell parameters and cell curves (plan docs/plans/electrical-core.md, 4.3)."""

import numpy as np
import pytest
from pvlib import pvsystem, singlediode

from cactus.electrical import (
    cell_curves,
    cell_voltage_at_current,
    max_power_point,
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
    wide = np.linspace(-50.0, 9.0, 600)
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
