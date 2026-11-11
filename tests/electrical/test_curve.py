"""Combining curves (plan docs/plans/electrical-core.md, 4.3)."""

import numpy as np
import pytest
from pvlib import pvsystem, singlediode

from cactus.electrical import (
    IVCurve,
    bypass,
    cell_curves,
    max_power_point,
    parallel,
    series,
)

GROUP_SIZE = 24


def pmp(curve):
    return max_power_point(curve)[2]


def string_of(curve, n):
    return series([curve] * n)


def test_series_identity(cell, grid):
    """Invariant 3: N identical cells in series give N times the cell voltage."""
    (one,) = cell_curves(cell, 1000.0, 25.0, grid)
    ten = series([one] * 10)
    np.testing.assert_allclose(ten.current, grid, rtol=0, atol=1e-12)
    np.testing.assert_allclose(ten.voltage, 10 * one.voltage, rtol=0, atol=1e-9)


def test_parallel_identity(unshaded):
    """Invariant 3: N identical strings in parallel give N times the current."""
    three = parallel([unshaded] * 3)
    i1, _, p1 = max_power_point(unshaded)
    i3, _, p3 = max_power_point(three)
    assert p3 == pytest.approx(3 * p1, rel=2e-4)
    assert i3 == pytest.approx(3 * i1, rel=1e-3)


def _current_at(curve, v):
    strict = curve.voltage - 1e-9 * (curve.current - curve.current[0])
    return np.interp(v, strict[::-1], curve.current[::-1])


def test_parallel_identity_full_curve(unshaded):
    """Invariant 3: N identical strings in parallel give N times the current at
    every voltage (Justin, 2026-11-11: relative tolerance 1e-3)."""
    three = parallel([unshaded] * 3)
    v_oc = np.interp(0.0, unshaded.current, unshaded.voltage)
    v = np.linspace(0.0, 0.99 * v_oc, 200)
    np.testing.assert_allclose(
        _current_at(three, v), 3 * _current_at(unshaded, v), rtol=1e-3
    )


def test_module_matches_pvlib(d001_module, unshaded):
    m = d001_module
    module = parallel([unshaded, unshaded])
    values = pvsystem.calcparams_desoto(
        1000.0,
        25.0,
        alpha_sc=m["alpha_sc"],
        a_ref=m["a_ref"],
        I_L_ref=m["I_L_ref"],
        I_o_ref=m["I_o_ref"],
        R_sh_ref=m["R_sh_ref"],
        R_s=m["R_s"],
        EgRef=1.121,
        dEgdT=-0.0002677,
    )
    p_ref = float(singlediode.bishop88_mpp(*values)[2])
    assert p_ref == pytest.approx(451.03, abs=0.01)
    assert pmp(module) == pytest.approx(p_ref, rel=5e-4)


def test_bypass_per_group(cell, grid, unshaded):
    """Invariant 1: the bypass diode clips the group it spans, inside the series sum."""
    irradiance = np.full(72, 1000.0)
    irradiance[0] = 200.0
    curves = cell_curves(cell, irradiance, 25.0, grid)
    groups = [
        bypass(series(curves[g * GROUP_SIZE : (g + 1) * GROUP_SIZE])) for g in range(3)
    ]
    shaded = series(groups)
    ratio = pmp(shaded) / pmp(unshaded)
    assert 0.650 <= ratio <= 0.660
    assert groups[0].voltage.min() >= -0.5


def test_power_bound(cell, grid, substring):
    """Invariant 4: an assembly never exceeds the sum of its parts' maximum powers."""
    rng = np.random.default_rng(0)
    for _ in range(50):
        irradiance = rng.uniform(0, 1100, 72)
        parts = sum(pmp(c) for c in cell_curves(cell, irradiance, 25.0, grid))
        assert pmp(substring(irradiance)) <= parts + 1e-6


def test_unequal_parallel_strings(unshaded):
    array = parallel([string_of(unshaded, 4), string_of(unshaded, 11)])
    ratio = pmp(array) / (15 * pmp(unshaded))
    assert 0.53 <= ratio <= 0.58


def test_equal_parallel_strings(unshaded):
    array = parallel([string_of(unshaded, 10)] * 5)
    ratio = pmp(array) / (50 * pmp(unshaded))
    assert ratio == pytest.approx(1.0, rel=1e-3)


def test_series_of_parallel(unshaded):
    tier = parallel([unshaded, unshaded])
    stack = series([tier, tier])
    assert pmp(stack) == pytest.approx(4 * pmp(unshaded), rel=5e-4)


def test_series_needs_shared_range():
    """Invariant 2: no silent extrapolation when the current ranges do not cover zero."""
    a = IVCurve(np.array([-1.0, 1.0, 2.0]), np.array([1.0, 0.5, 0.0]))
    b = IVCurve(np.array([0.5, 1.5, 3.0]), np.array([1.0, 0.5, 0.0]))
    with pytest.raises(ValueError):
        series([a, b])
    with pytest.raises(ValueError):
        series([])


def test_parallel_needs_shared_range():
    """Invariant 2: parallel raises if the operands share no positive voltage."""
    current = np.array([0.0, 1.0, 2.0])
    dead = IVCurve(current, np.array([0.0, -0.5, -1.0]))
    with pytest.raises(ValueError):
        parallel([dead, dead])
    high = IVCurve(current, np.array([3.0, 2.5, 2.0]))
    low = IVCurve(current, np.array([1.0, 0.5, 0.0]))
    with pytest.raises(ValueError):
        parallel([high, low])
    with pytest.raises(ValueError):
        parallel([])


def test_ivcurve_validation():
    with pytest.raises(ValueError):
        IVCurve(np.array([0.0, 2.0, 1.0]), np.array([1.0, 0.5, 0.0]))
    with pytest.raises(ValueError):
        IVCurve(np.array([0.0, 1.0, 2.0]), np.array([0.0, 0.5, 1.0]))
    with pytest.raises(ValueError):
        IVCurve(np.array([0.0, 1.0, 2.0]), np.array([1.0, 0.0]))


def test_mpp_of_dead_curve():
    dead = IVCurve(np.array([-1.0, 0.0, 1.0, 2.0]), np.array([0.0, -0.1, -0.2, -0.5]))
    assert max_power_point(dead) == (0.0, 0.0, 0.0)
