# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Unit tests for QGC cleanup in run-regression.sh.

FUSE unmount target selection and the pid-reuse guard use a fake /proc and
dummy (non-FUSE) directories. The stop_our_qgc tests start their own
setsid'd dummy QGC and only ever signal that dummy's process group (a
foreign QGC binary is shown to survive). Never calls fusermount.
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


@pytest.mark.parametrize('path,want', [
    ('/tmp/.mount_QGrounAbC123/usr/bin/QGroundControl', True),
    # APPIMAGE_EXTRACT_AND_RUN=1 extracts instead of FUSE-mounting.
    ('/tmp/appimage_extracted_769fb81d76a7b70384c0399076fe9d37/usr/bin/QGroundControl', True),
    ('/opt/other/usr/bin/QGroundControl', False),
    ('/tmp/appimage_extracted_abc/usr/bin/other-app', False),
])
def test_qgc_bin_pattern_matches_mounted_and_extracted(tmp_path, path, want):
    """Stop logic must see the extracted binary (it ignores SIGTERM)."""
    empty = tmp_path / 'proc'
    empty.mkdir()
    r = _run_helpers(
        empty,
        f'if printf "%s\\n" "{path}" | grep -Eq "${{QGC_BIN_PATTERN}}"; '
        'then echo match; else echo nomatch; fi',
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ('match' if want else 'nomatch')


# --- stat parsing / pid-reuse guard (fake /proc, nothing is signalled) ----

def _stat_full(pid, comm, state='S', ppid=1, pgrp=None, sid=None, starttime=12345):
    pgrp = pid if pgrp is None else pgrp
    sid = pgrp if sid is None else sid
    # fields 3..21, then 22 = starttime, then a few more
    rest = [state, ppid, pgrp, sid] + [0] * 15 + [starttime] + [0] * 5
    return f"{pid} ({comm}) " + ' '.join(str(x) for x in rest) + '\n'


def test_stat_field_survives_spaces_and_parens_in_comm(tmp_path):
    proc = tmp_path / 'proc'
    (proc / '4242').mkdir(parents=True)
    (proc / '4242' / 'stat').write_text(
        _stat_full(4242, 'QGC) (evil 1 2 3', pgrp=4242, sid=77, starttime=987654))
    r = _run_helpers(
        proc,
        'qgc_stat_field 4242 3; qgc_pid_pgid 4242; qgc_stat_field 4242 6; '
        'qgc_pid_starttime 4242',
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ['S', '4242', '77', '987654']


def test_reused_qgc_pid_is_not_signalled(tmp_path):
    """QGC_PID now belongs to another process (different start time)."""
    proc = tmp_path / 'proc'
    exe = Path('/usr/bin/true')
    d = proc / '5150'
    d.mkdir(parents=True)
    (d / 'stat').write_text(_stat_full(5150, 'bash', starttime=999))
    (d / 'exe').symlink_to(exe)
    r = _run_helpers(
        proc,
        'if qgc_pid_is_ours 5150; then echo ours; else echo notours; fi; '
        'if qgc_group_trusted; then echo trusted; else echo untrusted; fi',
        {'QGC_PID': '5150', 'QGC_PGID': '5150', 'QGC_STARTTIME': '111'},
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ['notours', 'untrusted']


def test_matching_starttime_is_ours_and_zombie_is_not(tmp_path):
    proc = tmp_path / 'proc'
    for pid, state in ((6001, 'S'), (6002, 'Z')):
        d = proc / str(pid)
        d.mkdir(parents=True)
        (d / 'stat').write_text(_stat_full(pid, 'appimage', state=state, starttime=111))
    r = _run_helpers(
        proc,
        'for p in 6001 6002; do QGC_PID=$p QGC_PGID=$p; '
        'if qgc_pid_is_ours $p; then echo ours; else echo notours; fi; done',
        {'QGC_STARTTIME': '111'},
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ['ours', 'notours']


# --- stop_our_qgc against a real dummy process ---------------------------
# A setsid'd fake AppImage runtime (dies on TERM) starts a fake extracted
# QGroundControl that ignores TERM, like the real one. The fake binary is a
# copy of bash at /tmp/appimage_extracted_odltest/usr/bin/QGroundControl so
# /proc/<pid>/exe matches QGC_BIN_PATTERN. Only pids in the dummy's own
# process group/session can be signalled; a real QGC is never touched.

ODLTEST_DIR = Path('/tmp/appimage_extracted_odltest')

RUNTIME_SH = r'''#!/usr/bin/env bash
# Fake AppImage runtime: default TERM handling (dies), child ignores TERM.
( trap '' TERM; exec "$1" -c 'exec 3<>"$1"; echo ready >&2; read -r -u 3 _' qgc "$2" ) &
wait
'''

STOP_SNIPPET = r'''
setsid "$ODLTEST_RUNTIME" "$ODLTEST_BIN" "$ODLTEST_FIFO" 2>"$ODLTEST_READY" &
QGC_PID=$!
REG_STARTED_QGC=1
QGC_STARTTIME="$(qgc_pid_starttime "${QGC_PID}")"
for _ in $(seq 1 50); do grep -q ready "$ODLTEST_READY" && break; sleep 0.1; done
QGC_SID="$(qgc_stat_field "${QGC_PID}" 6)"
QGC_PGID="$(ps -o pgid= -p "${QGC_PID}" | tr -d ' ')"
[ "${QGC_PGID}" = "${QGC_PID}" ] || { echo "dummy is not a group leader" >&2; exit 2; }
CHILD="$(pgrep -f -g "${QGC_PGID}" '^/tmp/appimage_extracted_odltest/usr/bin/QGroundControl')"
echo "child=${CHILD}"
[ -n "${ODLTEST_FALLBACK:-}" ] && QGC_PGID=""
stop_our_qgc
if kill -0 "${CHILD}" 2>/dev/null; then echo "child-alive"; else echo "child-gone"; fi
'''


@pytest.fixture
def dummy_qgc(tmp_path):
    import shutil
    if not shutil.which('setsid') or not shutil.which('pgrep'):
        pytest.skip('setsid/pgrep not available')
    bash = os.path.realpath(shutil.which('bash'))
    if ODLTEST_DIR.exists():
        shutil.rmtree(ODLTEST_DIR)
    bin_path = ODLTEST_DIR / 'usr' / 'bin' / 'QGroundControl'
    bin_path.parent.mkdir(parents=True)
    shutil.copy2(bash, bin_path)
    runtime = tmp_path / 'fake-appimage-runtime.sh'
    runtime.write_text(RUNTIME_SH)
    runtime.chmod(0o755)
    fifo = tmp_path / 'block.fifo'
    os.mkfifo(fifo)
    env = {
        'ODLTEST_RUNTIME': str(runtime),
        'ODLTEST_BIN': str(bin_path),
        'ODLTEST_FIFO': str(fifo),
        'ODLTEST_READY': str(tmp_path / 'ready.txt'),
        'QGC_TERM_WAIT_STEPS': '2',
    }
    yield env
    # Teardown: kill only leftovers whose exe is our dummy binary.
    import signal
    for pid in os.listdir('/proc'):
        if not pid.isdigit():
            continue
        try:
            exe = os.readlink(f'/proc/{pid}/exe')
        except OSError:
            continue
        if exe.removesuffix(' (deleted)') == str(bin_path):
            try:
                os.kill(int(pid), signal.SIGKILL)
            except OSError:
                pass
    if ODLTEST_DIR.exists():
        shutil.rmtree(ODLTEST_DIR, ignore_errors=True)


def _run_stop(env_extra):
    env = os.environ.copy()
    env['QGC_FUSE_HELPERS_ONLY'] = '1'
    env.pop('QGC_PROC_ROOT', None)  # real /proc
    env.update(env_extra)
    body = f'set -euo pipefail\nsource "{SCRIPT}"\n{STOP_SNIPPET}\n'
    return subprocess.run(
        ['bash', '-c', body], cwd=str(REPO), env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=60,
    )


def test_stop_our_qgc_kills_term_ignoring_extracted_binary(dummy_qgc):
    r = _run_stop(dummy_qgc)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert 'child=' in r.stdout and 'child=\n' not in r.stdout, out
    assert 'still running after TERM; sending KILL' in out
    assert 'after KILL' in out
    assert 'child-gone' in r.stdout, out
    assert '[WARN]' not in out, out
    # The runtime was SIGKILLed out of its cleanup: our leftover dir is
    # reported and removed because nothing uses it any more.
    assert 'removed leftover extracted QGC dir /tmp/appimage_extracted_odltest' in out
    assert not ODLTEST_DIR.exists()


def test_stop_our_qgc_fallback_without_process_group(dummy_qgc):
    """R5: QGC_PGID cleared -> still finds the binary via QGC_PID's session."""
    r = _run_stop(dict(dummy_qgc, ODLTEST_FALLBACK='1'))
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert 'no own process group' in out
    assert 'after KILL' in out
    assert 'child-gone' in r.stdout, out


@pytest.mark.parametrize('fallback', ['', '1'])
def test_stop_our_qgc_leaves_foreign_qgc_alone(dummy_qgc, tmp_path, fallback):
    """A QGC binary outside our group/session (e.g. opened by hand) and
    started before ours is never signalled, and keeps its extracted dir."""
    fifo2 = tmp_path / 'foreign.fifo'
    os.mkfifo(fifo2)
    foreign = subprocess.Popen(
        [dummy_qgc['ODLTEST_BIN'], '-c', 'exec 3<>"$1"; read -r -u 3 _', 'qgc', str(fifo2)],
        start_new_session=True,
    )
    try:
        r = _run_stop(dict(dummy_qgc, ODLTEST_FALLBACK=fallback))
        out = r.stdout + r.stderr
        assert r.returncode == 0, out
        assert 'after KILL' in out
        assert 'child-gone' in r.stdout, out
        assert foreign.poll() is None, 'foreign QGC was killed: ' + out
        assert f'still used by pid {foreign.pid}' in out, out
        assert ODLTEST_DIR.exists()
    finally:
        foreign.kill()
        foreign.wait(timeout=10)
