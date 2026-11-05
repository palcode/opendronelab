#!/usr/bin/env python3
"""Benchmark YOLOX-nano ONNX inference: CPU vs CUDA.

Runs N timed InferenceSession.run() calls on a synthetic 416x416 float32
input (or a real image if --image is given). Prints mean/p50/p95/min/max ms
and the active ORT providers. Exit non-zero if --require-cuda is set and
CUDAExecutionProvider is not active.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

import numpy as np


def build_session(model_path: str, use_cuda: bool, num_threads: int):
    import onnxruntime as ort

    try:
        import onnxruntime.preload_dlls as preload
        preload.preload_dlls()
    except Exception as err:  # pragma: no cover
        print(f'WARN: preload_dlls skipped: {err}', file=sys.stderr)

    available = ort.get_available_providers()
    if use_cuda:
        providers = []
        if 'CUDAExecutionProvider' in available:
            providers.append('CUDAExecutionProvider')
        providers.append('CPUExecutionProvider')
    else:
        providers = ['CPUExecutionProvider']

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = num_threads
    opts.inter_op_num_threads = num_threads
    session = ort.InferenceSession(model_path, opts, providers=providers)
    active = session.get_providers()
    return session, available, providers, active


def make_input(session, image_path: str | None):
    inp = session.get_inputs()[0]
    name = inp.name
    shape = inp.shape  # [N, C, H, W]
    h = int(shape[2]) if isinstance(shape[2], int) else 416
    w = int(shape[3]) if isinstance(shape[3], int) else 416

    if image_path:
        import cv2
        # Import helpers from the package if available; else letterbox inline.
        img = cv2.imread(image_path)
        if img is None:
            raise SystemExit(f'failed to read image: {image_path}')
        try:
            from drone_perception.yolox_detector_node import preprocess_yolox
            tensor, _, _ = preprocess_yolox(img, (h, w))
        except Exception:
            # Fallback: resize + pad 114, CHW float32
            scale = min(w / img.shape[1], h / img.shape[0])
            nw, nh = int(img.shape[1] * scale), int(img.shape[0] * scale)
            resized = cv2.resize(img, (nw, nh))
            padded = np.full((h, w, 3), 114, dtype=np.uint8)
            padded[:nh, :nw] = resized
            tensor = padded.astype(np.float32).transpose(2, 0, 1)[None, ...]
    else:
        # Synthetic BGR-ish float input in YOLOX range (0..255).
        rng = np.random.default_rng(0)
        tensor = rng.integers(0, 256, size=(1, 3, h, w), dtype=np.uint8).astype(np.float32)

    return name, tensor


def time_runs(session, input_name: str, tensor: np.ndarray, warmup: int, n: int):
    feeds = {input_name: tensor}
    for _ in range(warmup):
        session.run(None, feeds)
    times_ms = []
    for _ in range(n):
        t0 = time.perf_counter()
        session.run(None, feeds)
        times_ms.append((time.perf_counter() - t0) * 1000.0)
    return times_ms


def summarize(label: str, times_ms: list[float], available, providers, active):
    s = sorted(times_ms)
    p50 = s[len(s) // 2]
    p95 = s[max(0, int(len(s) * 0.95) - 1)]
    print(f'=== {label} ===')
    print(f'available_providers: {available}')
    print(f'requested_providers: {providers}')
    print(f'active_providers:    {active}')
    mean = statistics.mean(times_ms)
    fps = 1000.0 / mean if mean > 0 else 0.0
    print(
        f'N={len(times_ms)}  mean={mean:.3f} ms  '
        f'p50={p50:.3f} ms  p95={p95:.3f} ms  '
        f'min={min(times_ms):.3f} ms  max={max(times_ms):.3f} ms  '
        f'fps={fps:.1f}'
    )
    return {
        'label': label,
        'mean': mean,
        'p50': p50,
        'p95': p95,
        'min': min(times_ms),
        'max': max(times_ms),
        'fps': fps,
        'active': list(active),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--model', default='/data/models/yolox_nano.onnx')
    ap.add_argument('--image', default=None, help='Optional BGR image path')
    ap.add_argument('--n', type=int, default=200)
    ap.add_argument('--warmup', type=int, default=20)
    ap.add_argument('--threads', type=int, default=4)
    ap.add_argument('--cpu-only', action='store_true', help='Bench CPU only')
    ap.add_argument('--cuda-only', action='store_true', help='Bench CUDA only')
    ap.add_argument(
        '--require-cuda',
        action='store_true',
        help='Exit 1 if CUDA EP is not active when CUDA is requested',
    )
    args = ap.parse_args()

    if not Path(args.model).is_file():
        raise SystemExit(f'model not found: {args.model}')

    results = []
    do_cpu = not args.cuda_only
    do_cuda = not args.cpu_only

    if do_cpu:
        session, available, providers, active = build_session(
            args.model, use_cuda=False, num_threads=args.threads,
        )
        name, tensor = make_input(session, args.image)
        times = time_runs(session, name, tensor, args.warmup, args.n)
        results.append(summarize('CPU', times, available, providers, active))
        del session

    if do_cuda:
        session, available, providers, active = build_session(
            args.model, use_cuda=True, num_threads=args.threads,
        )
        name, tensor = make_input(session, args.image)
        times = time_runs(session, name, tensor, args.warmup, args.n)
        results.append(summarize('CUDA', times, available, providers, active))
        if args.require_cuda and 'CUDAExecutionProvider' not in active:
            print('ERROR: CUDAExecutionProvider not active', file=sys.stderr)
            sys.exit(1)
        del session

    if len(results) == 2:
        cpu, cuda = results
        if cpu['mean'] > 0:
            speedup = cpu['mean'] / cuda['mean']
            print(f'=== speedup (CPU mean / CUDA mean) = {speedup:.2f}x ===')


if __name__ == '__main__':
    main()
