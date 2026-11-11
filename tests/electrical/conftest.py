"""Shared fixtures for the electrical tests (plan docs/plans/electrical-core.md, 4.3)."""

import numpy as np
import pytest

from cactus.electrical import (
    bypass,
    cell_curves,
    cell_parameters_from_module,
    series,
)

# IPV_Workbench device D001: 144 half-cell mono-Si module, module-level values.
D001 = {
    "I_L_ref": 11.34299391,
    "I_o_ref": 1.77e-11,
    "R_s": 0.202623823,
    "R_sh_ref": 767.4762928,
    "a_ref": 1.828557411,
    "alpha_sc": 0.00034,
    "n_series": 72,
    "n_parallel": 2,
}

TEMPERATURE = 25.0
GROUP_SIZE = 24
N_GROUPS = 3


@pytest.fixture
def d001_module():
    return dict(D001)


@pytest.fixture
def cell(d001_module):
    return cell_parameters_from_module(**d001_module)


@pytest.fixture
def grid():
    return np.linspace(-3.0, 9.0, 600)


def make_substring(cell, irradiance, grid):
    """72 cells in three groups of 24, each group bypassed, the groups in series."""
    curves = cell_curves(cell, irradiance, TEMPERATURE, grid)
    groups = [
        bypass(series(curves[g * GROUP_SIZE : (g + 1) * GROUP_SIZE]))
        for g in range(N_GROUPS)
    ]
    return series(groups)


@pytest.fixture
def substring(cell, grid):
    """Factory: substring(irradiance of 72 cells) -> IVCurve."""
    return lambda irradiance: make_substring(cell, irradiance, grid)


@pytest.fixture
def unshaded(substring):
    return substring(np.full(72, 1000.0))
