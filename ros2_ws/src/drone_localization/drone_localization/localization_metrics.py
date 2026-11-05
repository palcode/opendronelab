#!/usr/bin/env python3
"""
Localization metrics computation from rosbag2 data.

Computes RMSE and error statistics by comparing PX4 EKF estimates
with Gazebo ground truth.
"""
import sys
import json
import argparse
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt

# rosbag2 / rclpy imports are only needed for bag I/O (main). Unit tests
# import the pure-numpy helpers without requiring a ROS install.
try:
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    from rosbag2_py import SequentialReader, StorageOptions, ConverterOptions
    _HAS_ROSBAG = True
except ImportError:  # pragma: no cover - unit-test path on the box
    _HAS_ROSBAG = False


def enu_to_ned(x_enu, y_enu, z_enu):
    """Convert ENU coordinates to NED."""
    return y_enu, x_enu, -z_enu


def read_bag_messages(bag_path, topic_name):
    """
    Read messages from a rosbag2 bag.

    Returns:
        list: List of (timestamp_ns, message) tuples (bag receive time).
    """
    if not _HAS_ROSBAG:
        raise RuntimeError('rosbag2_py / rclpy not available')

    storage_options = StorageOptions(uri=str(bag_path), storage_id='')
    converter_options = ConverterOptions(
        input_serialization_format='cdr',
        output_serialization_format='cdr',
    )

    reader = SequentialReader()
    reader.open(storage_options, converter_options)

    topic_types = reader.get_all_topics_and_types()
    type_map = {t.name: t.type for t in topic_types}
    if topic_name not in type_map:
        return []

    msg_type = get_message(type_map[topic_name])
    messages = []
    while reader.has_next():
        topic, data, timestamp = reader.read_next()
        if topic == topic_name:
            messages.append((timestamp, deserialize_message(data, msg_type)))
    return messages


def extract_vehicle_local_position(messages):
    """
    Extract NED positions from vehicle_local_position messages.

    Uses bag receive timestamps for both estimate and ground truth so the
    two series share one clock (PX4 `timestamp` is boot-time us; header may
    be absent on some px4_msgs variants).
    """
    timestamps = []
    positions = []
    for timestamp_ns, msg in messages:
        timestamps.append(timestamp_ns)
        positions.append([msg.x, msg.y, msg.z])
    return np.array(timestamps, dtype=np.float64), np.array(positions, dtype=np.float64)


def extract_ground_truth_odometry(messages, convert_enu_to_ned=True):
    """
    Extract positions from nav_msgs/Odometry (ground truth).

    Uses bag receive timestamps (same clock as the estimate extractor).
    Converts ENU -> NED when convert_enu_to_ned is True (default), matching
    Gazebo ENU published by ground_truth_publisher.
    """
    timestamps = []
    positions = []
    for timestamp_ns, msg in messages:
        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y
        z = msg.pose.pose.position.z
        if convert_enu_to_ned:
            x, y, z = enu_to_ned(x, y, z)
        timestamps.append(timestamp_ns)
        positions.append([x, y, z])
    return np.array(timestamps, dtype=np.float64), np.array(positions, dtype=np.float64)


def interpolate_trajectory(timestamps, positions, target_timestamps):
    """Interpolate trajectory to match target timestamps."""
    t_src = timestamps / 1e9
    t_tgt = target_timestamps / 1e9
    x_interp = np.interp(t_tgt, t_src, positions[:, 0])
    y_interp = np.interp(t_tgt, t_src, positions[:, 1])
    z_interp = np.interp(t_tgt, t_src, positions[:, 2])
    return np.column_stack([x_interp, y_interp, z_interp])


def extract_heading_ned(messages):
    """Return EKF2 heading (yaw, rad, NED) from vehicle_local_position msgs."""
    return np.array([float(msg.heading) for _, msg in messages], dtype=np.float64)


def quaternion_to_yaw(qx, qy, qz, qw):
    """Yaw (rad) about +z of a quaternion (ZYX convention)."""
    return np.arctan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))


