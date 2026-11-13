# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Launch file for Gazebo camera bridge."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

# Default Gazebo topics verified live on odl-sim with gz_x500_mono_cam.
_DEFAULT_GZ_IMAGE = (
    '/world/default/model/x500_mono_cam_0/link/camera_link/sensor/imager/image'
)
_DEFAULT_GZ_INFO = (
    '/world/default/model/x500_mono_cam_0/link/camera_link/sensor/imager/camera_info'
)


def generate_launch_description():
    """Generate launch description for camera bridge."""
    gz_image = LaunchConfiguration('gz_image_topic')
    gz_info = LaunchConfiguration('gz_camera_info_topic')
    ros_image = LaunchConfiguration('ros_image_topic')
    ros_info = LaunchConfiguration('ros_camera_info_topic')

    return LaunchDescription([
        DeclareLaunchArgument(
            'gz_image_topic',
            default_value=_DEFAULT_GZ_IMAGE,
            description='Gazebo image topic name',
        ),
        DeclareLaunchArgument(
            'gz_camera_info_topic',
            default_value=_DEFAULT_GZ_INFO,
            description='Gazebo camera info topic name',
        ),
        DeclareLaunchArgument(
            'ros_image_topic',
            default_value='/camera/image_raw',
            description='ROS 2 image topic name',
        ),
        DeclareLaunchArgument(
            'ros_camera_info_topic',
            default_value='/camera/camera_info',
            description='ROS 2 camera info topic name',
        ),

        # Clock bridge: Gazebo → ROS (direction '['). Required for use_sim_time.
        Node(
            package='ros_gz_bridge',
            executable='parameter_bridge',
            name='clock_bridge',
            output='screen',
            arguments=['/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock'],
            parameters=[{'use_sim_time': True}],
        ),

        # Image bridge via ros_gz_image (handles image transport cleanly).
        # image_bridge publishes a ROS topic with the same name as the gz topic;
        # remapping renames it to /camera/image_raw.
        Node(
            package='ros_gz_image',
            executable='image_bridge',
            name='image_bridge',
            output='screen',
            arguments=[gz_image],
            remappings=[(gz_image, ros_image)],
            parameters=[{'use_sim_time': True}],
        ),

        # CameraInfo bridge: Gazebo → ROS. Argument is topic@ros_type[gz_type
        # (the '[' is the direction indicator, not a bracket pair).
        Node(
            package='ros_gz_bridge',
            executable='parameter_bridge',
            name='camera_info_bridge',
            output='screen',
            arguments=[[
                gz_info,
                '@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo',
            ]],
            remappings=[(gz_info, ros_info)],
            parameters=[{'use_sim_time': True}],
        ),
    ])
