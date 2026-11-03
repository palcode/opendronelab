"""Launch file for drone mission manager node."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    """Generate launch description for mission node."""
    return LaunchDescription([
        DeclareLaunchArgument(
            'target_altitude',
            default_value='3.0',
            description='Target altitude in meters (max 4.0m)'
        ),
        DeclareLaunchArgument(
            'hover_duration',
            default_value='10.0',
            description='Hover duration in seconds'
        ),
        Node(
            package='drone_mission_manager',
            executable='mission_node',
            name='mission_node',
            output='screen',
            emulate_tty=True,
            parameters=[{
                'target_altitude': LaunchConfiguration('target_altitude'),
                'hover_duration': LaunchConfiguration('hover_duration'),
            }],
        ),
    ])