def extract_ground_truth_yaw_ned(messages):
    """
    Return ground-truth yaw (rad) in NED from ENU/FLU nav_msgs/Odometry.

    ENU yaw is measured from East toward North; NED yaw from North toward
    East, so yaw_ned = pi/2 - yaw_enu (wrapped to [-pi, pi]).
    """
    yaws = []
    for _, msg in messages:
        q = msg.pose.pose.orientation
        yaw_enu = quaternion_to_yaw(q.x, q.y, q.z, q.w)
        yaws.append(np.pi / 2.0 - yaw_enu)
    yaws = np.array(yaws, dtype=np.float64)
    return np.arctan2(np.sin(yaws), np.cos(yaws))


def interpolate_yaw(timestamps, yaws, target_timestamps):
    """Interpolate yaw angles (rad) onto target times without wrap jumps."""
    unwrapped = np.unwrap(yaws)
    out = np.interp(target_timestamps / 1e9, timestamps / 1e9, unwrapped)
    return np.arctan2(np.sin(out), np.cos(out))


def yaw_to_quaternion(yaws):
    """Yaw-only quaternions as an (N, 4) array in TUM order qx qy qz qw."""
    yaws = np.asarray(yaws, dtype=np.float64)
    zeros = np.zeros_like(yaws)
    return np.column_stack([zeros, zeros, np.sin(yaws / 2.0), np.cos(yaws / 2.0)])


def write_tum(path, timestamps_ns, positions, quaternions):
    """
    Write a TUM trajectory file: ``timestamp tx ty tz qx qy qz qw``.

    Timestamps are bag receive time converted to seconds (9 decimals), so
    estimate and ground-truth files share one time base.
    """
    timestamps_ns = np.asarray(timestamps_ns, dtype=np.float64)
    positions = np.asarray(positions, dtype=np.float64)
    quaternions = np.asarray(quaternions, dtype=np.float64)
    if not (len(timestamps_ns) == len(positions) == len(quaternions)):
        raise ValueError('timestamps, positions and quaternions differ in length')
    with open(path, 'w') as f:
        for t, p, q in zip(timestamps_ns, positions, quaternions):
            f.write(
                f'{t / 1e9:.9f} {p[0]:.6f} {p[1]:.6f} {p[2]:.6f} '
                f'{q[0]:.9f} {q[1]:.9f} {q[2]:.9f} {q[3]:.9f}\n'
            )


