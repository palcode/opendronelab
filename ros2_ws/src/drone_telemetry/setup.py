"""Setup script for drone_telemetry package."""
from setuptools import setup

package_name = 'drone_telemetry'

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
    description='PX4 telemetry subscriber for OpenDroneLab',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'telemetry_node = drone_telemetry.telemetry_node:main',
        ],
    },
)
