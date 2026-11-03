"""Unit tests for safety limit validation."""
import unittest
import math


class TestSafetyLimits(unittest.TestCase):
    """Test safety limit calculations."""

    def test_altitude_limit(self):
        """Test altitude limit validation."""
        max_altitude = 4.0
        valid_targets = [1.0, 2.0, 3.0, 3.9, 4.0]
        invalid_targets = [4.1, 5.0, 10.0]

        for target in valid_targets:
            self.assertTrue(target <= max_altitude,
                            f'Target {target}m should be valid')

        for target in invalid_targets:
            self.assertFalse(target <= max_altitude,
                             f'Target {target}m should be invalid')

    def test_xy_drift_calculation(self):
        """Test XY drift calculation."""
        start_x, start_y = 0.0, 0.0

        # Test cases: (x, y, expected_drift)
        cases = [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 1.0),
            (0.0, 1.0, 1.0),
            (3.0, 4.0, 5.0),
            (-1.0, 0.0, 1.0),
        ]

        for x, y, expected in cases:
            drift = math.sqrt((x - start_x) ** 2 + (y - start_y) ** 2)
            self.assertAlmostEqual(drift, expected, places=5,
                                   msg=f'Drift from ({start_x},{start_y}) '
                                       f'to ({x},{y})')

    def test_drift_limit(self):
        """Test drift limit violation detection."""
        max_drift = 2.0

        valid_drifts = [0.0, 0.5, 1.0, 1.5, 2.0]
        invalid_drifts = [2.1, 3.0, 5.0]

        for drift in valid_drifts:
            self.assertTrue(drift <= max_drift,
                            f'Drift {drift}m should be valid')

        for drift in invalid_drifts:
            self.assertFalse(drift <= max_drift,
                             f'Drift {drift}m should trigger abort')


if __name__ == '__main__':
    unittest.main()
