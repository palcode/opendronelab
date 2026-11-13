# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Setup script for drone_perception package."""
from setuptools import setup

package_name = 'drone_perception'

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
    description='Computer vision and perception for OpenDroneLab',
    license='AGPL-3.0-only',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'edge_overlay_node = drone_perception.edge_overlay_node:main',
            'yolox_detector_node = drone_perception.yolox_detector_node:main',
        ],
    },
)
