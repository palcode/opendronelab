"""Setup script for drone_localization package."""
from setuptools import setup

package_name = 'drone_localization'

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
    maintainer_email='dev@opendronelab.local',
    description='Localization evaluation and baseline missions for OpenDroneLab',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'localization_metrics = drone_localization.localization_metrics:main',
            'ground_truth_publisher = drone_localization.ground_truth_publisher:main',
            'vision_px4_bridge = drone_localization.vision_px4_bridge:main',
        ],
    },
)
