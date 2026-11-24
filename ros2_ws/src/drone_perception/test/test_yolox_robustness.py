# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""YOLOX helper robustness (ODL-132) and decode/IoU maths (ODL-143)."""
import warnings

import numpy as np
import pytest

from drone_perception.yolox_detector_node import (
    NMS_MAX_CANDIDATES,
    decode_yolox_outputs,
    letterbox,
    nms,
    preprocess_yolox,
)


@pytest.mark.parametrize('shape', [(1, 5000, 3), (5000, 1, 3), (1, 1, 3)])
def test_extreme_aspect_ratio_letterbox(shape):
    padded, scale, pad = letterbox(np.zeros(shape, dtype=np.uint8), (416, 416))
    assert padded.shape == (416, 416, 3)
    tensor, _, _ = preprocess_yolox(np.zeros(shape, dtype=np.uint8))
    assert tensor.shape == (1, 3, 416, 416)


def _raw(n=3549, k=85):
    return np.zeros((1, n, k), dtype=np.float32)


def test_decode_huge_logits_stay_finite():
    raw = _raw()
    raw[0, :, 2:4] = 1000.0
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        det = decode_yolox_outputs(raw)
    assert np.all(np.isfinite(det[:, :4]))


def test_decode_corner_maths():
    raw = _raw()
    # Anchor 0: grid (0, 0), stride 8. cx = (1 + 0) * 8, cy = (2 + 0) * 8,
    # w = h = exp(0) * 8 -> corners (4, 12, 12, 20).
    raw[0, 0, :4] = [1.0, 2.0, 0.0, 0.0]
    raw[0, 0, 4] = 0.9
    raw[0, 0, 5 + 3] = 0.8
    d = decode_yolox_outputs(raw)[0]
    np.testing.assert_allclose(d[:4], [4.0, 12.0, 12.0, 20.0])
    assert d[4] == pytest.approx(0.9) and d[5] == pytest.approx(0.8) and d[6] == 3
    # Anchor 1: grid (1, 0): cx = (0 + 1) * 8 = 8, w = exp(ln 2) * 8 = 16.
    raw[0, 1, :4] = [0.0, 0.0, np.log(2.0), np.log(4.0)]
    d = decode_yolox_outputs(raw)[1]
    np.testing.assert_allclose(d[:4], [0.0, -16.0, 16.0, 16.0], atol=1e-4)


def _box(x1, y1, x2, y2, s=0.9):
    return [x1, y1, x2, y2, s, 1.0, 0]


def test_nms_iou_maths():
    # IoU = 50 / 150 = 1/3 exactly.
    d = np.array([_box(0, 0, 10, 10, 0.9), _box(5, 0, 15, 10, 0.8)])
    assert len(nms(d, score_threshold=0.1, nms_threshold=0.30)) == 1
    assert len(nms(d, score_threshold=0.1, nms_threshold=0.34)) == 2
    kept = nms(d, score_threshold=0.1, nms_threshold=0.30)
    assert kept[0][4] == pytest.approx(0.9)


@pytest.mark.parametrize('det', [np.zeros((0, 7)), np.array([_box(0, 0, 1, 1, 0.1)])])
def test_nms_empty_shape(det):
    assert nms(det, score_threshold=0.5).shape == (0, 7)


def test_nms_caps_candidates():
    n = NMS_MAX_CANDIDATES + 200
    d = np.array([_box(20 * i, 0, 20 * i + 10, 10, 0.5 + 0.4 * i / n) for i in range(n)])
    kept = nms(d, score_threshold=0.1, nms_threshold=0.45)
    assert len(kept) == NMS_MAX_CANDIDATES
    assert kept[:, 4].min() >= np.sort(d[:, 4])[-NMS_MAX_CANDIDATES] - 1e-12
