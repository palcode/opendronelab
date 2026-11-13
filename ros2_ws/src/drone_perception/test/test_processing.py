# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Unit tests for image processing functions."""
import sys
import unittest
from unittest.mock import MagicMock

# Mock ROS / cv_bridge so tests run on a plain host without those packages.
for mod in (
    'rclpy',
    'rclpy.node',
    'rclpy.qos',
    'rclpy.time',
    'sensor_msgs',
    'sensor_msgs.msg',
    'cv_bridge',
):
    sys.modules.setdefault(mod, MagicMock())

import numpy as np
from drone_perception.edge_overlay_node import (
    process_frame_with_overlay,
    add_text_overlay,
)


class TestImageProcessing(unittest.TestCase):
    """Test image processing functions."""

    def test_process_frame_synthetic(self):
        """Test edge detection on synthetic image."""
        # Create a synthetic test image (white square on black background)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        frame[25:75, 25:75] = 255

        # Process frame
        result, processing_ms = process_frame_with_overlay(frame, 50, 150)

        # Check result properties
        self.assertEqual(result.shape, frame.shape, 'Output shape should match input')
        self.assertGreaterEqual(processing_ms, 0.0, 'Processing time should be non-negative')
        self.assertLess(processing_ms, 1000.0, 'Processing should be < 1 second')

    def test_process_frame_mono_like(self):
        """BGR frame that looks grayscale still processes (mono8→bgr8 path)."""
        gray = np.random.randint(0, 255, (64, 64), dtype=np.uint8)
        frame = np.stack([gray, gray, gray], axis=-1)
        result, _ = process_frame_with_overlay(frame, 50, 150)
        self.assertEqual(result.shape, (64, 64, 3))

    def test_add_text_overlay(self):
        """Test text overlay function."""
        # Create blank test image
        frame = np.zeros((100, 100, 3), dtype=np.uint8)

        # Add text overlay
        result = add_text_overlay(frame, fps=30.0, processing_ms=5.0, latency_ms=10.0)

        # Check result properties
        self.assertEqual(result.shape, frame.shape, 'Output shape should match input')
        # Text overlay should modify pixels
        self.assertTrue(np.any(result != frame), 'Text overlay should modify frame')

    def test_fps_calculation(self):
        """Test FPS calculation logic."""
        frames = 30
        elapsed_time = 1.0  # 1 second
        fps = frames / elapsed_time
        self.assertAlmostEqual(fps, 30.0, places=1)

    def test_latency_calculation(self):
        """Test latency calculation."""
        # Simulate timestamps in nanoseconds
        stamp_ns = 1000000000  # 1 second
        now_ns = 1100000000    # 1.1 seconds
        latency_ms = (now_ns - stamp_ns) / 1e6
        self.assertAlmostEqual(latency_ms, 100.0, places=1)


if __name__ == '__main__':
    unittest.main()
