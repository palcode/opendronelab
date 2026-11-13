# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Unit tests for localization metrics."""
import pytest
import numpy as np

from drone_localization.localization_metrics import (
    enu_to_ned,
    interpolate_trajectory,
    align_trajectories,
    compute_metrics,
    airborne_mask_from_gt_z,
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


def test_yaw_conversions_and_quaternion():
    """GT ENU yaw -> NED yaw, and yaw-only quaternion round trip."""
    from drone_localization.localization_metrics import (
        quaternion_to_yaw,
        yaw_to_quaternion,
    )
    yaws = np.array([0.0, 0.5, -1.2, np.pi / 2])
    q = yaw_to_quaternion(yaws)
    assert q.shape == (4, 4)
    np.testing.assert_allclose(np.linalg.norm(q, axis=1), 1.0)
    back = quaternion_to_yaw(q[:, 0], q[:, 1], q[:, 2], q[:, 3])
    np.testing.assert_allclose(back, yaws, atol=1e-12)


def test_interpolate_yaw_across_wrap():
    """Yaw interpolation must not swing through zero at the +-pi wrap."""
    from drone_localization.localization_metrics import interpolate_yaw
    t = np.array([0.0, 1e9])
    yaws = np.array([np.pi - 0.1, -np.pi + 0.1])
    mid = interpolate_yaw(t, yaws, np.array([0.5e9]))[0]
    assert abs(abs(mid) - np.pi) < 1e-9


def test_write_tum_format(tmp_path):
    """TUM rows: 8 columns, seconds timestamps, positions as given."""
    from drone_localization.localization_metrics import (
        export_tum_pair,
    )
    ts = np.array([1.5e9, 2.0e9, 2.5e9])
    gt = np.array([[0.0, 0.0, -5.0], [1.0, 0.0, -5.0], [2.0, 0.0, -5.0]])
    est = gt + np.array([0.1, 0.0, 0.0])
    gt_path, est_path = export_tum_pair(
        tmp_path, ts, gt, est, np.zeros(3), np.zeros(3)
    )
    rows = np.loadtxt(est_path)
    assert rows.shape == (3, 8)
    np.testing.assert_allclose(rows[:, 0], [1.5, 2.0, 2.5])
    np.testing.assert_allclose(rows[:, 1:4], est, atol=1e-6)
    np.testing.assert_allclose(rows[:, 7], 1.0)
    rows_gt = np.loadtxt(gt_path)
    np.testing.assert_allclose(rows_gt[:, 0], rows[:, 0])


def test_airborne_mask_uses_raw_gt_z_when_ov_inits_mid_air():
    """Late mid-air OV init must not empty the airborne mask after origin-align.

    Recreates cal bag 20261109_224426: first overlapping OV pose is at cruise
    altitude, so origin-align shifts GT z from ~-5 m to ~0 and a mask on
    aligned z would drop every sample.
    """
    # 1 s on ground, then 3 s at 5 m AGL (NED z = -5).
    gt_t = np.array([0.0, 1.0, 2.0, 3.0, 4.0]) * 1e9
    gt_p = np.array([
        [0.0, 0.0, -0.15],
        [0.0, 0.0, -0.15],
        [0.0, 0.0, -5.0],
        [5.0, 0.0, -5.0],
        [10.0, 0.0, -5.0],
    ])
    # OV starts only once already at altitude (first pose z ≈ 0 in its frame).
    est_t = np.array([2.0, 3.0, 4.0]) * 1e9
    est_p = np.array([
        [0.0, 0.0, 0.0],
        [5.0, 0.0, 0.0],
        [10.0, 0.0, 0.0],
    ])
    gt_raw, _est_raw, _ts = align_trajectories(gt_t, gt_p, est_t, est_p, origin_align=False)
    gt_al, est_al, _ts2 = align_trajectories(gt_t, gt_p, est_t, est_p, origin_align=True)
    raw_mask = airborne_mask_from_gt_z(gt_raw[:, 2])
    aligned_mask = airborne_mask_from_gt_z(gt_al[:, 2])
    assert int(np.sum(raw_mask)) == 3
    assert int(np.sum(aligned_mask)) == 0
    # Scoring must use the raw-z mask on origin-aligned positions.
    metrics = compute_metrics(gt_al, est_al, raw_mask)
    assert metrics['num_samples'] == 3


def test_detect_pose_jumps_smooth_trajectory_is_clean():
    """150 Hz 1 m/s track with 1 cm noise stays under the 0.30 m margin."""
    from drone_localization.localization_metrics import detect_pose_jumps
    dt = 1.0 / 150.0
    t = np.arange(0.0, 2.0, dt)
    gt = np.column_stack([t * 1.0, np.zeros(len(t)), np.full(len(t), -5.0)])
    rng = np.random.default_rng(0)
    est = gt + rng.normal(0.0, 0.01, gt.shape)
    out = detect_pose_jumps(t, est, gt, margin_m=0.30)
    assert out['gating'] is False
    assert out['report_only'] is True
    assert out['count'] == 0
    assert out['max_jump_m'] is None
    assert out['jumps'] == []


def test_detect_pose_jumps_flags_implanted_impulse():
    """A 2 m step in 6 ms is flagged; bound is GT step + margin."""
    from drone_localization.localization_metrics import detect_pose_jumps
    dt = 0.006
    t = np.arange(0.0, 1.0, dt)
    gt = np.column_stack([t * 1.0, np.zeros(len(t)), np.full(len(t), -5.0)])
    est = gt.copy()
    jump_i = int(0.5 / dt)
    est[jump_i + 1:] += np.array([2.0, 0.0, 0.0])
    out = detect_pose_jumps(t, est, gt, margin_m=0.30)
    assert out['count'] == 1
    assert out['gating'] is False
    assert abs(out['max_jump_m'] - 2.0) < 0.02
    assert abs(out['max_jump_t_s'] - t[jump_i]) < dt * 0.51
    assert out['max_jump_dt_s'] == pytest.approx(dt, abs=1e-9)
    assert out['jumps'][0]['bound_m'] == pytest.approx(1.0 * dt + 0.30, abs=1e-6)
    assert out['max_jump_t_abs_s'] == pytest.approx(t[jump_i], abs=1e-9)


def test_detect_pose_jumps_bound_is_gt_step_plus_margin():
    """A step equal to GT displacement + half margin is clean; over margin flags."""
    from drone_localization.localization_metrics import detect_pose_jumps
    t = np.array([0.0, 0.1, 0.2])
    gt = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
    margin = 0.30
    est_ok = np.array([[0.0, 0.0, 0.0], [1.15, 0.0, 0.0], [2.15, 0.0, 0.0]])
    assert detect_pose_jumps(t, est_ok, gt, margin_m=margin)['count'] == 0
    est_bad = np.array([[0.0, 0.0, 0.0], [1.60, 0.0, 0.0], [2.20, 0.0, 0.0]])
    out = detect_pose_jumps(t, est_bad, gt, margin_m=margin)
    assert out['count'] == 1
    assert out['jumps'][0]['distance_m'] == pytest.approx(1.60, abs=1e-9)
    assert out['jumps'][0]['bound_m'] == pytest.approx(1.30, abs=1e-9)


def test_detect_pose_jumps_empty_and_singleton():
    from drone_localization.localization_metrics import detect_pose_jumps
    out = detect_pose_jumps([], [], [])
    assert out['count'] == 0
    assert out['gating'] is False
    t = np.array([1.0])
    p = np.array([[0.0, 0.0, 0.0]])
    assert detect_pose_jumps(t, p, p)['count'] == 0


def test_detect_pose_jumps_from_tum_roundtrip(tmp_path):
    """TUM pair written by export_tum_pair is scored the same as in-memory arrays."""
    from drone_localization.localization_metrics import (
        detect_pose_jumps_from_tum, export_tum_pair,
    )
    ts = np.array([10e9, 10.006e9, 10.012e9])
    # Stationary GT so the implanted 2 m VIO step is exact (not 2 m + v*dt).
    gt = np.array([[0.0, 0.0, -5.0], [0.0, 0.0, -5.0], [0.0, 0.0, -5.0]])
    est = gt.copy()
    est[1:] += np.array([2.0, 0.0, 0.0])
    gt_path, est_path = export_tum_pair(
        tmp_path, ts, gt, est, np.zeros(3), np.zeros(3)
    )
    out = detect_pose_jumps_from_tum(est_path, gt_path, margin_m=0.30)
    assert out['count'] == 1
    assert out['max_jump_m'] == pytest.approx(2.0, abs=1e-6)
    assert out['gating'] is False
