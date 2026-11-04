#!/usr/bin/env python3
"""
Edge overlay node for camera feed visualization.

Subscribes to camera image, runs Canny edge detection, overlays edges on frame,
and draws FPS and latency metrics as text.
"""
import time
import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image
from cv_bridge import CvBridge


def process_frame_with_overlay(frame, canny_low, canny_high):
    """
    Process frame with Canny edge detection and overlay.

    Args:
        frame: Input BGR image
        canny_low: Lower Canny threshold
        canny_high: Upper Canny threshold

    Returns:
        tuple: (processed_frame, processing_time_ms)
    """
    start_time = time.time()

    # Convert to grayscale for edge detection
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Apply Canny edge detection
    edges = cv2.Canny(gray, canny_low, canny_high)

    # Convert edges to BGR for overlay
    edges_bgr = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)

    # Overlay edges on original frame (green edges)
    edges_bgr[:, :, 0] = 0  # Zero out blue channel
    edges_bgr[:, :, 2] = 0  # Zero out red channel
    result = cv2.addWeighted(frame, 0.7, edges_bgr, 0.3, 0)

    processing_ms = (time.time() - start_time) * 1000.0

    return result, processing_ms


def add_text_overlay(frame, fps, processing_ms, latency_ms):
    """
    Add FPS, processing time, and latency text to frame.

    Args:
        frame: Input BGR image
        fps: Frames per second
        processing_ms: Processing time in milliseconds
        latency_ms: End-to-end latency in milliseconds

    Returns:
        Frame with text overlay
    """
    # Create text background for readability
    overlay = frame.copy()
    cv2.rectangle(overlay, (5, 5), (350, 100), (0, 0, 0), -1)
    frame = cv2.addWeighted(frame, 0.7, overlay, 0.3, 0)

    # Add text
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(frame, f'FPS: {fps:.1f}', (10, 30),
                font, 0.6, (0, 255, 0), 2)
    cv2.putText(frame, f'Processing: {processing_ms:.1f} ms', (10, 55),
                font, 0.6, (0, 255, 0), 2)
    cv2.putText(frame, f'Latency: {latency_ms:.1f} ms', (10, 80),
                font, 0.6, (0, 255, 0), 2)

    return frame


class EdgeOverlayNode(Node):
    """Edge detection and overlay node."""

    def __init__(self):
        """Initialize edge overlay node."""
        super().__init__('edge_overlay_node')

        # Parameters
        self.declare_parameter('canny_low', 50)
        self.declare_parameter('canny_high', 150)
        self.declare_parameter('process_every_n', 1)

        self.canny_low = self.get_parameter('canny_low').value
        self.canny_high = self.get_parameter('canny_high').value
        self.process_every_n = self.get_parameter('process_every_n').value

        # CV bridge
        self.bridge = CvBridge()

        # Frame processing state
        self.frame_count = 0
        self.last_log_time = time.time()
        self.frames_since_log = 0
        self.total_processing_ms = 0.0
        self.total_latency_ms = 0.0

        # Current metrics for overlay
        self.current_fps = 0.0
        self.current_processing_ms = 0.0
        self.current_latency_ms = 0.0

        # Sensor-data QoS for the subscriber (matches ros_gz_image / camera drivers).
        # Publisher uses the default (reliable) so rqt_image_view works without
        # a custom QoS override.
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,  # Only keep latest frame to avoid queuing
        )

        # Subscriber
        self.image_sub = self.create_subscription(
            Image,
            '/camera/image_raw',
            self.image_callback,
            sensor_qos,
        )

        # Publisher — default QoS (reliable, depth 10)
        self.annotated_pub = self.create_publisher(
            Image,
            '/perception/annotated',
            10,
        )

        # 1 Hz logging timer
        self.create_timer(1.0, self.log_metrics)

        self.get_logger().info(
            f'Edge overlay node started: '
            f'Canny=[{self.canny_low}, {self.canny_high}], '
            f'process_every_n={self.process_every_n}'
        )

    def _compute_latency_ms(self, msg):
        """Return capture→now latency in ms, or None if stamp/clock unusable."""
        stamp = msg.header.stamp
        if stamp.sec == 0 and stamp.nanosec == 0:
            return None
        try:
            now = self.get_clock().now()
            # Skip while sim clock has not started (use_sim_time + /clock not yet up)
            if now.nanoseconds == 0:
                return None
            msg_time = rclpy.time.Time.from_msg(stamp)
            latency_ms = (now - msg_time).nanoseconds / 1e6
            # Reject absurd values from clock-type mismatch or startup races
            if latency_ms < -50.0 or latency_ms > 10_000.0:
                return None
            return latency_ms
        except Exception:
            return None

    def image_callback(self, msg):
        """Process incoming image message."""
        self.frame_count += 1

        # Skip frames if configured
        if self.frame_count % self.process_every_n != 0:
            return

        try:
            # Convert ROS Image to OpenCV BGR. desired_encoding='bgr8' accepts
            # rgb8, bgr8, and mono8 (and other convertible encodings) via cv_bridge.
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')

            latency_ms = self._compute_latency_ms(msg)
            latency_for_overlay = (
                latency_ms if latency_ms is not None else self.current_latency_ms
            )

            # Process frame
            processed, processing_ms = process_frame_with_overlay(
                frame, self.canny_low, self.canny_high
            )

            # Add text overlay with current metrics
            annotated = add_text_overlay(
                processed,
                self.current_fps,
                processing_ms,
                latency_for_overlay,
            )

            # Publish annotated image
            out_msg = self.bridge.cv2_to_imgmsg(annotated, encoding='bgr8')
            out_msg.header = msg.header  # Preserve original header
            self.annotated_pub.publish(out_msg)

            # Update metrics for logging
            self.frames_since_log += 1
            self.total_processing_ms += processing_ms
            if latency_ms is not None:
                self.total_latency_ms += latency_ms

        except Exception as e:
            self.get_logger().error(f'Error processing image: {e}')

    def log_metrics(self):
        """Log metrics at 1 Hz."""
        if self.frames_since_log == 0:
            self.get_logger().info('Waiting for camera frames...')
            return

        # Calculate averages
        elapsed = time.time() - self.last_log_time
        fps = self.frames_since_log / elapsed if elapsed > 0 else 0.0
        avg_processing_ms = self.total_processing_ms / self.frames_since_log
        # Latency may be missing while clock/stamp settle; avoid ZeroDivision
        # by tracking only frames that contributed a latency sample via the
        # running total vs frames_since_log (approximate; fine for 1 Hz log).
        avg_latency_ms = self.total_latency_ms / self.frames_since_log

        # Update current metrics for overlay
        self.current_fps = fps
        self.current_processing_ms = avg_processing_ms
        self.current_latency_ms = avg_latency_ms

        self.get_logger().info(
            f'FPS: {fps:.1f}, Processing: {avg_processing_ms:.1f} ms, '
            f'Latency: {avg_latency_ms:.1f} ms'
        )

        # Reset counters
        self.last_log_time = time.time()
        self.frames_since_log = 0
        self.total_processing_ms = 0.0
        self.total_latency_ms = 0.0


def main(args=None):
    """Main entry point."""
    rclpy.init(args=args)
    node = EdgeOverlayNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
