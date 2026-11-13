# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Launch the C++ square flight (classic OFFBOARD, matches Python).

Optional args (defaults match baseline GPS square):
  cruise_speed   m/s velocity feedforward toward waypoint (0 = position-only)
  yaw_spin_rate  rad/s continuous yaw while flying (0 = yaw fixed at 0)
  yaw_spin_after_wp  only spin once corner_index >= this (1 = after hover wp0)
  corner_hold_time, square_side, altitude, mission_timeout
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    """Generate launch description."""
    return LaunchDescription([
        DeclareLaunchArgument('cruise_speed', default_value='0.0'),
        DeclareLaunchArgument('yaw_spin_rate', default_value='0.0'),
        DeclareLaunchArgument('yaw_spin_after_wp', default_value='0'),
        DeclareLaunchArgument('corner_hold_time', default_value='3.0'),
        DeclareLaunchArgument('square_side', default_value='10.0'),
        DeclareLaunchArgument('altitude', default_value='5.0'),
        DeclareLaunchArgument('mission_timeout', default_value='180.0'),
        Node(
            package='drone_flight_cpp',
            executable='square_flight_cpp',
            name='square_flight_cpp',
            output='screen',
            parameters=[{
                'cruise_speed': ParameterValue(
                    LaunchConfiguration('cruise_speed'), value_type=float),
                'yaw_spin_rate': ParameterValue(
                    LaunchConfiguration('yaw_spin_rate'), value_type=float),
                'yaw_spin_after_wp': ParameterValue(
                    LaunchConfiguration('yaw_spin_after_wp'), value_type=int),
                'corner_hold_time': ParameterValue(
                    LaunchConfiguration('corner_hold_time'), value_type=float),
                'square_side': ParameterValue(
                    LaunchConfiguration('square_side'), value_type=float),
                'altitude': ParameterValue(
                    LaunchConfiguration('altitude'), value_type=float),
                'mission_timeout': ParameterValue(
                    LaunchConfiguration('mission_timeout'), value_type=float),
            }],
        ),
    ])
