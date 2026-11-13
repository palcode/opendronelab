# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Unit tests for QGC FUSE unmount target selection in run-regression.sh.

Uses a fake /proc and dummy (non-FUSE) directories. Never calls fusermount
and never signals real processes.
"""
import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT = REPO / 'scripts' / 'run-regression.sh'


def _stat_line(pid: int, pgrp: int) -> str:
    # pid (comm) state ppid pgrp session ...
    return f"{pid} (QGroundControl) S 1 {pgrp} {pgrp} 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0\n"


def _write_fake_pid(proc: Path, pid: int, pgrp: int, exe: Path, cwd: Path | None = None,
                    mountinfo: str | None = None):
    d = proc / str(pid)
    d.mkdir(parents=True)
    (d / 'stat').write_text(_stat_line(pid, pgrp))
    exe.parent.mkdir(parents=True, exist_ok=True)
    if not exe.exists():
        exe.write_text('dummy-qgc\n')
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    (d / 'exe').symlink_to(exe)
    (d / 'cwd').symlink_to(cwd or exe.parent)
    if mountinfo is not None:
        (d / 'mountinfo').write_text(mountinfo)


def _run_helpers(proc: Path, script: str, env_extra=None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env['QGC_FUSE_HELPERS_ONLY'] = '1'
    env['QGC_PROC_ROOT'] = str(proc)
    if env_extra:
        env.update(env_extra)
    # Source helpers, then run the caller-provided snippet.
    body = f'set -euo pipefail\nsource "{SCRIPT}"\n{script}\n'
    return subprocess.run(
        ['bash', '-c', body],
        cwd=str(REPO), env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )


@pytest.fixture
def mounts(tmp_path):
    ours = Path('/tmp/.mount_QGrounODL85ours')
    hand = Path('/tmp/.mount_QGrounODL85hand')
    # Isolate under tmp_path if possible? exe must be /tmp/.mount_QGroun*.
    # Clean leftovers from a previous failed run, then create.
    import shutil
    for p in (ours, hand):
        if p.exists():
            shutil.rmtree(p)
    ours_exe = ours / 'usr' / 'bin' / 'QGroundControl'
    hand_exe = hand / 'usr' / 'bin' / 'QGroundControl'
    proc = tmp_path / 'proc'
    proc.mkdir()
    # mountinfo of our pid lists BOTH mounts — the original bug.
    both = (
        "1 0 0:1 / / rw - fuse /tmp/.mount_QGrounODL85ours fuse\n"
        "2 0 0:2 / /tmp/.mount_QGrounODL85hand rw - fuse /tmp/.mount_QGrounODL85hand fuse\n"
        "36 24 0:32 / /tmp/.mount_QGrounODL85hand rw,relatime - fuse /tmp/.mount_QGrounODL85hand fuse\n"
    )
    # Use a realistic mountinfo $5 = mount point
    both = (
        "36 24 0:32 / /tmp/.mount_QGrounODL85ours rw,relatime - fuse /tmp/.mount_QGrounODL85ours fuse\n"
        "37 24 0:33 / /tmp/.mount_QGrounODL85hand rw,relatime - fuse /tmp/.mount_QGrounODL85hand fuse\n"
    )
    _write_fake_pid(proc, 111, 111, ours_exe, mountinfo=both)
    _write_fake_pid(proc, 222, 222, hand_exe, mountinfo=both)
    yield {'proc': proc, 'ours': ours, 'hand': hand, 'ours_exe': ours_exe, 'hand_exe': hand_exe}
    import shutil
    for p in (ours, hand):
        if p.exists():
            shutil.rmtree(p)


def test_mounts_from_pids_uses_exe_not_mountinfo(mounts):
    r = _run_helpers(
        mounts['proc'],
        'qgc_mounts_from_pids',
        {'QGC_PID': '111', 'QGC_PGID': '111'},
    )
    assert r.returncode == 0, r.stderr
    lines = [ln for ln in r.stdout.splitlines() if ln]
    assert lines == ['/tmp/.mount_QGrounODL85ours']


def test_preexisting_mount_is_not_unmounted(mounts):
    r = _run_helpers(
        mounts['proc'],
        'qgc_ours_unmount_targets',
        {
            'QGC_PID': '111',
            'QGC_PGID': '111',
            'QGC_MOUNTS': '/tmp/.mount_QGrounODL85ours',
            'QGC_PREEXISTING_MOUNTS': '/tmp/.mount_QGrounODL85ours',
        },
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ''


def test_hand_opened_qgc_mount_not_selected_even_if_in_snapshot(mounts):
    r = _run_helpers(
        mounts['proc'],
        'qgc_ours_unmount_targets',
        {
            'QGC_PID': '111',
            'QGC_PGID': '111',
            # A buggy start snapshot that also recorded Pallab's mount.
            'QGC_MOUNTS': '/tmp/.mount_QGrounODL85ours\n/tmp/.mount_QGrounODL85hand',
            'QGC_PREEXISTING_MOUNTS': '/tmp/.mount_QGrounODL85hand',
        },
    )
    assert r.returncode == 0, r.stderr
    lines = [ln for ln in r.stdout.splitlines() if ln]
    assert lines == ['/tmp/.mount_QGrounODL85ours']


def test_skips_target_used_outside_our_pgid(mounts, tmp_path):
    # A third process outside pgid 111 has exe under our mount.
    other_exe = mounts['ours'] / 'usr' / 'bin' / 'other'
    _write_fake_pid(mounts['proc'], 333, 999, other_exe)
    r = _run_helpers(
        mounts['proc'],
        'qgc_ours_unmount_targets',
        {
            'QGC_PID': '111',
            'QGC_PGID': '111',
            'QGC_MOUNTS': '/tmp/.mount_QGrounODL85ours',
            'QGC_PREEXISTING_MOUNTS': '',
        },
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ''
    assert 'still used outside our process group' in r.stderr


def test_ours_unmount_targets_from_start_snapshot_after_pid_gone(mounts):
    # No live pids under the fake proc: rely on the start snapshot.
    empty = mounts['proc'] / 'empty'
    empty.mkdir()
    r = _run_helpers(
        empty,
        'qgc_ours_unmount_targets',
        {
            'QGC_PID': '',
            'QGC_PGID': '',
            'QGC_MOUNTS': '/tmp/.mount_QGrounODL85ours',
            'QGC_PREEXISTING_MOUNTS': '/tmp/.mount_QGrounODL85hand',
        },
    )
    assert r.returncode == 0, r.stderr
    lines = [ln for ln in r.stdout.splitlines() if ln]
    assert lines == ['/tmp/.mount_QGrounODL85ours']
