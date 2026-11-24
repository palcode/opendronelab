# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Pure safety checks used by mission_node.

No ROS imports, so the same functions mission_node calls can be unit-tested
on a plain host (CI) as well as in the dev image.
"""
import math

# Same margin as drone_flight_cpp (square_flight.cpp): land when the measured
# altitude is more than this above max_altitude.
ALTITUDE_MARGIN_M = 0.5


def as_float_param(name, value):
    """Return a numeric parameter as float.

    Integers are accepted (``target_altitude:=3``). bool and str are rejected
    so a typo such as ``target_altitude:=true`` fails loudly.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{name} must be a number, got {value!r}')
    return float(value)


def validate_limits(target_altitude, max_altitude, hover_duration,
                    max_mission_time, max_xy_drift):
    """Raise ValueError unless every mission limit is finite and sane.

    target_altitude must satisfy 0 < target <= max_altitude. NaN, inf, zero
    and negative targets are rejected (a negative NED target would be a
    setpoint below ground).
    """
    if not (math.isfinite(max_altitude) and max_altitude > 0.0):
        raise ValueError(f'max_altitude must be finite and > 0, got {max_altitude}')
    if not math.isfinite(target_altitude):
        raise ValueError(f'target_altitude must be finite, got {target_altitude}')
    if target_altitude <= 0.0:
        raise ValueError(f'target_altitude must be > 0 m, got {target_altitude}')
    if target_altitude > max_altitude:
        raise ValueError(
            f'Target altitude {target_altitude}m exceeds max {max_altitude}m')
    if not (math.isfinite(hover_duration) and hover_duration >= 0.0):
        raise ValueError(f'hover_duration must be finite and >= 0, got {hover_duration}')
    if not (math.isfinite(max_mission_time) and max_mission_time > 0.0):
        raise ValueError(f'max_mission_time must be finite and > 0, got {max_mission_time}')
    if not (math.isfinite(max_xy_drift) and max_xy_drift > 0.0):
        raise ValueError(f'max_xy_drift must be finite and > 0, got {max_xy_drift}')


def xy_drift(x, y, start_x, start_y):
    """Horizontal distance from the hover start (NaN in, NaN out)."""
    dx = x - start_x
    dy = y - start_y
    return math.sqrt(dx * dx + dy * dy)


def drift_exceeded(drift, max_xy_drift):
    """True when the drift is over the limit or not a finite number."""
    return not math.isfinite(drift) or drift > max_xy_drift


def altitude_exceeded(z_ned, max_altitude, margin=ALTITUDE_MARGIN_M):
    """True when the measured NED z is non-finite or above max + margin."""
    return not math.isfinite(z_ned) or -z_ned > max_altitude + margin


def airborne_violation(x, y, z, max_altitude, hover_start=None,
                       max_xy_drift=None):
    """Return a reason string when the airborne checks fail, else None.

    Checked in this order: non-finite position, altitude above
    max_altitude + ALTITUDE_MARGIN_M, then (when hover_start is given) XY
    drift above max_xy_drift. Any reason means: land (the existing failsafe).
    """
    if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
        return f'non-finite position ({x}, {y}, {z})'
    if altitude_exceeded(z, max_altitude):
        return (f'altitude {-z:.2f}m exceeds max {max_altitude}m '
                f'(+{ALTITUDE_MARGIN_M}m margin)')
    if hover_start is not None:
        drift = xy_drift(x, y, hover_start[0], hover_start[1])
        if drift_exceeded(drift, max_xy_drift):
            return f'XY drift {drift:.2f}m exceeds limit {max_xy_drift}m'
    return None


def timed_out(now_s, start_s, limit_s):
    """True when more than limit_s has passed since start_s."""
    if start_s is None:
        return False
    return (now_s - start_s) > limit_s
