"""Cell parameters and cell IV curves from the single-diode model.

The cell model is pvlib's De Soto parameters (``calcparams_desoto``) with the
Bishop reverse-bias term (``singlediode.bishop88``). Datasheet values for a
whole module are converted to one cell first, and the breakdown voltage
applies per cell (invariant 8).

Units: current A, voltage V, irradiance W/m2, temperature degC, resistance ohm.
"""

from dataclasses import dataclass

import numpy as np
from pvlib import pvsystem, singlediode

from .curve import IVCurve


@dataclass(frozen=True)
class CellParameters:
    """Single-diode reference parameters of one cell."""

    I_L_ref: float
    I_o_ref: float
    R_s: float
    R_sh_ref: float
    a_ref: float
    alpha_sc: float
    EgRef: float = 1.121
    dEgdT: float = -0.0002677
    breakdown_voltage: float = -15.0
    breakdown_factor: float = 0.002
    breakdown_exp: float = 3.28


def cell_parameters_from_module(
    I_L_ref: float,
    I_o_ref: float,
    R_s: float,
    R_sh_ref: float,
    a_ref: float,
    alpha_sc: float,
    n_series: int,
    n_parallel: int,
    **other: float,
) -> CellParameters:
    """Convert module-level single-diode parameters to one cell.

    For ``n_series`` cells in series and ``n_parallel`` in parallel:
    photocurrent, saturation current and ``alpha_sc`` divide by
    ``n_parallel``; series and shunt resistance multiply by
    ``n_parallel / n_series``; ``a_ref`` divides by ``n_series``.
    ``other`` passes ``EgRef``, ``dEgdT`` and the breakdown values through
    unscaled; they are per cell.
    """
    if n_series < 1 or n_parallel < 1:
        raise ValueError(
            f"n_series and n_parallel must be >= 1, got {n_series} and {n_parallel}"
        )
    return CellParameters(
        I_L_ref=I_L_ref / n_parallel,
        I_o_ref=I_o_ref / n_parallel,
        R_s=R_s * n_parallel / n_series,
        R_sh_ref=R_sh_ref * n_parallel / n_series,
        a_ref=a_ref / n_series,
        alpha_sc=alpha_sc / n_parallel,
        **other,
    )


def cell_voltage_at_current(
    params: CellParameters,
    irradiance,
    temperature,
    current_grid,
    n_sample: int = 400,
) -> np.ndarray:
    """Voltage of each cell on a shared current grid.

    ``irradiance`` is a scalar or 1-D array (one value per cell);
    ``temperature`` is broadcast to it. Returns an array of shape
    ``(n_cells, len(current_grid))``.

    For currents above the highest current the sampled curve reaches, the
    voltage is the breakdown voltage. This is a modelling choice: with De Soto
    parameters a dark cell has infinite shunt resistance and the Bishop term
    vanishes, so without it a dark cell could carry no reverse current at all.
    """
    irradiance = np.atleast_1d(np.asarray(irradiance, dtype=float))
    if irradiance.ndim != 1:
        raise ValueError("irradiance must be a scalar or a 1-D array")
    if np.any(irradiance < 0) or not np.all(np.isfinite(irradiance)):
        raise ValueError("irradiance must be finite and non-negative")
    temperature = np.broadcast_to(
        np.asarray(temperature, dtype=float), irradiance.shape
    )
    grid = np.asarray(current_grid, dtype=float)
    if grid.ndim != 1 or grid.size < 2 or not np.all(np.diff(grid) > 0):
        raise ValueError("current_grid must be a strictly increasing 1-D array")

    values = pvsystem.calcparams_desoto(
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
    il, i0, rs, rsh, nnsvth = (
        np.broadcast_to(np.asarray(x, dtype=float), irradiance.shape) for x in values
    )
    breakdown = {
        "breakdown_voltage": params.breakdown_voltage,
        "breakdown_factor": params.breakdown_factor,
        "breakdown_exp": params.breakdown_exp,
    }

    i_neg = max(0.0, -grid[0])
    vd_max = nnsvth * np.log((il + 1.05 * i_neg + 1e-12) / i0 + 1.0)
    half = n_sample // 2
    reverse = np.linspace(0.97 * params.breakdown_voltage, 0.0, half, endpoint=False)
    u = np.linspace(0.0, 1.0, half)

    out = np.empty((irradiance.size, grid.size))
    for k in range(irradiance.size):
        forward = vd_max[k] * (1.0 - (1.0 - u) ** 2)
        vd = np.concatenate([reverse, forward])
        i, v, _ = singlediode.bishop88(
            vd, il[k], i0[k], rs[k], rsh[k], nnsvth[k], **breakdown
        )
        # Current falls as diode voltage rises; reverse so current increases.
        i, v = i[::-1], v[::-1]
        if grid[0] < i[0]:
            raise ValueError(
                f"current_grid starts at {grid[0]} A, below the lowest sampled "
                f"current {i[0]} A of cell {k}"
            )
        # Breakdown rule: above the highest sampled current the cell sits at its
        # breakdown voltage. This is the only place an end value is set by np.interp.
        out[k] = np.interp(grid, i, v, right=params.breakdown_voltage)
    return out


def cell_curves(
    params: CellParameters, irradiance, temperature, current_grid
) -> list[IVCurve]:
    """One ``IVCurve`` per cell on a shared current grid."""
    grid = np.asarray(current_grid, dtype=float)
    voltages = cell_voltage_at_current(params, irradiance, temperature, grid)
    return [IVCurve(grid.copy(), v) for v in voltages]
