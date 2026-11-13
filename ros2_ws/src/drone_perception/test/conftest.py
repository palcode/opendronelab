# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Mock ROS / ONNX / cv_bridge so pure-function tests can import the node module."""
import sys
from unittest.mock import MagicMock

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
    sys.modules.setdefault(mod, MagicMock())

# Provide the symbols the module imports by name.
sys.modules['rclpy.node'].Node = type('Node', (), {'__init__': lambda self, *a, **k: None})
sys.modules['rclpy.qos'].QoSProfile = MagicMock
sys.modules['rclpy.qos'].ReliabilityPolicy = MagicMock()
sys.modules['rclpy.qos'].HistoryPolicy = MagicMock()
