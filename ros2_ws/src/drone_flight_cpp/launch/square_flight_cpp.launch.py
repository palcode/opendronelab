"""Launch the C++ square flight (classic OFFBOARD, matches Python)."""
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    """Generate launch description."""
    return LaunchDescription([
        Node(
            package='drone_flight_cpp',
            executable='square_flight_cpp',
            name='square_flight_cpp',
            output='screen',
        ),
    ])
