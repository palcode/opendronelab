"""Launch OpenVINS VIO (Phase 4b).

OpenVINS (GPL-3) is a separate process from an isolated overlay
(/data/ros2_build/openvins/install). This launch file lives in drone_bringup
and only starts bridges + ov_msckf via ros2; it does not link OpenVINS into
first-party libraries.

SITL defaults (use_sim_bridges:=true): Gazebo mono_cam + /sim/imu + optional GT.
Hardware bring-up: set use_sim_bridges:=false use_sim_time:=false and point
config_path at a filled Kalibr tree (see config/openvins/hardware_placeholder/).
OpenVINS image/IMU topics come from that Kalibr YAML (rostopic fields), not
from invented vendor names in this launch file.
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from ament_index_python.packages import PackageNotFoundError, get_package_prefix
import os


def _truthy(value: str) -> bool:
    return value.lower() in ('1', 'true', 'yes')


def _expand(context, *args, **kwargs):
    del args, kwargs
    world = LaunchConfiguration('gz_world').perform(context)
    model = LaunchConfiguration('gz_model').perform(context)
    img = LaunchConfiguration('gz_image_topic').perform(context)
    info = LaunchConfiguration('gz_camera_info_topic').perform(context)
    imu = LaunchConfiguration('gz_imu_topic').perform(context)
    ros_image = LaunchConfiguration('ros_image_topic').perform(context)
    ros_info = LaunchConfiguration('ros_camera_info_topic').perform(context)
    ros_imu = LaunchConfiguration('ros_imu_topic').perform(context)
    config_path = LaunchConfiguration('config_path').perform(context)
    start_ov = LaunchConfiguration('start_openvins').perform(context)
    start_gt = LaunchConfiguration('start_ground_truth').perform(context)
    use_sim_bridges = _truthy(LaunchConfiguration('use_sim_bridges').perform(context))
    use_sim_time = _truthy(LaunchConfiguration('use_sim_time').perform(context))

    if not ros_image:
        ros_image = '/camera/image_raw'
    if not ros_info:
        ros_info = '/camera/camera_info'
    if not ros_imu:
        ros_imu = '/sim/imu'

    if use_sim_bridges:
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

    if use_sim_bridges:
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
                    'ros_image_topic': ros_image,
                    'ros_camera_info_topic': ros_info,
                }.items(),
            )
        )

        # Gazebo IMU -> ros_imu_topic (default /sim/imu), same sim clock as camera.
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
                remappings=[(imu, ros_imu)],
                parameters=[{'use_sim_time': use_sim_time}],
            )
        )

        if _truthy(start_gt):
            pose_topic = f'/world/{world}/pose/info'
            actions.append(
                Node(
                    package='drone_localization',
                    executable='ground_truth_publisher',
                    name='ground_truth_publisher',
                    output='screen',
                    parameters=[
                        {'use_sim_time': use_sim_time},
                        {'model_name': model},
                        {'gz_pose_topic': pose_topic},
                    ],
                )
            )
    # else: hardware/drivers already publish Image/CameraInfo/Imu. OpenVINS
    # subscribes via kalibr_* rostopic fields in config_path. No GT in that path.

    if _truthy(start_ov):
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
                    {'use_sim_time': use_sim_time},
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
            description='Gazebo world name (must match PX4_GZ_WORLD); SITL only',
        ),
        DeclareLaunchArgument(
            'gz_model',
            default_value='x500_mono_cam_0',
            description='Gazebo model instance name; SITL only',
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
            'ros_image_topic',
            default_value='/camera/image_raw',
            description='ROS image topic after gz bridge (SITL) or document match for Kalibr',
        ),
        DeclareLaunchArgument(
            'ros_camera_info_topic',
            default_value='/camera/camera_info',
            description='ROS CameraInfo topic after gz bridge (SITL)',
        ),
        DeclareLaunchArgument(
            'ros_imu_topic',
            default_value='/sim/imu',
            description='ROS Imu topic after gz bridge (SITL). Hardware: set in Kalibr YAML.',
        ),
        DeclareLaunchArgument(
            'use_sim_bridges',
            default_value='true',
            description='If true, start Gazebo camera/IMU/(optional GT) bridges. '
                        'False for hardware drivers (no gz).',
        ),
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='true',
            description='ROS use_sim_time. True for SITL; false for most hardware clocks.',
        ),
        DeclareLaunchArgument(
            'config_path',
            default_value='',
            description='Path to OpenVINS estimator_config.yaml '
                        '(empty = SITL gz_x500_mono_cam tree)',
        ),
        DeclareLaunchArgument(
            'start_openvins',
            default_value='true',
            description='Start ov_msckf run_subscribe_msckf',
        ),
        DeclareLaunchArgument(
            'start_ground_truth',
            default_value='true',
            description='Start ground_truth_publisher (ignored unless use_sim_bridges)',
        ),
        DeclareLaunchArgument(
            'verbosity',
            default_value='INFO',
            description='OpenVINS verbosity',
        ),
        OpaqueFunction(function=_expand),
    ])
