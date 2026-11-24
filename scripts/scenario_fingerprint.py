#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Scenario fingerprint: sha256 of the vehicle MODEL (PX4 SITL airframe),
the world SDF + OpenVINS overlay directory, plus any maskN files the overlay
config references outside that directory.

Used so a low_texture (or other) result can be compared only with runs that
used the same world and overlay. The git SHA is recorded too, but is not the
primary hash: unrelated commits would change it.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path


def _repo_relative(repo: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _resolve_world(repo: Path, world: str | None) -> tuple[Path | None, str | None]:
    if not world:
        return None, None
    raw = Path(world)
    if raw.suffix == '.sdf' and raw.is_file():
        return raw, _repo_relative(repo, raw)
    name = raw.stem
    # Container path /workspace/worlds/<name>.sdf or a bare world name.
    for cand in (
        raw if raw.is_absolute() else None,
        repo / 'worlds' / f'{name}.sdf',
        repo / raw if not raw.is_absolute() else None,
    ):
        if cand is not None and cand.is_file():
            return cand, _repo_relative(repo, cand)
    # Record the expected relative path even if the file is missing.
    return None, f'worlds/{name}.sdf'


def _resolve_overlay(repo: Path, overlay_config: str | Path | None) -> tuple[Path | None, str | None]:
    if not overlay_config:
        return None, None
    raw = Path(overlay_config)
    # Map the container workspace prefix onto the repo we were given.
    parts = raw.as_posix()
    if parts.startswith('/workspace/'):
        raw = repo / parts[len('/workspace/'):]
    elif not raw.is_absolute():
        raw = repo / raw
    if raw.is_dir():
        directory = raw
    elif raw.is_file():
        directory = raw.parent
    else:
        # Given but missing (e.g. a typo'd overlay name). Never fall back to
        # the parent directory: that silently hashes the wrong config
        # (e.g. all of config/openvins). The caller hashes a 'missing' marker.
        return None, _repo_relative(repo, raw)
    return directory, _repo_relative(repo, directory)


def _iter_overlay_files(overlay_dir: Path):
    files = []
    for f in overlay_dir.rglob('*'):
        if not f.is_file():
            continue
        rel_parts = f.relative_to(overlay_dir).parts
        if any(p.startswith('.') or p == '__pycache__' for p in rel_parts):
            continue
        # TODO: exclude README*.md files from the hash when the next
        # intentional hash change happens (deferred to avoid changing all
        # fingerprints twice in quick succession).
        files.append(f)
    files.sort(key=lambda p: p.relative_to(overlay_dir).as_posix())
    return files


def _git_sha(repo: Path) -> str | None:
    try:
        proc = subprocess.run(
            ['git', '-C', str(repo), 'rev-parse', 'HEAD'],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    sha = (proc.stdout or '').strip()
    return sha or None


def _mask_references(overlay_dir: Path):
    """maskN paths from estimator_config.yaml, resolved like OpenVINS.

    OpenVINS does get_config_folder() + mask_path, i.e. the config
    directory plus the configured relative (or absolute) path.
    """
    cfg = overlay_dir / 'estimator_config.yaml'
    if not cfg.is_file():
        return []
    refs = []
    for raw in cfg.read_text().splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        m = re.match(r'^mask(\d+):\s*["\']?([^"\']+?)["\']?\s*$', line)
        if not m:
            continue
        mask_name, mask_path = m.group(1), m.group(2).strip()
        if not mask_path:
            continue
        raw_path = Path(mask_path)
        if raw_path.is_absolute():
            resolved = raw_path
        else:
            # Same string-concat as OpenVINS, then resolve for reading.
            resolved = Path(str(cfg.parent) + '/' + mask_path)
        refs.append((f'mask{mask_name}', resolved, mask_path))
    return refs


def compute_scenario_fingerprint(
    repo: str | Path,
    world: str | None,
    overlay_config: str | Path | None = None,
    model: str | None = None,
) -> dict:
    """Return {scheme, sha256, git_sha, model, world, openvins_overlay}.

    scheme is the fingerprint version: 2 (current, includes MODEL),
    1 (pre-ODL-92, world+overlay only). Missing scheme in old results
    should be treated as 1.

    sha256 covers the vehicle MODEL name (e.g. gz_x500_mono_cam; always
    hashed, as an empty string when unknown, since ODL-92), the world SDF
    bytes, the overlay directory files, and any
    maskN file referenced by estimator_config.yaml that lives outside the
    overlay directory (OpenVINS resolves mask paths relative to the config
    file). It changes when the scenario itself changes and not when unrelated
    files change. git_sha is informational.
    """
    repo = Path(repo)
    world_path, world_rel = _resolve_world(repo, world)
    overlay_dir, overlay_rel = _resolve_overlay(repo, overlay_config)

    model_name = (model or '').strip()

    hasher = hashlib.sha256()
    # MODEL first (ODL-92): the same world + overlay flown by a different
    # airframe is a different scenario. Always present so the input layout
    # is fixed.
    hasher.update(b'model:')
    hasher.update(model_name.encode())
    hasher.update(b'\0')
    if world_path is not None:
        hasher.update(b'world:')
        hasher.update((world_rel or world_path.as_posix()).encode())
        hasher.update(b'\0')
        hasher.update(world_path.read_bytes())
        hasher.update(b'\0')
    elif world:
        # A world was given but does not resolve (typo or not vendored):
        # hash a marker so it differs from "no world". Valid scenarios
        # never take this branch, so their fingerprints are unchanged.
        hasher.update(b'world-missing:')
        hasher.update((world_rel or str(world)).encode())
        hasher.update(b'\0')
    if overlay_dir is None and overlay_config:
        # Same for a given-but-missing overlay (see _resolve_overlay).
        hasher.update(b'overlay-missing:')
        hasher.update((overlay_rel or str(overlay_config)).encode())
        hasher.update(b'\0')
    if overlay_dir is not None:
        hashed_resolved = set()
        for f in _iter_overlay_files(overlay_dir):
            rel = f.relative_to(overlay_dir).as_posix()
            hasher.update(b'overlay:')
            hasher.update(rel.encode())
            hasher.update(b'\0')
            hasher.update(f.read_bytes())
            hasher.update(b'\0')
            try:
                hashed_resolved.add(f.resolve())
            except OSError:
                pass
        for _name, resolved, mask_path in _mask_references(overlay_dir):
            try:
                resolved_real = resolved.resolve()
            except OSError:
                continue
            if not resolved_real.is_file() or resolved_real in hashed_resolved:
                continue
            # Configured path (usually ../mask_....png) plus the file bytes,
            # so a shared-mask change still changes the fingerprint.
            hasher.update(b'mask:')
            hasher.update(mask_path.encode())
            hasher.update(b'\0')
            hasher.update(resolved_real.read_bytes())
            hasher.update(b'\0')
            hashed_resolved.add(resolved_real)

    result = {
        'scheme': 2,
        'sha256': hasher.hexdigest(),
        'git_sha': _git_sha(repo),
        'model': model_name or None,
        'world': world_rel,
        'openvins_overlay': overlay_rel,
    }
    missing = []
    if world and world_path is None:
        missing.append('world')
    if overlay_config and overlay_dir is None:
        missing.append('openvins_overlay')
    if missing:
        # Only present when something was not found, so valid summaries
        # keep the same keys.
        result['missing'] = missing
    return result


if __name__ == '__main__':
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', default='.')
    ap.add_argument('--world', required=True)
    ap.add_argument('--overlay', required=False)
    ap.add_argument('--model', required=False,
                    help='PX4 SITL airframe (MODEL), e.g. gz_x500_mono_cam')
    args = ap.parse_args()
    print(json.dumps(compute_scenario_fingerprint(
        args.repo, args.world, args.overlay, model=args.model), indent=2))
