# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""process_every_n validation used by both perception nodes."""
import inspect
from pathlib import Path

import pytest

from drone_perception.params import validate_process_every_n

PKG = Path(__file__).resolve().parents[1] / 'drone_perception'


@pytest.mark.parametrize('value,expected', [(1, 1), (3, 3), (10, 10), (2.0, 2)])
def test_valid_values(value, expected):
    out = validate_process_every_n(value)
    assert out == expected and isinstance(out, int)


@pytest.mark.parametrize('value', [0, -1, -3, 0.0, 1.5, True, False, '3', None,
                                   float('nan')])
def test_invalid_values_rejected(value):
    with pytest.raises(ValueError):
        validate_process_every_n(value)


@pytest.mark.parametrize('module', ['edge_overlay_node.py', 'yolox_detector_node.py'])
def test_nodes_validate_process_every_n(module):
    src = (PKG / module).read_text()
    assert 'validate_process_every_n(' in src
    assert "self.process_every_n = validate_process_every_n(" in src


def test_validator_has_no_ros_imports():
    import drone_perception.params as p
    src = inspect.getsource(p)
    assert 'rclpy' not in src and 'cv2' not in src
