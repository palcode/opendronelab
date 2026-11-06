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
