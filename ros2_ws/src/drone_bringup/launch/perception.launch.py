# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Launch file for camera bridge and perception pipeline."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    """Generate launch description for perception pipeline."""
    return LaunchDescription([
        DeclareLaunchArgument(
            'rqt_image_view',
            default_value='false',
            description='Launch rqt_image_view for visualization',
        ),
        DeclareLaunchArgument(
            'gz_image_topic',
            default_value=(
                '/world/default/model/x500_mono_cam_0/'
                'link/camera_link/sensor/imager/image'
            ),
            description='Gazebo image topic name',
        ),
        DeclareLaunchArgument(
            'gz_camera_info_topic',
            default_value=(
                '/world/default/model/x500_mono_cam_0/'
                'link/camera_link/sensor/imager/camera_info'
            ),
            description='Gazebo camera info topic name',
        ),

        # Include camera bridge launch file
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([
                PathJoinSubstitution([
                    FindPackageShare('drone_bringup'),
                    'launch',
                    'camera_bridge.launch.py',
                ])
            ]),
            launch_arguments={
                'gz_image_topic': LaunchConfiguration('gz_image_topic'),
                'gz_camera_info_topic': LaunchConfiguration('gz_camera_info_topic'),
            }.items(),
        ),

        # Edge overlay node
        Node(
            package='drone_perception',
            executable='edge_overlay_node',
            name='edge_overlay_node',
            output='screen',
            emulate_tty=True,
            parameters=[{
                'use_sim_time': True,
                'canny_low': 50,
                'canny_high': 150,
                'process_every_n': 1,
            }],
        ),

        # Optional rqt_image_view (topic as positional argument)
        Node(
            package='rqt_image_view',
            executable='rqt_image_view',
            name='rqt_image_view',
            arguments=['/perception/annotated'],
            condition=IfCondition(LaunchConfiguration('rqt_image_view')),
            parameters=[{'use_sim_time': True}],
        ),
    ])
