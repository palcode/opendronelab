# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Alignment correctness (ODL-118 origin offset timing, ODL-119 GT cropping).

GT here is piecewise linear, so linear interpolation of GT is exact and a
perfect estimate must score 0 (to float precision) whatever the GT rate,
the estimate rate, the speed, or when the estimate starts.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

from drone_localization import localization_metrics as lm
from drone_localization.localization_metrics import (
    align_trajectories,
    compute_metrics,
)

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / 'scripts'))
from scoring_version import summary_scoring_version  # noqa: E402

V = np.array([6.0, 1.5, -0.2])  # m/s, NED


def truth(t_s):
    """Constant-velocity path from (0, 0, -5); exact under linear interp."""
    t_s = np.asarray(t_s, dtype=np.float64)
    return np.array([0.0, 0.0, -5.0]) + np.outer(t_s, V)


def series(t0, t1, hz, phase=0.0):
    t = np.arange(t0 + phase, t1, 1.0 / hz)
    return t * 1e9, truth(t)


def score(gt_t, gt_p, est_t, est_p, origin_align=True):
    g, e, ts = align_trajectories(gt_t, gt_p, est_t, est_p,
                                  origin_align=origin_align)
    return compute_metrics(g, e), g, e, ts


def test_scoring_version_is_2():
    assert lm.SCORING_VERSION == 2


@pytest.mark.parametrize('gt_hz', [10.0, 30.0, 60.0])
@pytest.mark.parametrize('est_phase', [0.0, 0.003, 0.0371])
def test_perfect_estimate_scores_zero(gt_hz, est_phase):
    # ODL-118: v1 scored 0.058 m at 6 m/s with 60 Hz GT and 0.18 m at 10 Hz.
    gt_t, gt_p = series(0.0, 20.0, gt_hz)
    est_t, est_p = series(0.0, 20.0, 150.0, phase=est_phase)
    m, _, _, _ = score(gt_t, gt_p, est_t, est_p)
    assert m['horizontal_rmse'] < 1e-9
    assert m['horizontal_max'] < 1e-9
    assert m['vertical_max'] < 1e-9


def test_perfect_estimate_starting_mid_air_scores_zero():
    # VIO that first publishes at t=7.31 s, between 10 Hz GT samples.
    gt_t, gt_p = series(0.0, 20.0, 10.0)
    est_t, est_p = series(7.31, 20.0, 150.0)
    est_p = est_p - truth([7.31])[0]  # VIO frame starts at its own origin
    m, g, e, _ = score(gt_t, gt_p, est_t, est_p)
    assert m['horizontal_max'] < 1e-9
    assert m['vertical_max'] < 1e-9
    np.testing.assert_allclose(g[0], e[0], atol=1e-12)


def test_known_constant_offset():
    gt_t, gt_p = series(0.0, 10.0, 30.0)
    est_t, est_p = series(0.0, 10.0, 100.0, phase=0.004)
    off = np.array([1.0, -2.0, 0.5])
    est_p = est_p + off
    m, _, _, _ = score(gt_t, gt_p, est_t, est_p)
    assert m['horizontal_max'] < 1e-9  # origin-align removes it exactly
    m, _, _, _ = score(gt_t, gt_p, est_t, est_p, origin_align=False)
    assert m['horizontal_rmse'] == pytest.approx(np.sqrt(5.0), abs=1e-9)
    assert m['vertical_rmse'] == pytest.approx(0.5, abs=1e-9)


def test_known_time_shift():
    # Estimate lags truth by 0.1 s while moving at |v_xy| = 6.18 m/s, then
    # both stop at t=5 s. Origin-aligned: 0 while both move, then the lag
    # distance once both have stopped.
    def path(t):
        t = np.asarray(t, dtype=np.float64)
        return truth(np.minimum(np.maximum(t, 0.0), 5.0))
    gt_t = np.arange(0.0, 10.0, 1 / 30.0)
    est_t = np.arange(0.5, 10.0, 1 / 100.0)
    gt_p, est_p = path(gt_t), path(est_t - 0.1)
    g, e, ts = align_trajectories(gt_t * 1e9, gt_p, est_t * 1e9, est_p)
    err = np.linalg.norm((e - g)[:, :2], axis=1)
    t = ts / 1e9
    lag_xy = 0.1 * np.linalg.norm(V[:2])
    assert np.max(err[t < 4.99]) < 1e-9
    np.testing.assert_allclose(err[t > 5.11], lag_xy, atol=1e-9)
    g, e, ts = align_trajectories(gt_t * 1e9, gt_p, est_t * 1e9, est_p,
                                  origin_align=False)
    err = np.linalg.norm((e - g)[:, :2], axis=1)
    np.testing.assert_allclose(err[(ts / 1e9) < 4.99], lag_xy, atol=1e-9)


def test_edges_use_full_gt_not_clamped():
    # ODL-119: estimate starts 0.07 s after a GT sample and ends 0.06 s
    # before one. v1 cropped GT to the overlap first, so those edge samples
    # got the clamped first/last cropped GT sample (error up to v * 0.1 s).
    gt_t, gt_p = series(0.0, 10.05, 10.0)
    est_t, est_p = series(0.07, 9.94, 200.0)
    m, _, _, ts = score(gt_t, gt_p, est_t, est_p, origin_align=False)
    assert m['horizontal_max'] < 1e-9
    assert len(ts) == len(est_t)


def test_estimate_outside_gt_range_is_dropped():
    gt_t, gt_p = series(2.0, 8.0, 30.0)
    est_t, est_p = series(0.0, 10.0, 100.0)
    m, _, _, ts = score(gt_t, gt_p, est_t, est_p)
    assert ts[0] >= gt_t[0] and ts[-1] <= gt_t[-1]
    assert m['num_samples'] == int(np.sum((est_t >= gt_t[0]) & (est_t <= gt_t[-1])))
    assert m['horizontal_max'] < 1e-9


def test_no_overlap_raises():
    gt_t, gt_p = series(0.0, 5.0, 30.0)
    est_t, est_p = series(6.0, 9.0, 100.0)
    with pytest.raises(ValueError):
        align_trajectories(gt_t, gt_p, est_t, est_p)
    with pytest.raises(ValueError):
        align_trajectories(gt_t[:0], gt_p[:0], est_t, est_p)


def test_summary_scoring_version():
    assert summary_scoring_version({}, {}) is None
    assert summary_scoring_version({'horizontal_rmse': 0.2}, {}) == 1
    assert summary_scoring_version({'scoring_version': 2}, {}) == 2
    assert summary_scoring_version({'scoring_version': 2},
                                   {'scoring_version': 2}) == 2
    assert summary_scoring_version({'scoring_version': 2},
                                   {'horizontal_rmse': 1.0}) == 1
