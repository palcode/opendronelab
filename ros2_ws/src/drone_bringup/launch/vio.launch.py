"""Launch OpenVINS VIO against Gazebo mono_cam + IMU (Phase 4b).

OpenVINS (GPL-3) is a separate process from an isolated overlay
(/data/ros2_build/openvins/install). This launch file lives in drone_bringup
and only starts bridges + ov_msckf via ros2; it does not link OpenVINS into
first-party libraries.

Defaults match WORLD=detection_test MODEL=gz_x500_mono_cam (GstCamera off).
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from ament_index_python.packages import PackageNotFoundError, get_package_prefix
import os


def _expand(context, *args, **kwargs):
    del args, kwargs
    world = LaunchConfiguration('gz_world').perform(context)
    model = LaunchConfiguration('gz_model').perform(context)
    img = LaunchConfiguration('gz_image_topic').perform(context)
    info = LaunchConfiguration('gz_camera_info_topic').perform(context)
    imu = LaunchConfiguration('gz_imu_topic').perform(context)
    config_path = LaunchConfiguration('config_path').perform(context)
    start_ov = LaunchConfiguration('start_openvins').perform(context)
    start_gt = LaunchConfiguration('start_ground_truth').perform(context)

    if not img:
        img = (
            f'/world/{world}/model/{model}/link/camera_link/sensor/imager/image'
        )
    if not info:
        info = (
            f'/world/{world}/model/{model}/link/camera_link/sensor/imager/camera_info'
        )
    if not imu:
        imu = (
            f'/world/{world}/model/{model}/link/base_link/sensor/imu_sensor/imu'
        )
    if not config_path:
        # Repo config mounted at /workspace inside odl-sim.
        config_path = '/workspace/config/openvins/gz_x500_mono_cam/estimator_config.yaml'

    actions = []

    # Camera + clock (clock_bridge is inside camera_bridge.launch.py).
    actions.append(
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
        )
    )

    # Gazebo IMU -> /sim/imu (sensor_msgs/Imu), same sim clock as camera.
    actions.append(
        Node(
            package='ros_gz_bridge',
            executable='parameter_bridge',
            name='imu_bridge',
            output='screen',
            arguments=[[
                imu,
                '@sensor_msgs/msg/Imu[gz.msgs.IMU',
            ]],
            remappings=[(imu, '/sim/imu')],
            parameters=[{'use_sim_time': True}],
        )
    )

    if start_gt.lower() in ('1', 'true', 'yes'):
        # Start GT publisher only (camera_bridge already provides /clock).
        pose_topic = f'/world/{world}/pose/info'
        actions.append(
            Node(
                package='drone_localization',
                executable='ground_truth_publisher',
                name='ground_truth_publisher',
                output='screen',
                parameters=[
                    {'use_sim_time': True},
                    {'model_name': model},
                    {'gz_pose_topic': pose_topic},
                ],
            )
        )

    if start_ov.lower() in ('1', 'true', 'yes'):
        try:
            get_package_prefix('ov_msckf')
        except PackageNotFoundError as exc:
            raise RuntimeError(
                'ov_msckf not on ROS package path. Build/source the isolated '
                'OpenVINS overlay first: '
                'source /data/ros2_build/openvins/install/setup.bash '
                '(see scripts/build-openvins.sh).'
            ) from exc
        if not os.path.isfile(config_path):
            raise RuntimeError(f'OpenVINS config_path missing: {config_path}')

        actions.append(
            Node(
                package='ov_msckf',
                executable='run_subscribe_msckf',
                name='run_subscribe_msckf',
                namespace='ov_msckf',
                output='screen',
                parameters=[
                    {'use_sim_time': True},
                    {'verbosity': LaunchConfiguration('verbosity')},
                    {'use_stereo': False},
                    {'max_cameras': 1},
                    {'save_total_state': False},
                    {'config_path': config_path},
                ],
            )
        )

    return actions


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'gz_world',
            default_value='vio_test',
            description='Gazebo world name (must match PX4_GZ_WORLD)',
        ),
        DeclareLaunchArgument(
            'gz_model',
            default_value='x500_mono_cam_0',
            description='Gazebo model instance name',
        ),
        DeclareLaunchArgument(
            'gz_image_topic',
            default_value='',
            description='Gazebo image topic; empty = derive from world/model',
        ),
        DeclareLaunchArgument(
            'gz_camera_info_topic',
            default_value='',
            description='Gazebo camera_info topic; empty = derive',
        ),
        DeclareLaunchArgument(
            'gz_imu_topic',
            default_value='',
            description='Gazebo IMU topic; empty = derive',
        ),
        DeclareLaunchArgument(
            'config_path',
            default_value='',
            description='Path to OpenVINS estimator_config.yaml',
        ),
        DeclareLaunchArgument(
            'start_openvins',
            default_value='true',
            description='Start ov_msckf run_subscribe_msckf',
        ),
        DeclareLaunchArgument(
            'start_ground_truth',
            default_value='true',
            description='Also start localization.launch.py (GT + clock)',
        ),
        DeclareLaunchArgument(
            'verbosity',
            default_value='INFO',
            description='OpenVINS verbosity',
        ),
        OpaqueFunction(function=_expand),
    ])
