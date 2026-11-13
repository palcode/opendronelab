#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""YOLOX object detector node for real-time detection.

Uses YOLOX-nano ONNX with CUDA EP when available, CPU EP otherwise.
Pass force_cpu:=true to stick to CPU. The Megvii 0.1.1rc0 ONNX export
ships with decode_in_inference=False, so outputs are raw (relative to grid
cells) and must go through demo_postprocess (grids + strides, exp on wh)
before xywh→xyxy conversion — matching YOLOX onnx_inference demo.
"""
import time

import cv2
import numpy as np
import onnxruntime as ort
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2D, Detection2DArray, ObjectHypothesisWithPose
from cv_bridge import CvBridge

# COCO class names (80 classes)
COCO_CLASSES = [
    'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat',
    'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird', 'cat',
    'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe', 'backpack',
    'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee', 'skis', 'snowboard', 'sports ball',
    'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard', 'tennis racket',
    'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple',
    'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair',
    'couch', 'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse',
    'remote', 'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink', 'refrigerator',
    'book', 'clock', 'vase', 'scissors', 'teddy bear', 'hair drier', 'toothbrush'
]


def letterbox(img, target_size=(416, 416)):
    """Resize with letterboxing; place content at top-left (official YOLOX preproc).

    Pad value is 114. Returns (padded_hwc_uint8, scale, (pad_h, pad_w)) where
    pad_h/pad_w are the top/left offsets (always 0 for top-left placement).
    """
    target_h, target_w = target_size
    img_h, img_w = img.shape[:2]

    scale = min(target_w / img_w, target_h / img_h)
    new_w = int(img_w * scale)
    new_h = int(img_h * scale)

    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    # Official YOLOX preproc: top-left placement, pad 114 on bottom/right.
    pad_h = 0
    pad_w = 0
    padded = np.full((target_h, target_w, 3), 114, dtype=np.uint8)
    padded[0:new_h, 0:new_w] = resized

    return padded, scale, (pad_h, pad_w)


def preprocess_yolox(img, input_size=(416, 416)):
    """Preprocess BGR image for YOLOX: letterbox, float32 CHW, no normalisation."""
    padded, scale, padding = letterbox(img, input_size)
    input_tensor = padded.astype(np.float32)
    input_tensor = np.transpose(input_tensor, (2, 0, 1))  # HWC -> CHW
    input_tensor = np.expand_dims(input_tensor, axis=0)
    return input_tensor, scale, padding


def demo_postprocess(outputs, img_size=(416, 416), p6=False):
    """Official YOLOX ONNX postprocess (grids + strides, exp on wh).

    outputs: (1, N, 85) raw network output with decode_in_inference=False.
    Mutates and returns outputs with absolute cx,cy,w,h in model input pixels.
    """
    grids = []
    expanded_strides = []
    strides = [8, 16, 32] if not p6 else [8, 16, 32, 64]

    hsizes = [img_size[0] // stride for stride in strides]
    wsizes = [img_size[1] // stride for stride in strides]

    for hsize, wsize, stride in zip(hsizes, wsizes, strides):
        xv, yv = np.meshgrid(np.arange(wsize), np.arange(hsize))
        grid = np.stack((xv, yv), 2).reshape(1, -1, 2)
        grids.append(grid)
        shape = grid.shape[:2]
        expanded_strides.append(np.full((*shape, 1), stride))

    grids = np.concatenate(grids, 1)
    expanded_strides = np.concatenate(expanded_strides, 1)
    outputs = outputs.copy()
    outputs[..., :2] = (outputs[..., :2] + grids) * expanded_strides
    outputs[..., 2:4] = np.exp(outputs[..., 2:4]) * expanded_strides
    return outputs


def decode_yolox_outputs(outputs, input_size=(416, 416), strides=None):
    """Decode YOLOX ONNX outputs to corner boxes.

    Returns (N, 7): [x1, y1, x2, y2, obj_conf, class_conf, class_id].
    strides is accepted for API compatibility; demo_postprocess uses the
    standard [8, 16, 32] set for YOLOX-nano.
    """
    del strides  # unused; kept for callers/tests
    if len(outputs.shape) == 2:
        outputs = outputs[None, ...]

    # Raw ONNX (decode_in_inference=False) → absolute cxcywh
    outputs = demo_postprocess(outputs, img_size=input_size)
    outputs = outputs[0]

    boxes = outputs[:, :4]
    objectness = outputs[:, 4:5]
    class_scores = outputs[:, 5:]

    x1 = boxes[:, 0] - boxes[:, 2] / 2
    y1 = boxes[:, 1] - boxes[:, 3] / 2
    x2 = boxes[:, 0] + boxes[:, 2] / 2
    y2 = boxes[:, 1] + boxes[:, 3] / 2

    class_conf = np.max(class_scores, axis=1, keepdims=True)
    class_id = np.argmax(class_scores, axis=1, keepdims=True).astype(np.float32)

    detections = np.concatenate([
        np.stack([x1, y1, x2, y2], axis=1),
        objectness,
        class_conf,
        class_id,
    ], axis=1)
    return detections


def nms(detections, score_threshold=0.5, nms_threshold=0.45):
    """Non-maximum suppression. detections: (N, 7)."""
    if len(detections) == 0:
        return np.array([])

    scores = detections[:, 4] * detections[:, 5]
    mask = scores >= score_threshold
    detections = detections[mask]
    if len(detections) == 0:
        return np.array([])
    scores = scores[mask]

    order = scores.argsort()[::-1]
    keep = []
    while len(order) > 0:
        i = order[0]
        keep.append(i)

        xx1 = np.maximum(detections[i, 0], detections[order[1:], 0])
        yy1 = np.maximum(detections[i, 1], detections[order[1:], 1])
        xx2 = np.minimum(detections[i, 2], detections[order[1:], 2])
        yy2 = np.minimum(detections[i, 3], detections[order[1:], 3])

        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h

        area_i = (detections[i, 2] - detections[i, 0]) * (detections[i, 3] - detections[i, 1])
        area_order = (
            (detections[order[1:], 2] - detections[order[1:], 0]) *
            (detections[order[1:], 3] - detections[order[1:], 1])
        )
        union = area_i + area_order - inter
        iou = inter / (union + 1e-6)

        order = order[1:][iou <= nms_threshold]

    return detections[keep]


def unscale_boxes(boxes, scale, padding, original_shape):
    """Convert boxes from model input space back to original image space."""
    pad_h, pad_w = padding
    boxes = boxes.copy()
    boxes[:, 0] -= pad_w
    boxes[:, 1] -= pad_h
    boxes[:, 2] -= pad_w
    boxes[:, 3] -= pad_h
    boxes /= scale
    boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0, original_shape[1])
    boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0, original_shape[0])
    return boxes


class YOLOXDetectorNode(Node):
    """YOLOX object detection node."""

    def __init__(self):
        super().__init__('yolox_detector_node')

        self.declare_parameter('model_path', '/data/models/yolox_nano.onnx')
        self.declare_parameter('score_threshold', 0.35)
        self.declare_parameter('nms_threshold', 0.45)
        self.declare_parameter('process_every_n', 3)
        self.declare_parameter('num_threads', 4)
        self.declare_parameter('force_cpu', False)

        model_path = self.get_parameter('model_path').value
        self.score_threshold = self.get_parameter('score_threshold').value
        self.nms_threshold = self.get_parameter('nms_threshold').value
        self.process_every_n = int(self.get_parameter('process_every_n').value)
        num_threads = int(self.get_parameter('num_threads').value)
        _fc = self.get_parameter('force_cpu').value
        if isinstance(_fc, str):
            force_cpu = _fc.strip().lower() in ('1', 'true', 'yes', 'on')
        else:
            force_cpu = bool(_fc)

        try:
            # onnxruntime-gpu ships CUDA libs via nvidia-* pip wheels; preload
            # them so the CUDA EP can resolve cublas/cudnn without a system CUDA.
            # API is ort.preload_dlls() (function on the package), not a submodule.
            try:
                ort.preload_dlls()
            except Exception as preload_err:  # pragma: no cover - best effort
                self.get_logger().warn(f'ORT preload_dlls skipped: {preload_err}')

            available = ort.get_available_providers()
            if force_cpu:
                providers = ['CPUExecutionProvider']
            else:
                providers = []
                if 'CUDAExecutionProvider' in available:
                    providers.append('CUDAExecutionProvider')
                providers.append('CPUExecutionProvider')

            sess_options = ort.SessionOptions()
            sess_options.intra_op_num_threads = num_threads
            sess_options.inter_op_num_threads = num_threads
            self.session = ort.InferenceSession(
                model_path, sess_options, providers=providers,
            )
            self.input_name = self.session.get_inputs()[0].name
            input_shape = self.session.get_inputs()[0].shape
            # ONNX shape is [N, C, H, W]
            self.input_size = (int(input_shape[2]), int(input_shape[3]))
            active = self.session.get_providers()
            self.get_logger().info(f'Loaded YOLOX model from {model_path}')
            self.get_logger().info(f'Input size: {self.input_size}')
            self.get_logger().info(
                f'ORT providers available={available} requested={providers} '
                f'active={active} force_cpu={force_cpu}'
            )
            if (
                not force_cpu
                and 'CUDAExecutionProvider' in providers
                and 'CUDAExecutionProvider' not in active
            ):
                self.get_logger().warn(
                    'CUDAExecutionProvider was requested but is not active; '
                    'falling back to CPU. Check nvidia runtime / ORT GPU install.'
                )
        except Exception as e:
            self.get_logger().error(
                f'Failed to load model at {model_path}: {e}. '
                f'Run scripts/fetch-models.sh first.'
            )
            raise

        self.bridge = CvBridge()
        self.frame_count = 0
        self.inference_running = False
        self.last_log_time = time.time()
        self.frames_since_log = 0
        self.total_inference_ms = 0.0
        self.total_detections = 0
        self.current_fps = 0.0
        self.current_inference_ms = 0.0

        qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )

        self.image_sub = self.create_subscription(
            Image,
            '/camera/image_raw',
            self.image_callback,
            qos_profile,
        )

        self.detections_pub = self.create_publisher(
            Detection2DArray,
            '/perception/detections',
            10,
        )

        self.detections_image_pub = self.create_publisher(
            Image,
            '/perception/detections_image',
            qos_profile,
        )

        self.create_timer(1.0, self.log_metrics)

        self.get_logger().info(
            f'YOLOX detector started: '
            f'score_threshold={self.score_threshold}, '
            f'nms_threshold={self.nms_threshold}, '
            f'process_every_n={self.process_every_n}'
        )

    def image_callback(self, msg):
        self.frame_count += 1
        if self.frame_count % self.process_every_n != 0:
            return
        if self.inference_running:
            return

        self.inference_running = True
        try:
            # Camera bridge publishes rgb8; convert to BGR for YOLOX preproc.
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            original_shape = frame.shape[:2]

            input_tensor, scale, padding = preprocess_yolox(frame, self.input_size)

            start_time = time.time()
            outputs = self.session.run(None, {self.input_name: input_tensor})
            inference_ms = (time.time() - start_time) * 1000.0

            detections = decode_yolox_outputs(outputs[0], self.input_size)
            detections = nms(detections, self.score_threshold, self.nms_threshold)

            if len(detections) > 0:
                boxes = detections[:, :4].copy()
                boxes = unscale_boxes(boxes, scale, padding, original_shape)
                detections[:, :4] = boxes

            self.publish_detections(detections, msg.header)

            annotated = self.draw_detections(frame, detections)
            annotated_msg = self.bridge.cv2_to_imgmsg(annotated, encoding='bgr8')
            annotated_msg.header = msg.header
            self.detections_image_pub.publish(annotated_msg)

            self.frames_since_log += 1
            self.total_inference_ms += inference_ms
            self.total_detections += len(detections)
        except Exception as e:
            self.get_logger().error(f'Error processing image: {e}')
        finally:
            self.inference_running = False

    def publish_detections(self, detections, header):
        msg = Detection2DArray()
        msg.header = header

        for det in detections:
            x1, y1, x2, y2, obj_conf, class_conf, class_id = det
            class_id = int(class_id)

            detection = Detection2D()
            detection.header = header

            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            width = x2 - x1
            height = y2 - y1

            detection.bbox.center.position.x = float(cx)
            detection.bbox.center.position.y = float(cy)
            detection.bbox.size_x = float(width)
            detection.bbox.size_y = float(height)

            hypothesis = ObjectHypothesisWithPose()
            # Prefer human-readable COCO name; fall back to numeric id.
            if 0 <= class_id < len(COCO_CLASSES):
                hypothesis.hypothesis.class_id = COCO_CLASSES[class_id]
            else:
                hypothesis.hypothesis.class_id = str(class_id)
            hypothesis.hypothesis.score = float(obj_conf * class_conf)
            detection.results.append(hypothesis)
            msg.detections.append(detection)

        self.detections_pub.publish(msg)

    def draw_detections(self, frame, detections):
        annotated = frame.copy()
        for det in detections:
            x1, y1, x2, y2, obj_conf, class_conf, class_id = det
            class_id = int(class_id)
            score = float(obj_conf * class_conf)
            color = (0, 255, 0)
            cv2.rectangle(annotated, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
            name = COCO_CLASSES[class_id] if 0 <= class_id < len(COCO_CLASSES) else str(class_id)
            label = f'{name}: {score:.2f}'
            label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(
                annotated,
                (int(x1), int(y1) - label_size[1] - 4),
                (int(x1) + label_size[0], int(y1)),
                color, -1,
            )
            cv2.putText(
                annotated, label, (int(x1), int(y1) - 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1,
            )

        cv2.putText(
            annotated,
            f'FPS: {self.current_fps:.1f}  Inference: {self.current_inference_ms:.1f}ms  '
            f'Detections: {len(detections)}',
            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2,
        )
        return annotated

    def log_metrics(self):
        if self.frames_since_log == 0:
            self.get_logger().info('Waiting for camera frames...')
            return

        elapsed = time.time() - self.last_log_time
        fps = self.frames_since_log / elapsed if elapsed > 0 else 0.0
        avg_inference_ms = self.total_inference_ms / self.frames_since_log
        avg_detections = self.total_detections / self.frames_since_log

        self.current_fps = fps
        self.current_inference_ms = avg_inference_ms

        self.get_logger().info(
            f'FPS: {fps:.1f}, Inference: {avg_inference_ms:.1f} ms, '
            f'Avg detections: {avg_detections:.1f}'
        )

        self.last_log_time = time.time()
        self.frames_since_log = 0
        self.total_inference_ms = 0.0
        self.total_detections = 0


def main(args=None):
    rclpy.init(args=args)
    node = YOLOXDetectorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