def export_tum_pair(output_dir, timestamps_ns, gt_positions, est_positions,
                    gt_yaws, est_yaws):
    """
    Write ``gt_ned.tum`` and ``est_ned.tum`` for the exact samples scored.

    Both are NED, origin-aligned like the metrics, sampled at the estimate's
    bag receive times (GT interpolated), airborne samples only. Orientation
    is yaw-only (GT yaw vs EKF2 heading). Returns the two paths.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    gt_path = output_dir / 'gt_ned.tum'
    est_path = output_dir / 'est_ned.tum'
    write_tum(gt_path, timestamps_ns, gt_positions, yaw_to_quaternion(gt_yaws))
    write_tum(est_path, timestamps_ns, est_positions, yaw_to_quaternion(est_yaws))
    return gt_path, est_path


def align_trajectories(
    gt_timestamps,
    gt_positions,
    est_timestamps,
    est_positions,
    origin_align=True,
):
    """
    Align ground truth and estimated trajectories.

    Finds the overlapping time window, optionally removes a constant origin
    offset (first-sample alignment), and interpolates GT onto estimate times.

    Returns:
        tuple: (aligned_gt, aligned_est, aligned_timestamps) — all length K.
    """
    t_start = max(gt_timestamps[0], est_timestamps[0])
    t_end = min(gt_timestamps[-1], est_timestamps[-1])

    gt_mask = (gt_timestamps >= t_start) & (gt_timestamps <= t_end)
    est_mask = (est_timestamps >= t_start) & (est_timestamps <= t_end)

    gt_timestamps = gt_timestamps[gt_mask]
    gt_positions = gt_positions[gt_mask]
    est_timestamps = est_timestamps[est_mask]
    est_positions = est_positions[est_mask]

    if len(gt_timestamps) == 0 or len(est_timestamps) == 0:
        raise ValueError(
            'No overlapping timestamps between ground truth and estimate'
        )

    if origin_align:
        origin_offset = gt_positions[0] - est_positions[0]
        gt_positions = gt_positions - origin_offset

    gt_interp = interpolate_trajectory(
        gt_timestamps, gt_positions, est_timestamps
    )
    return gt_interp, est_positions, est_timestamps


def compute_metrics(gt_positions, est_positions, airborne_mask=None):
    """Compute localization error metrics (RMSE / mean / max)."""
    if airborne_mask is not None:
        gt_positions = gt_positions[airborne_mask]
        est_positions = est_positions[airborne_mask]

    if len(gt_positions) == 0:
        raise ValueError('No samples left after airborne mask')

    errors = est_positions - gt_positions
    horizontal_errors = np.sqrt(errors[:, 0] ** 2 + errors[:, 1] ** 2)
    vertical_errors = np.abs(errors[:, 2])

    return {
        'horizontal_rmse': float(np.sqrt(np.mean(horizontal_errors ** 2))),
        'horizontal_mean': float(np.mean(horizontal_errors)),
        'horizontal_max': float(np.max(horizontal_errors)),
        'vertical_rmse': float(np.sqrt(np.mean(vertical_errors ** 2))),
        'vertical_mean': float(np.mean(vertical_errors)),
        'vertical_max': float(np.max(vertical_errors)),
        'num_samples': int(len(horizontal_errors)),
    }


def plot_trajectory(gt_positions, est_positions, output_path):
    """Plot XY trajectory comparison (NED: X=North, Y=East)."""
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.plot(
        gt_positions[:, 1], gt_positions[:, 0],
        'g-', label='Ground Truth', linewidth=2,
    )
    ax.plot(
        est_positions[:, 1], est_positions[:, 0],
        'r--', label='Estimated', linewidth=2,
    )
    ax.plot(gt_positions[0, 1], gt_positions[0, 0], 'go', markersize=10, label='Start')
    ax.plot(gt_positions[-1, 1], gt_positions[-1, 0], 'gs', markersize=10, label='End')
    ax.set_xlabel('East (m)')
    ax.set_ylabel('North (m)')
    ax.set_title('Trajectory Comparison (XY Plane, NED Frame)')
    ax.legend()
    ax.grid(True)
    ax.axis('equal')
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


def plot_errors(timestamps, gt_positions, est_positions, output_path):
    """Plot horizontal/vertical error over time."""
    errors = est_positions - gt_positions
    horizontal_errors = np.sqrt(errors[:, 0] ** 2 + errors[:, 1] ** 2)
    vertical_errors = np.abs(errors[:, 2])
    time_s = (timestamps - timestamps[0]) / 1e9

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    ax1.plot(time_s, horizontal_errors, 'b-', linewidth=1.5)
    ax1.set_xlabel('Time (s)')
    ax1.set_ylabel('Horizontal Error (m)')
    ax1.set_title('Horizontal Position Error Over Time')
    ax1.grid(True)

    ax2.plot(time_s, vertical_errors, 'r-', linewidth=1.5)
    ax2.set_xlabel('Time (s)')
    ax2.set_ylabel('Vertical Error (m)')
    ax2.set_title('Vertical Position Error Over Time')
    ax2.grid(True)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


def main(args=None):
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Compute localization metrics from bag'
    )
    parser.add_argument('bag_path', help='Path to rosbag2 directory')
    parser.add_argument(
        '--output-dir', help='Output directory (defaults to bag directory)'
    )
    parser.add_argument(
        '--no-origin-align',
        action='store_true',
        help='Disable first-sample origin alignment (keeps absolute bias)',
    )
    parser.add_argument(
        '--tum-dir',
        help='Also write gt_ned.tum / est_ned.tum (scored samples) here '
             'for an external evo cross-check (scripts/evo-check.sh)',
    )
    parsed = parser.parse_args(args)

    bag_path = Path(parsed.bag_path)
    output_dir = Path(parsed.output_dir) if parsed.output_dir else bag_path

    if not bag_path.exists():
        print(f'Error: Bag path does not exist: {bag_path}')
        return 1

    print(f'Reading bag: {bag_path}')
    est_msgs = read_bag_messages(bag_path, '/fmu/out/vehicle_local_position_v1')
    if not est_msgs:
        print('Error: No vehicle_local_position_v1 messages found')
        return 1

    gt_msgs = read_bag_messages(bag_path, '/ground_truth/odometry')
    if not gt_msgs:
        print('Error: No ground_truth/odometry messages found')
        return 1

    print(
        f'Found {len(est_msgs)} estimated and {len(gt_msgs)} ground truth samples'
    )

    est_timestamps, est_positions = extract_vehicle_local_position(est_msgs)
    gt_timestamps, gt_positions = extract_ground_truth_odometry(gt_msgs)

    print('Aligning trajectories...')
    gt_aligned, est_aligned, aligned_ts = align_trajectories(
        gt_timestamps,
        gt_positions,
        est_timestamps,
        est_positions,
        origin_align=not parsed.no_origin_align,
    )

    # Airborne: NED z more negative than -0.5 m (above ~0.5 m AGL).
    airborne_mask = (est_aligned[:, 2] < -0.5) & (est_aligned[:, 2] > -20.0)
    print(f'Airborne samples: {np.sum(airborne_mask)} / {len(airborne_mask)}')

    print('Computing metrics...')
    metrics = compute_metrics(gt_aligned, est_aligned, airborne_mask)
    metrics['origin_aligned'] = not parsed.no_origin_align

    metrics_path = output_dir / 'metrics.json'
    with open(metrics_path, 'w') as f:
        json.dump(metrics, f, indent=2)
    print(f'Metrics saved to: {metrics_path}')

    if parsed.tum_dir:
        gt_yaw = interpolate_yaw(
            gt_timestamps, extract_ground_truth_yaw_ned(gt_msgs), aligned_ts
        )
        est_yaw = extract_heading_ned(est_msgs)
        # Same overlap window align_trajectories applied to the estimate.
        window = (est_timestamps >= aligned_ts[0]) & (est_timestamps <= aligned_ts[-1])
        est_yaw = est_yaw[window]
        gt_tum, est_tum = export_tum_pair(
            parsed.tum_dir,
            aligned_ts[airborne_mask],
            gt_aligned[airborne_mask],
            est_aligned[airborne_mask],
            gt_yaw[airborne_mask],
            est_yaw[airborne_mask],
        )
        print(f'TUM export: {gt_tum} and {est_tum}')

    print('\n=== Localization Metrics ===')
    print(f"Horizontal RMSE: {metrics['horizontal_rmse']:.3f} m")
    print(f"Horizontal Mean: {metrics['horizontal_mean']:.3f} m")
    print(f"Horizontal Max:  {metrics['horizontal_max']:.3f} m")
    print(f"Vertical RMSE:   {metrics['vertical_rmse']:.3f} m")
    print(f"Vertical Mean:   {metrics['vertical_mean']:.3f} m")
    print(f"Vertical Max:    {metrics['vertical_max']:.3f} m")
    print(f"Airborne Samples: {metrics['num_samples']}")
    print(f"Origin aligned:   {metrics['origin_aligned']}")

    print('\nGenerating plots...')
    traj_path = output_dir / 'trajectory.png'
    plot_trajectory(
        gt_aligned[airborne_mask], est_aligned[airborne_mask], traj_path
    )
    print(f'Trajectory plot saved to: {traj_path}')

    error_path = output_dir / 'error_plot.png'
    # Use aligned timestamps (same length as gt_aligned / est_aligned).
    plot_errors(
        aligned_ts[airborne_mask],
        gt_aligned[airborne_mask],
        est_aligned[airborne_mask],
        error_path,
    )
    print(f'Error plot saved to: {error_path}')
    print('\nDone!')
    return 0


if __name__ == '__main__':
    sys.exit(main())
