"""IV curves and how they combine.

Every element (cell, diode group, module, string, array) is an ``IVCurve``:
voltage sampled on a strictly increasing current grid. Series connection adds
voltages at equal current; parallel connection adds currents at equal voltage.

No function here lets ``np.interp`` repeat an end value: every interpolation
is evaluated inside the range covered by its sample points.

Units: current A, voltage V, power W.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

#: Allowed upward step in voltage (V) between neighbouring samples.
VOLTAGE_NOISE = 1e-9

#: Slope (V/A) added to flat parts of a curve so voltage can be inverted.
SLOPE = 1e-9


@dataclass(frozen=True, eq=False)
class IVCurve:
    """Voltage of an element on a strictly increasing current grid."""

    current: np.ndarray
    voltage: np.ndarray

    def __post_init__(self):
        current = np.asarray(self.current, dtype=float)
        voltage = np.asarray(self.voltage, dtype=float)
        if current.ndim != 1 or voltage.ndim != 1:
            raise ValueError("current and voltage must be 1-D arrays")
        if current.size != voltage.size:
            raise ValueError(
                f"current and voltage differ in length ({current.size} and "
                f"{voltage.size})"
            )
        if current.size < 2:
            raise ValueError("a curve needs at least 2 points")
        if not np.all(np.isfinite(current)) or not np.all(np.isfinite(voltage)):
            raise ValueError("current and voltage must be finite")
        if not np.all(np.diff(current) > 0):
            raise ValueError("current must be strictly increasing")
        if not np.all(np.diff(voltage) <= VOLTAGE_NOISE):
            raise ValueError("voltage must not increase with current")
        object.__setattr__(self, "current", current)
        object.__setattr__(self, "voltage", voltage)


def bypass(curve: IVCurve, diode_voltage: float = 0.5) -> IVCurve:
    """Ideal bypass diode across the group of cells that ``curve`` describes.

    Voltage is floored at ``-diode_voltage``. Apply it to the group the diode
    spans, before that group is added in series with others (invariant 1).
    """
    if diode_voltage < 0:
        raise ValueError(f"diode_voltage must be >= 0, got {diode_voltage}")
    return IVCurve(curve.current, np.maximum(curve.voltage, -diode_voltage))


def series(curves: Sequence[IVCurve], n_points: int = 600) -> IVCurve:
    """Curves in series: voltages added at equal current.

    The common current grid covers only the range all operands share, which
    must include zero current and some positive current.
    """
    curves = list(curves)
    if not curves:
        raise ValueError("series needs at least one curve")
    if len(curves) == 1:
        return curves[0]
    lo = max(c.current[0] for c in curves)
    hi = min(c.current[-1] for c in curves)
    if not lo <= 0 < hi:
        raise ValueError(
            f"the operands' shared current range [{lo}, {hi}] A does not include "
            "zero and positive current"
        )
    grid = np.linspace(lo, hi, n_points)
    # grid lies inside every operand's current range: no end value is repeated.
    voltage = sum(np.interp(grid, c.current, c.voltage) for c in curves)
    return IVCurve(grid, voltage)


def _current_at_voltage(curve: IVCurve, v_grid: np.ndarray) -> np.ndarray:
    """Current of ``curve`` at increasing voltages inside its voltage range."""
    strict = curve.voltage - SLOPE * (curve.current - curve.current[0])
    return np.interp(v_grid, strict[::-1], curve.current[::-1])


def parallel(curves: Sequence[IVCurve], n_points: int = 600) -> IVCurve:
    """Curves in parallel: currents added at equal voltage.

    Only the voltage range all operands share is used; it must include
    positive voltage.
    """
    curves = list(curves)
    if not curves:
        raise ValueError("parallel needs at least one curve")
    if len(curves) == 1:
        return curves[0]
    v_lo = max(c.voltage.min() for c in curves)
    v_hi = min(c.voltage.max() for c in curves)
    if v_hi <= 0 or v_lo >= v_hi:
        raise ValueError(
            f"the operands' shared voltage range [{v_lo}, {v_hi}] V does not "
            "include positive voltage"
        )
    v_grid = np.unique(np.concatenate([np.clip(c.voltage, v_lo, v_hi) for c in curves]))
    # v_grid lies inside every operand's voltage range: no end value is repeated.
    total = sum(_current_at_voltage(c, v_grid) for c in curves)
    # total falls as voltage rises; reverse so current increases.
    x = total[::-1]
    if not np.all(np.diff(x) > 0):
        x = x + SLOPE * np.arange(x.size)
    grid = np.linspace(total.min(), total.max(), n_points)
    # grid lies inside [x[0], x[-1]]: no end value is repeated.
    return IVCurve(grid, np.interp(grid, x, v_grid[::-1]))


def max_power_point(curve: IVCurve) -> tuple[float, float, float]:
    """Current, voltage and power at the maximum power point.

    Only points with non-negative current and voltage count. The best sample
    is refined with a parabola through it and its two neighbours.
    Returns ``(0.0, 0.0, 0.0)`` if no point has positive power.
    """
    current, voltage = curve.current, curve.voltage
    valid = (current >= 0) & (voltage >= 0)
    power = np.where(valid, current * voltage, 0.0)
    k = int(np.argmax(power))
    if power[k] <= 0:
        return 0.0, 0.0, 0.0
    if 0 < k < power.size - 1 and valid[k - 1] and valid[k + 1]:
        v3 = voltage[k - 1 : k + 2]
        i3 = current[k - 1 : k + 2]
        if np.ptp(v3) > 0:
            a = np.polyfit(v3, power[k - 1 : k + 2], 2)
            if a[0] < 0:
                v_peak = -a[1] / (2 * a[0])
                if v3.min() <= v_peak <= v3.max():
                    # v_peak lies inside the three points; reverse so voltage increases.
                    i_peak = np.interp(v_peak, v3[::-1], i3[::-1])
                    return float(i_peak), float(v_peak), float(np.polyval(a, v_peak))
    return float(current[k]), float(voltage[k]), float(power[k])
