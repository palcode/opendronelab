# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Launch Phase 2 telemetry subscriber (drone_telemetry)."""
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    """Generate launch description for telemetry node."""
    return LaunchDescription([
        Node(
            package='drone_telemetry',
            executable='telemetry_node',
            name='telemetry_node',
            output='screen',
            emulate_tty=True,
        ),
    ])
