# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Launch file for localization ground truth bridge.

Bridges /clock, and runs ground_truth_publisher, which reads Gazebo Pose_V
(pose/info or dynamic_pose/info) directly via gz-transport (ros_gz_bridge's
Pose_V -> TFMessage drops entity names) and publishes /ground_truth/odometry
in Gazebo ENU; localization_metrics converts to NED.

Defaults match MODEL=gz_x500 in the default world (model x500_0).
Optional raw-sensor bridges are omitted from the default launch so missing
gz sensor topic paths cannot fail the GT path; add them later if needed.
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

# Verified for MODEL=gz_x500, world default. Override via launch args if needed.
_DEFAULT_GZ_POSE = '/world/default/pose/info'
_DEFAULT_MODEL = 'x500_0'


def generate_launch_description():
    """Generate launch description for ground truth bridge."""
    gz_pose = LaunchConfiguration('gz_pose_topic')
    model_name = LaunchConfiguration('model_name')

    return LaunchDescription([
        DeclareLaunchArgument(
            'gz_pose_topic',
            default_value=_DEFAULT_GZ_POSE,
            description=(
                'Gazebo Pose_V topic. Prefer /world/default/pose/info; '
                'dynamic_pose/info is an alternative.'
            ),
        ),
        DeclareLaunchArgument(
            'model_name',
            default_value=_DEFAULT_MODEL,
            description='Gazebo model frame to extract (e.g. x500_0)',
        ),

        # Clock bridge: required when nodes use use_sim_time:=True.
        Node(
            package='ros_gz_bridge',
            executable='parameter_bridge',
            name='clock_bridge',
            output='screen',
            arguments=['/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock'],
            parameters=[{'use_sim_time': True}],
        ),

        # Gazebo Pose_V (read directly via gz-transport) -> nav_msgs/Odometry (ENU)
        Node(
            package='drone_localization',
            executable='ground_truth_publisher',
            name='ground_truth_publisher',
            output='screen',
            parameters=[
                {'use_sim_time': True},
                {'model_name': model_name},
                {'gz_pose_topic': gz_pose},
            ],
        ),
    ])
