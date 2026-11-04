#!/usr/bin/env python3
"""
Ground truth publisher node.

Subscribes directly to the Gazebo Pose_V topic (e.g. /world/default/pose/info)
through gz-transport Python bindings and publishes nav_msgs/Odometry for the
configured model.

Why not ros_gz_bridge: the Pose_V -> tf2_msgs/TFMessage conversion drops the
entity names (every child_frame_id arrives empty), so the drone cannot be
identified. gz-transport keeps the names.

Position/orientation are left in Gazebo ENU (world). localization_metrics
converts ENU -> NED when comparing against PX4 vehicle_local_position.
The stamp is the Gazebo sim time from the Pose_V header, matching /clock.
"""
import threading

import rclpy
from rclpy.node import Node
from builtin_interfaces.msg import Time
from nav_msgs.msg import Odometry

from gz.transport13 import Node as GzNode
from gz.msgs10.pose_v_pb2 import Pose_V


def matches_model(name: str, model_name: str) -> bool:
    """Match model name, with optional /base_link or ::base_link suffix."""
    if name == model_name:
        return True
    return any(name.startswith(model_name + sep) for sep in ('/', '::'))


class GroundTruthPublisher(Node):
    """Publish ground truth odometry from Gazebo pose info."""

    def __init__(self):
        """Initialize ground truth publisher node."""
        super().__init__('ground_truth_publisher')

        self.declare_parameter('model_name', 'x500_0')
        self.declare_parameter('gz_pose_topic', '/world/default/pose/info')
        self.declare_parameter('odom_topic', '/ground_truth/odometry')
        self.model_name = self.get_parameter('model_name').value
        gz_topic = self.get_parameter('gz_pose_topic').value
        odom_topic = self.get_parameter('odom_topic').value

        self.odom_pub = self.create_publisher(Odometry, odom_topic, 10)
        self._lock = threading.Lock()
        self.seen_names = set()
        self.model_found = False
        self._miss_count = 0

        self._gz_node = GzNode()
        if not self._gz_node.subscribe(Pose_V, gz_topic, self._gz_callback):
            raise RuntimeError(f'Could not subscribe to gz topic {gz_topic}')

        self.get_logger().info(
            f'Ground truth publisher started; gz={gz_topic} '
            f'model={self.model_name} -> {odom_topic}'
        )

    def _gz_callback(self, msg: Pose_V):
        """Handle a Gazebo Pose_V message (runs on a gz-transport thread)."""
        with self._lock:
            for pose in msg.pose:
                if matches_model(pose.name, self.model_name):
                    if not self.model_found:
                        self.model_found = True
                        self.get_logger().info(
                            f'Found target model: {pose.name} (id {pose.id})'
                        )
                    self._publish(msg, pose)
                    return
            for pose in msg.pose:
                self.seen_names.add(pose.name)
            self._miss_count += 1
            if not self.model_found and self._miss_count % 200 == 1:
                self.get_logger().warn(
                    f'Model {self.model_name} not found. '
                    f'Seen: {sorted(self.seen_names)}'
                )

    def _publish(self, msg: Pose_V, pose):
        """Publish odometry (Gazebo ENU, sim-time stamp)."""
        odom = Odometry()
        stamp = msg.header.stamp if msg.HasField('header') else pose.header.stamp
        odom.header.stamp = Time(sec=stamp.sec, nanosec=stamp.nsec)
        odom.header.frame_id = 'world'  # Gazebo ENU
        odom.child_frame_id = self.model_name
        p, q = pose.position, pose.orientation
        odom.pose.pose.position.x = p.x
        odom.pose.pose.position.y = p.y
        odom.pose.pose.position.z = p.z
        odom.pose.pose.orientation.x = q.x
        odom.pose.pose.orientation.y = q.y
        odom.pose.pose.orientation.z = q.z
        odom.pose.pose.orientation.w = q.w
        # Velocity not available from Pose_V; metrics use position only.
        self.odom_pub.publish(odom)


def main(args=None):
    """Main entry point."""
    rclpy.init(args=args)
    node = GroundTruthPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
