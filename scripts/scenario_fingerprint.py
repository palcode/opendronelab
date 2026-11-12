#!/usr/bin/env python3
"""Scenario fingerprint: sha256 of the world SDF + OpenVINS overlay directory.

Used so a low_texture (or other) result can be compared only with runs that
used the same world and overlay. The git SHA is recorded too, but is not the
primary hash: unrelated commits would change it.
"""
from __future__ import annotations

import hashlib
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
    directory = raw if raw.is_dir() else raw.parent
    if directory.is_dir():
        return directory, _repo_relative(repo, directory)
    return None, _repo_relative(repo, directory)


def _iter_overlay_files(overlay_dir: Path):
    files = []
    for f in overlay_dir.rglob('*'):
        if not f.is_file():
            continue
        rel_parts = f.relative_to(overlay_dir).parts
        if any(p.startswith('.') or p == '__pycache__' for p in rel_parts):
            continue
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


def compute_scenario_fingerprint(
    repo: str | Path,
    world: str | None,
    overlay_config: str | Path | None = None,
) -> dict:
    """Return {sha256, git_sha, world, openvins_overlay}.

    sha256 covers only the world SDF bytes and the overlay directory files, so
    it changes when the scenario itself changes and not when unrelated files
    change. git_sha is informational.
    """
    repo = Path(repo)
    world_path, world_rel = _resolve_world(repo, world)
    overlay_dir, overlay_rel = _resolve_overlay(repo, overlay_config)

    hasher = hashlib.sha256()
    if world_path is not None:
        hasher.update(b'world:')
        hasher.update((world_rel or world_path.as_posix()).encode())
        hasher.update(b'\0')
        hasher.update(world_path.read_bytes())
        hasher.update(b'\0')
    if overlay_dir is not None:
        for f in _iter_overlay_files(overlay_dir):
            rel = f.relative_to(overlay_dir).as_posix()
            hasher.update(b'overlay:')
            hasher.update(rel.encode())
            hasher.update(b'\0')
            hasher.update(f.read_bytes())
            hasher.update(b'\0')

    return {
        'sha256': hasher.hexdigest(),
        'git_sha': _git_sha(repo),
        'world': world_rel,
        'openvins_overlay': overlay_rel,
    }


if __name__ == '__main__':
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', default='.')
    ap.add_argument('--world', required=True)
    ap.add_argument('--overlay', required=False)
    args = ap.parse_args()
    print(json.dumps(compute_scenario_fingerprint(args.repo, args.world, args.overlay), indent=2))
