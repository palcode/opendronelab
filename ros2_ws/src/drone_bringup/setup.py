"""Setup script for drone_bringup package."""
import os
from glob import glob
from setuptools import setup

package_name = 'drone_bringup'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='OpenDroneLab',
    maintainer_email='dev@opendronelab.local',
    description='Launch files for OpenDroneLab',
    license='MIT',
    tests_require=['pytest'],
)
