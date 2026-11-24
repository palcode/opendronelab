# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""mission_node wiring tests against the real node (needs rclpy + px4_msgs).

Runs in the dev image (SCENARIOS=pytest ./scripts/run-regression.sh). The
pure checks are in test_safety_limits.py, which also runs in CI.
"""
import math
from types import SimpleNamespace

import pytest

rclpy = pytest.importorskip('rclpy')
pytest.importorskip('px4_msgs.msg')

from rclpy.parameter import Parameter  # noqa: E402

from drone_mission_manager import mission_node as mn  # noqa: E402

NAN = float('nan')
ARMED = 2
OFFBOARD = 14


@pytest.fixture(scope='module', autouse=True)
def ros_context():
    rclpy.init()
    yield
    rclpy.shutdown()


@pytest.fixture
def make_node():
    nodes = []

    def _make(**params):
        overrides = [Parameter(k, value=v) for k, v in params.items()]
        node = mn.MissionNode(parameter_overrides=overrides)
        node.lands = []
        node.land = lambda: node.lands.append(node.state)
        node.fake_now = 1000.0
        node.now_s = lambda: node.fake_now
        nodes.append(node)
        return node

    yield _make
    for node in nodes:
        node.destroy_node()


def _status(arming=ARMED, nav=OFFBOARD):
    return SimpleNamespace(arming_state=arming, nav_state=nav)


def _pos(x=0.0, y=0.0, z=-3.0, z_valid=True):
    return SimpleNamespace(x=x, y=y, z=z, z_valid=z_valid)


def _hovering(node, x=0.0, y=0.0, z=-3.0):
    node.vehicle_status = _status()
    node.vehicle_local_position = _pos(x, y, z)
    node.state = 'HOVER'
    node.mission_start_time = node.fake_now
    node.hover_start_time = node.fake_now
    node.hover_start_position = (0.0, 0.0, -3.0)


def test_integer_target_altitude_accepted(make_node):
    """target_altitude:=3 used to raise InvalidParameterTypeException."""
    node = make_node(target_altitude=3, max_altitude=4)
    assert node.target_altitude == 3.0 and isinstance(node.target_altitude, float)
    assert node.max_altitude == 4.0 and isinstance(node.max_altitude, float)


@pytest.mark.parametrize('target', [NAN, -1.0, 0.0, 0, 4.5, 5])
def test_invalid_target_altitude_refused(make_node, target):
    with pytest.raises(ValueError):
        make_node(target_altitude=target)


def test_string_target_altitude_refused(make_node):
    with pytest.raises(ValueError):
        make_node(target_altitude='three')


def test_hover_nan_position_lands(make_node):
    node = make_node()
    _hovering(node, x=NAN)
    node.control_loop()
    assert node.state == 'LANDING' and node.lands == ['HOVER']


def test_takeoff_nan_altitude_lands(make_node):
    node = make_node()
    _hovering(node, z=NAN)
    node.state = 'TAKEOFF'
    node.control_loop()
    assert node.state == 'LANDING' and node.lands == ['TAKEOFF']


def test_hover_drift_lands(make_node):
    node = make_node()
    _hovering(node, x=2.5)
    node.control_loop()
    assert node.state == 'LANDING'


def test_hover_within_limits_keeps_hovering(make_node):
    node = make_node()
    _hovering(node, x=1.0, y=1.0)
    node.control_loop()
    assert node.state == 'HOVER' and node.lands == []


@pytest.mark.parametrize('state', ['TAKEOFF', 'HOVER'])
def test_runtime_max_altitude_lands(make_node, state):
    node = make_node(target_altitude=3.0, max_altitude=4.0)
    _hovering(node, z=-4.6)
    node.state = state
    node.control_loop()
    assert node.state == 'LANDING' and node.lands == [state]


def test_altitude_inside_margin_keeps_flying(make_node):
    node = make_node(target_altitude=3.0, max_altitude=4.0)
    _hovering(node, z=-4.4)
    node.control_loop()
    assert node.state == 'HOVER' and node.lands == []


def test_landing_is_not_re_aborted(make_node):
    node = make_node()
    _hovering(node, x=NAN)
    node.state = 'LANDING'
    node.offboard_setpoint_counter = 1  # not a NAV_LAND re-issue tick
    node.control_loop()
    assert node.state == 'LANDING' and node.lands == []


def test_mission_timeout_uses_node_clock(make_node):
    node = make_node(max_mission_time=60.0, hover_duration=1000.0)
    _hovering(node)
    node.fake_now += 59.0
    node.control_loop()
    assert node.state == 'HOVER'
    node.fake_now += 2.0
    node.control_loop()
    assert node.state == 'LANDING' and node.lands == ['HOVER']


def test_hover_duration_uses_node_clock(make_node):
    node = make_node(hover_duration=10.0)
    _hovering(node)
    node.fake_now += 9.9
    node.control_loop()
    assert node.state == 'HOVER'
    node.fake_now += 0.2
    node.control_loop()
    assert node.state == 'LANDING'


def test_now_s_is_ros_clock(make_node):
    node = make_node()
    del node.now_s  # back to the real method
    expected = node.get_clock().now().nanoseconds * 1e-9
    assert math.isclose(node.now_s(), expected, abs_tol=1.0)


def test_no_wall_clock_in_node_source():
    import inspect
    src = inspect.getsource(mn)
    assert 'time.time(' not in src
    assert 'import time' not in src
