"""Setup script for drone_mission_manager package."""
from setuptools import setup

package_name = 'drone_mission_manager'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='OpenDroneLab',
    maintainer_email='13868623+palcode@users.noreply.github.com',
    description='PX4 offboard mission manager for OpenDroneLab',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'mission_node = drone_mission_manager.mission_node:main',
        ],
    },
)
