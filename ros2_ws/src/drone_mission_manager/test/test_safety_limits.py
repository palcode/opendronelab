# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Unit tests for the safety checks mission_node actually calls.

Imports drone_mission_manager.safety (no ROS needed), so these run in CI.
Node-level wiring is covered by test_mission_node.py in the dev image.
"""
import math

import pytest

from drone_mission_manager import safety

NAN = float('nan')
INF = float('inf')


def _limits(**over):
    kw = dict(target_altitude=3.0, max_altitude=4.0, hover_duration=10.0,
              max_mission_time=60.0, max_xy_drift=2.0)
    kw.update(over)
    return kw


@pytest.mark.parametrize('target', [0.1, 1.0, 3.0, 3.9, 4.0])
def test_valid_targets_accepted(target):
    safety.validate_limits(**_limits(target_altitude=target))


@pytest.mark.parametrize('target', [4.0001, 4.1, 10.0, NAN, INF, -INF,
                                    0.0, -0.0, -1.0, -3.0])
def test_invalid_targets_rejected(target):
    with pytest.raises(ValueError):
        safety.validate_limits(**_limits(target_altitude=target))


@pytest.mark.parametrize('field,value', [
    ('max_altitude', NAN), ('max_altitude', 0.0), ('max_altitude', -4.0),
    ('max_altitude', INF),
    ('hover_duration', NAN), ('hover_duration', -1.0),
    ('max_mission_time', NAN), ('max_mission_time', 0.0), ('max_mission_time', INF),
    ('max_xy_drift', NAN), ('max_xy_drift', 0.0), ('max_xy_drift', INF),
])
def test_invalid_other_limits_rejected(field, value):
    with pytest.raises(ValueError):
        safety.validate_limits(**_limits(**{field: value}))


def test_hover_duration_zero_allowed():
    safety.validate_limits(**_limits(hover_duration=0.0))


@pytest.mark.parametrize('value,expected', [(3, 3.0), (3.5, 3.5), (0, 0.0)])
def test_as_float_param_accepts_int_and_float(value, expected):
    out = safety.as_float_param('target_altitude', value)
    assert isinstance(out, float) and out == expected


@pytest.mark.parametrize('value', [True, False, '3', None, [3.0]])
def test_as_float_param_rejects_non_numbers(value):
    with pytest.raises(ValueError):
        safety.as_float_param('target_altitude', value)


@pytest.mark.parametrize('x,y,expected', [
    (0.0, 0.0, 0.0), (1.0, 0.0, 1.0), (0.0, 1.0, 1.0), (3.0, 4.0, 5.0),
    (-1.0, 0.0, 1.0),
])
def test_xy_drift(x, y, expected):
    assert safety.xy_drift(x, y, 0.0, 0.0) == pytest.approx(expected)
    # Relative to a non-zero start too.
    assert safety.xy_drift(x + 2.0, y - 1.0, 2.0, -1.0) == pytest.approx(expected)


@pytest.mark.parametrize('drift', [0.0, 0.5, 1.0, 1.5, 2.0])
def test_drift_within_limit(drift):
    assert not safety.drift_exceeded(drift, 2.0)


@pytest.mark.parametrize('drift', [2.0001, 2.1, 3.0, 5.0, NAN, INF])
def test_drift_over_limit_or_non_finite(drift):
    assert safety.drift_exceeded(drift, 2.0)


def test_nan_position_drift_is_nan_and_triggers():
    """Regression: sqrt(NaN) > max is False, so NaN used to bypass the abort."""
    d = safety.xy_drift(NAN, 0.0, 0.0, 0.0)
    assert math.isnan(d)
    assert safety.drift_exceeded(d, 2.0)


@pytest.mark.parametrize('z,exceeded', [
    (0.0, False), (-3.0, False), (-4.0, False), (-4.5, False),
    (-4.5001, True), (-6.0, True), (NAN, True), (-INF, True), (INF, True),
])
def test_altitude_exceeded(z, exceeded):
    assert safety.altitude_exceeded(z, 4.0) is exceeded


def test_altitude_margin_matches_cpp_node():
    assert safety.ALTITUDE_MARGIN_M == 0.5


def test_airborne_violation_ok():
    assert safety.airborne_violation(0.1, -0.2, -3.0, 4.0) is None
    assert safety.airborne_violation(0.1, -0.2, -3.0, 4.0, (0.0, 0.0), 2.0) is None


@pytest.mark.parametrize('pos', [(NAN, 0.0, -3.0), (0.0, NAN, -3.0),
                                 (0.0, 0.0, NAN), (INF, 0.0, -3.0)])
def test_airborne_violation_non_finite(pos):
    reason = safety.airborne_violation(*pos, 4.0, (0.0, 0.0), 2.0)
    assert reason is not None and 'non-finite' in reason
    # Also without a hover start (TAKEOFF).
    assert safety.airborne_violation(*pos, 4.0) is not None


def test_airborne_violation_altitude():
    reason = safety.airborne_violation(0.0, 0.0, -4.6, 4.0)
    assert reason is not None and 'altitude' in reason


def test_airborne_violation_drift_only_with_hover_start():
    assert safety.airborne_violation(3.0, 0.0, -3.0, 4.0) is None
    reason = safety.airborne_violation(3.0, 0.0, -3.0, 4.0, (0.0, 0.0), 2.0)
    assert reason is not None and 'drift' in reason


def test_airborne_violation_non_finite_hover_start():
    reason = safety.airborne_violation(0.0, 0.0, -3.0, 4.0, (NAN, 0.0), 2.0)
    assert reason is not None and 'drift' in reason


@pytest.mark.parametrize('now,start,limit,expected', [
    (100.0, None, 60.0, False),
    (100.0, 50.0, 60.0, False),
    (110.0, 50.0, 60.0, False),
    (110.001, 50.0, 60.0, True),
    (500.0, 50.0, 60.0, True),
])
def test_timed_out(now, start, limit, expected):
    assert safety.timed_out(now, start, limit) is expected
