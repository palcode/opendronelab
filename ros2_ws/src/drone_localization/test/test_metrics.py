"""Unit tests for localization metrics."""
import pytest
import numpy as np

from drone_localization.localization_metrics import (
    enu_to_ned,
    interpolate_trajectory,
    align_trajectories,
    compute_metrics,
)


def test_enu_to_ned():
    """Test ENU to NED coordinate conversion."""
    x_ned, y_ned, z_ned = enu_to_ned(1.0, 2.0, 3.0)
    assert x_ned == 2.0
    assert y_ned == 1.0
    assert z_ned == -3.0

    x_ned, y_ned, z_ned = enu_to_ned(0.0, 0.0, 0.0)
    assert (x_ned, y_ned, z_ned) == (0.0, 0.0, 0.0)

    x_ned, y_ned, z_ned = enu_to_ned(-1.0, -2.0, -3.0)
    assert x_ned == -2.0
    assert y_ned == -1.0
    assert z_ned == 3.0


def test_interpolate_trajectory():
    """Test trajectory interpolation."""
    timestamps = np.array([0, 1e9, 2e9, 3e9])
    positions = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [2.0, 0.0, 0.0],
        [3.0, 0.0, 0.0],
    ])
    target_timestamps = np.array([0.5e9, 1.5e9, 2.5e9])
    interp = interpolate_trajectory(timestamps, positions, target_timestamps)

    assert interp.shape == (3, 3)
    np.testing.assert_allclose(interp[0], [0.5, 0.0, 0.0])
    np.testing.assert_allclose(interp[1], [1.5, 0.0, 0.0])
    np.testing.assert_allclose(interp[2], [2.5, 0.0, 0.0])


def test_align_trajectories():
    """Test trajectory alignment with origin offset removal."""
    gt_timestamps = np.linspace(0, 10e9, 11)
    gt_positions = np.column_stack([
        np.linspace(0, 10, 11),
        np.zeros(11),
        np.zeros(11),
    ])
    est_timestamps = np.linspace(0, 10e9, 11)
    est_positions = np.column_stack([
        np.linspace(1, 11, 11),  # 1 m constant offset
        np.zeros(11),
        np.zeros(11),
    ])

    gt_aligned, est_aligned, aligned_ts = align_trajectories(
        gt_timestamps, gt_positions, est_timestamps, est_positions
    )

    np.testing.assert_allclose(gt_aligned[0], est_aligned[0], atol=1e-6)
    assert gt_aligned.shape == est_aligned.shape
    assert len(aligned_ts) == len(est_aligned)
    errors = np.linalg.norm(est_aligned - gt_aligned, axis=1)
    np.testing.assert_allclose(errors, 0.0, atol=1e-6)


def test_align_trajectories_no_origin_align():
    """Without origin align, constant bias is preserved."""
    gt_timestamps = np.linspace(0, 10e9, 11)
    gt_positions = np.column_stack([
        np.linspace(0, 10, 11), np.zeros(11), np.zeros(11)
    ])
    est_timestamps = gt_timestamps.copy()
    est_positions = gt_positions.copy()
    est_positions[:, 0] += 1.0

    gt_aligned, est_aligned, _ = align_trajectories(
        gt_timestamps, gt_positions, est_timestamps, est_positions,
        origin_align=False,
    )
    errors = np.linalg.norm(est_aligned - gt_aligned, axis=1)
    np.testing.assert_allclose(errors, 1.0, atol=1e-6)


def test_synthetic_square_trajectory():
    """Known 1 m constant ATE on a square; use origin_align=False.

    Default origin-align zeros a constant bias, so absolute-ATE tests must
    disable it (or call compute_metrics on raw arrays).
    """
    gt_timestamps = np.array([0, 5e9, 10e9, 15e9, 20e9])
    gt_positions = np.array([
        [0.0, 0.0, -5.0],
        [10.0, 0.0, -5.0],
        [10.0, 10.0, -5.0],
        [0.0, 10.0, -5.0],
        [0.0, 0.0, -5.0],
    ])
    est_timestamps = gt_timestamps.copy()
    est_positions = gt_positions.copy()
    est_positions[:, 0] += 1.0

    gt_aligned, est_aligned, aligned_ts = align_trajectories(
        gt_timestamps, gt_positions, est_timestamps, est_positions,
        origin_align=False,
    )
    assert len(aligned_ts) == len(est_aligned)

    metrics = compute_metrics(gt_aligned, est_aligned)
    assert abs(metrics['horizontal_rmse'] - 1.0) < 0.001
    assert abs(metrics['horizontal_mean'] - 1.0) < 0.001
    assert abs(metrics['horizontal_max'] - 1.0) < 0.001
    assert metrics['vertical_rmse'] < 1e-10
    assert metrics['vertical_mean'] < 1e-10
    assert metrics['vertical_max'] < 1e-10


def test_compute_metrics_perfect():
    gt_positions = np.array([
        [0.0, 0.0, -5.0],
        [10.0, 0.0, -5.0],
        [10.0, 10.0, -5.0],
        [0.0, 10.0, -5.0],
    ])
    metrics = compute_metrics(gt_positions, gt_positions.copy())
    assert metrics['horizontal_rmse'] < 1e-10
    assert metrics['vertical_rmse'] < 1e-10
    assert metrics['num_samples'] == 4


def test_compute_metrics_constant_error():
    gt_positions = np.array([
        [0.0, 0.0, -5.0],
        [10.0, 0.0, -5.0],
        [10.0, 10.0, -5.0],
        [0.0, 10.0, -5.0],
    ])
    est_positions = gt_positions.copy()
    est_positions[:, 0] += 1.0
    metrics = compute_metrics(gt_positions, est_positions)
    assert abs(metrics['horizontal_rmse'] - 1.0) < 0.001
    assert metrics['vertical_rmse'] < 1e-10


def test_compute_metrics_vertical_error():
    gt_positions = np.array([
        [0.0, 0.0, -5.0],
        [10.0, 0.0, -5.0],
        [10.0, 10.0, -5.0],
        [0.0, 10.0, -5.0],
    ])
    est_positions = gt_positions.copy()
    est_positions[:, 2] -= 0.5
    metrics = compute_metrics(gt_positions, est_positions)
    assert metrics['horizontal_rmse'] < 1e-10
    assert abs(metrics['vertical_rmse'] - 0.5) < 0.001


def test_compute_metrics_with_mask():
    gt_positions = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, -5.0],
        [2.0, 0.0, -5.0],
        [3.0, 0.0, 0.0],
    ])
    est_positions = gt_positions.copy()
    est_positions[1:3, 0] += 1.0
    airborne_mask = np.array([False, True, True, False])
    metrics = compute_metrics(gt_positions, est_positions, airborne_mask)
    assert metrics['num_samples'] == 2
    assert abs(metrics['horizontal_rmse'] - 1.0) < 0.001


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
