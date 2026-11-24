# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Mock ROS / ONNX / cv_bridge so pure-function tests can import the node module.

Only modules that cannot be imported are mocked. In the dev image the real
rclpy etc. are used, so this conftest does not replace them for the other
packages' tests in the same pytest session (test_mission_node.py and the
vision_px4_bridge node tests need the real rclpy).
"""
import importlib
import sys
from unittest.mock import MagicMock

_MOCKED = set()
for mod in (
    'rclpy',
    'rclpy.node',
    'rclpy.qos',
    'sensor_msgs',
    'sensor_msgs.msg',
    'vision_msgs',
    'vision_msgs.msg',
    'cv_bridge',
    'onnxruntime',
):
    if mod in sys.modules:
        continue
    try:
        importlib.import_module(mod)
    except Exception:  # noqa: BLE001 - any import failure means "mock it"
        sys.modules[mod] = MagicMock()
        _MOCKED.add(mod)

# Provide the symbols the module imports by name (mocked modules only).
if 'rclpy.node' in _MOCKED:
    sys.modules['rclpy.node'].Node = type('Node', (), {'__init__': lambda self, *a, **k: None})
if 'rclpy.qos' in _MOCKED:
    sys.modules['rclpy.qos'].QoSProfile = MagicMock
    sys.modules['rclpy.qos'].ReliabilityPolicy = MagicMock()
    sys.modules['rclpy.qos'].HistoryPolicy = MagicMock()
