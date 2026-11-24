# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Unit tests for quaternion to Euler conversion."""
import unittest
import math
from drone_telemetry.telemetry_node import quaternion_to_euler


class TestQuaternionConversion(unittest.TestCase):
    """Test quaternion to Euler angle conversion."""

    def test_identity_quaternion(self):
        """Test identity quaternion (no rotation)."""
        roll, pitch, yaw = quaternion_to_euler(1.0, 0.0, 0.0, 0.0)
        self.assertAlmostEqual(roll, 0.0, places=5)
        self.assertAlmostEqual(pitch, 0.0, places=5)
        self.assertAlmostEqual(yaw, 0.0, places=5)

    def test_90_deg_roll(self):
        """Test 90 degree roll rotation."""
        # q = [cos(45°), sin(45°), 0, 0] for 90° roll
        w = math.cos(math.radians(45))
        x = math.sin(math.radians(45))
        roll, pitch, yaw = quaternion_to_euler(w, x, 0.0, 0.0)
        self.assertAlmostEqual(roll, math.radians(90), places=5)
        self.assertAlmostEqual(pitch, 0.0, places=5)
        self.assertAlmostEqual(yaw, 0.0, places=5)

    def test_90_deg_pitch(self):
        """Test 90 degree pitch rotation."""
        w = math.cos(math.radians(45))
        y = math.sin(math.radians(45))
        roll, pitch, yaw = quaternion_to_euler(w, 0.0, y, 0.0)
        self.assertAlmostEqual(roll, 0.0, places=5)
        self.assertAlmostEqual(pitch, math.radians(90), places=5)
        self.assertAlmostEqual(yaw, 0.0, places=5)

    def test_90_deg_yaw(self):
        """Test 90 degree yaw rotation."""
        w = math.cos(math.radians(45))
        z = math.sin(math.radians(45))
        roll, pitch, yaw = quaternion_to_euler(w, 0.0, 0.0, z)
        self.assertAlmostEqual(roll, 0.0, places=5)
        self.assertAlmostEqual(pitch, 0.0, places=5)
        self.assertAlmostEqual(yaw, math.radians(90), places=5)


if __name__ == '__main__':
    unittest.main()


def test_non_unit_quaternion_is_normalised():
    """ODL-139: a scaled quaternion gives the same angles as its unit form."""
    w = math.cos(math.radians(15))
    z = math.sin(math.radians(15))
    unit = quaternion_to_euler(w, 0.0, 0.0, z)
    for k in (0.5, 2.0, 1.001):
        got = quaternion_to_euler(k * w, 0.0, 0.0, k * z)
        for a, b in zip(got, unit):
            assert math.isclose(a, b, abs_tol=1e-9)
    assert math.isclose(unit[2], math.radians(30), abs_tol=1e-9)
    # Unnormalised, a 2x quaternion of a 45 deg pitch would saturate asin.
    w, y = math.cos(math.radians(22.5)), math.sin(math.radians(22.5))
    _, pitch, _ = quaternion_to_euler(2 * w, 0.0, 2 * y, 0.0)
    assert math.isclose(pitch, math.radians(45), abs_tol=1e-9)


def test_zero_or_nan_quaternion_is_nan():
    """ODL-139: no rotation can be read from a zero or NaN quaternion."""
    for q in ((0.0, 0.0, 0.0, 0.0), (math.nan, 0.0, 0.0, 1.0)):
        assert all(math.isnan(a) for a in quaternion_to_euler(*q))
