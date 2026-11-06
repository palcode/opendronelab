"""VIO + optional PX4 external-vision bridge (does not change GPS defaults).

Start SITL with EV enabled explicitly, e.g.:
  docker rm -f odl-sim
  PX4_PARAM_EKF2_EV_CTRL=3 HEADLESS=1 GZ_SEED=1234 WORLD=vio_test \\
    MODEL=gz_x500_mono_cam ./scripts/launch-sitl.sh

EKF2_EV_CTRL=3 = horizontal + vertical position from vision (no yaw bit).
Leave EKF2_HGT_REF at baro (1) unless you intentionally switch height ref.

vision_px4_bridge aligns OpenVINS (Z-up, arbitrary yaw) to PX4 local NED using
vehicle_local_position before publishing; timestamps use the PX4 clock domain.

Hardware: forward use_sim_bridges:=false use_sim_time:=false and a filled
config_path. Still require an explicit PX4 EKF2_EV_CTRL opt-in on the FC —
this launch never changes the GPS-only default by itself.
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('gz_world', default_value='vio_test'),
        DeclareLaunchArgument('gz_model', default_value='x500_mono_cam_0'),
        DeclareLaunchArgument('use_sim_bridges', default_value='true'),
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('config_path', default_value=''),
        DeclareLaunchArgument('ros_image_topic', default_value='/camera/image_raw'),
        DeclareLaunchArgument('ros_camera_info_topic', default_value='/camera/camera_info'),
        DeclareLaunchArgument('ros_imu_topic', default_value='/sim/imu'),
        DeclareLaunchArgument('start_ground_truth', default_value='true'),
        DeclareLaunchArgument('publish_orientation', default_value='false'),
        DeclareLaunchArgument('publish_velocity', default_value='true'),
        DeclareLaunchArgument(
            'input_topic',
            default_value='/ov_msckf/odomimu',
            description='OpenVINS odometry topic into the EV bridge',
        ),
        DeclareLaunchArgument(
            'output_topic',
            default_value='/fmu/in/vehicle_visual_odometry',
            description='PX4 visual odometry input topic',
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([
                PathJoinSubstitution([
                    FindPackageShare('drone_bringup'),
                    'launch',
                    'vio.launch.py',
                ])
            ]),
            launch_arguments={
                'gz_world': LaunchConfiguration('gz_world'),
                'gz_model': LaunchConfiguration('gz_model'),
                'use_sim_bridges': LaunchConfiguration('use_sim_bridges'),
                'use_sim_time': LaunchConfiguration('use_sim_time'),
                'config_path': LaunchConfiguration('config_path'),
                'ros_image_topic': LaunchConfiguration('ros_image_topic'),
                'ros_camera_info_topic': LaunchConfiguration('ros_camera_info_topic'),
                'ros_imu_topic': LaunchConfiguration('ros_imu_topic'),
                'start_ground_truth': LaunchConfiguration('start_ground_truth'),
            }.items(),
        ),
        Node(
            package='drone_localization',
            executable='vision_px4_bridge',
            name='vision_px4_bridge',
            output='screen',
            parameters=[{
                'use_sim_time': LaunchConfiguration('use_sim_time'),
                'input_topic': LaunchConfiguration('input_topic'),
                'output_topic': LaunchConfiguration('output_topic'),
                'publish_orientation': LaunchConfiguration('publish_orientation'),
                'publish_velocity': LaunchConfiguration('publish_velocity'),
                'pose_variance': 0.05,
                'velocity_variance': 0.1,
            }],
        ),
    ])
