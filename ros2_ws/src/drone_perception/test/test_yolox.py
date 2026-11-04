"""Unit tests for YOLOX detection functions (no rclpy/ort required at import of helpers)."""
import unittest
import numpy as np

# Import helpers without constructing the ROS node.
from drone_perception.yolox_detector_node import (
    letterbox,
    preprocess_yolox,
    decode_yolox_outputs,
    demo_postprocess,
    nms,
    unscale_boxes,
    COCO_CLASSES,
)


class TestYOLOXFunctions(unittest.TestCase):
    """Test YOLOX preprocessing and postprocessing functions."""

    def test_letterbox_top_left(self):
        """Official YOLOX preproc places content at top-left with pad 114."""
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        img[:] = 200
        padded, scale, (pad_h, pad_w) = letterbox(img, (416, 416))

        self.assertEqual(padded.shape, (416, 416, 3))
        self.assertAlmostEqual(scale, min(416 / 640, 416 / 480), places=4)
        self.assertEqual(pad_h, 0)
        self.assertEqual(pad_w, 0)
        # Top-left pixel comes from the image; bottom-right pad stays 114.
        self.assertTrue(np.all(padded[0, 0] == 200))
        self.assertTrue(np.all(padded[-1, -1] == 114))

    def test_preprocess_yolox_shape(self):
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        tensor, scale, padding = preprocess_yolox(img, (416, 416))
        self.assertEqual(tensor.shape, (1, 3, 416, 416))
        self.assertEqual(tensor.dtype, np.float32)
        self.assertEqual(padding, (0, 0))

    def test_demo_postprocess_expands_to_pixel_space(self):
        """Raw relative outputs become absolute after demo_postprocess."""
        # One batch, 3549 anchors (52^2+26^2+13^2), 85 channels — zeros.
        raw = np.zeros((1, 3549, 85), dtype=np.float32)
        # First stride-8 cell at grid (0,0): cx=cy=0, log(w)=log(h)=0 → w=h=stride
        raw[0, 0, :4] = [0.0, 0.0, 0.0, 0.0]
        out = demo_postprocess(raw, img_size=(416, 416))
        # (0+0)*8 = 0 for xy; exp(0)*8 = 8 for wh
        self.assertAlmostEqual(float(out[0, 0, 0]), 0.0, places=3)
        self.assertAlmostEqual(float(out[0, 0, 2]), 8.0, places=3)

    def test_decode_yolox_outputs_shape(self):
        raw = np.zeros((1, 3549, 85), dtype=np.float32)
        # Put a confident person at the first anchor after postprocess.
        raw[0, 0, 4] = 0.9
        raw[0, 0, 5] = 0.8
        detections = decode_yolox_outputs(raw, input_size=(416, 416))
        self.assertEqual(detections.shape[1], 7)
        self.assertEqual(detections.shape[0], 3549)

    def test_nms_filters_overlapping_boxes(self):
        detections = np.array([
            [100, 100, 200, 200, 0.9, 0.85, 0],
            [105, 105, 205, 205, 0.8, 0.80, 0],
            [300, 300, 400, 400, 0.9, 0.90, 1],
        ])
        filtered = nms(detections, score_threshold=0.5, nms_threshold=0.5)
        self.assertEqual(len(filtered), 2)
        scores = filtered[:, 4] * filtered[:, 5]
        self.assertTrue(np.all(scores >= 0.5))

    def test_nms_empty_input(self):
        detections = np.array([]).reshape(0, 7)
        filtered = nms(detections)
        self.assertEqual(len(filtered), 0)

    def test_nms_below_threshold(self):
        detections = np.array([
            [100, 100, 200, 200, 0.3, 0.4, 0],
        ])
        filtered = nms(detections, score_threshold=0.5)
        self.assertEqual(len(filtered), 0)

    def test_unscale_boxes_top_left(self):
        scale = 0.5
        padding = (0, 0)
        original_shape = (480, 640)
        boxes = np.array([
            [100, 100, 200, 200],
            [150, 150, 250, 250],
        ], dtype=np.float32)
        unscaled = unscale_boxes(boxes.copy(), scale, padding, original_shape)
        np.testing.assert_allclose(unscaled[0], [200, 200, 400, 400])
        self.assertTrue(np.all(unscaled[:, [0, 2]] <= original_shape[1]))
        self.assertTrue(np.all(unscaled[:, [1, 3]] <= original_shape[0]))

    def test_coco_classes_count(self):
        self.assertEqual(len(COCO_CLASSES), 80)
        self.assertIn('person', COCO_CLASSES)
        self.assertIn('car', COCO_CLASSES)
        self.assertIn('dog', COCO_CLASSES)


if __name__ == '__main__':
    unittest.main()
