# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Launch file for camera bridge and YOLOX object detection."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def _expand_topics(context, *args, **kwargs):
    """Build gz topic defaults from gz_world unless explicitly overridden."""
    del args, kwargs
    world = LaunchConfiguration('gz_world').perform(context)
    img = LaunchConfiguration('gz_image_topic').perform(context)
    info = LaunchConfiguration('gz_camera_info_topic').perform(context)

    default_img = (
        f'/world/{world}/model/x500_mono_cam_0/link/camera_link/sensor/imager/image'
    )
    default_info = (
        f'/world/{world}/model/x500_mono_cam_0/link/camera_link/sensor/imager/camera_info'
    )
    # Empty string means "use world-derived default".
    if not img:
        img = default_img
    if not info:
        info = default_info

    return [
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([
                PathJoinSubstitution([
                    FindPackageShare('drone_bringup'),
                    'launch',
                    'camera_bridge.launch.py',
                ])
            ]),
            launch_arguments={
                'gz_image_topic': img,
                'gz_camera_info_topic': info,
            }.items(),
        ),
        Node(
            package='drone_perception',
            executable='yolox_detector_node',
            name='yolox_detector_node',
            output='screen',
            emulate_tty=True,
            parameters=[{
                'use_sim_time': True,
                'model_path': LaunchConfiguration('model_path'),
                'score_threshold': LaunchConfiguration('score_threshold'),
                'nms_threshold': LaunchConfiguration('nms_threshold'),
                'process_every_n': LaunchConfiguration('process_every_n'),
                'num_threads': 4,
                'force_cpu': LaunchConfiguration('force_cpu'),
            }],
        ),
        Node(
            package='rqt_image_view',
            executable='rqt_image_view',
            name='rqt_image_view',
            arguments=['/perception/detections_image'],
            condition=IfCondition(LaunchConfiguration('rqt_image_view')),
            parameters=[{'use_sim_time': True}],
        ),
    ]


def generate_launch_description():
    """Generate launch description for object detection pipeline."""
    return LaunchDescription([
        DeclareLaunchArgument(
            'rqt_image_view',
            default_value='false',
            description='Launch rqt_image_view for visualization',
        ),
        DeclareLaunchArgument(
            'gz_world',
            default_value='detection_test',
            description='Gazebo world name (must match PX4_GZ_WORLD / SDF world name)',
        ),
        DeclareLaunchArgument(
            'gz_image_topic',
            default_value='',
            description='Gazebo image topic; empty = derive from gz_world',
        ),
        DeclareLaunchArgument(
            'gz_camera_info_topic',
            default_value='',
            description='Gazebo camera_info topic; empty = derive from gz_world',
        ),
        DeclareLaunchArgument(
            'model_path',
            default_value='/data/models/yolox_nano.onnx',
            description='Path to YOLOX ONNX model',
        ),
        DeclareLaunchArgument(
            'score_threshold',
            default_value='0.35',
            description='Detection score threshold',
        ),
        DeclareLaunchArgument(
            'nms_threshold',
            default_value='0.45',
            description='NMS IoU threshold',
        ),
        DeclareLaunchArgument(
            'process_every_n',
            default_value='3',
            description='Process every Nth frame (1=all frames)',
        ),
        DeclareLaunchArgument(
            'force_cpu',
            default_value='false',
            description='Force CPUExecutionProvider (skip CUDA even if available)',
        ),
        OpaqueFunction(function=_expand_topics),
    ])
