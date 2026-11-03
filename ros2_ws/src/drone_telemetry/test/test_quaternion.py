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
