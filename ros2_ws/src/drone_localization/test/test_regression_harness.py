# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Tests for run-regression.sh harness fixes (no Docker, no SITL).

regression-lib.sh is sourced with a stub `docker` on PATH (ODL-121 wait_dds,
ODL-122 run ids, ODL-123 JSON writers). The end-to-end tests run the real
run-regression.sh from a copy of scripts/ and config/ in a directory whose
name has an apostrophe, with stub launch/stop/DDS/flight scripts and a stub
docker that fakes the judge: duplicate scenarios (ODL-122), errexit inside
run_flight (ODL-125), per-scenario bag duration in the report (ODL-138).
"""
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
LIB = REPO / 'scripts' / 'regression-lib.sh'


def _exe(path: Path, body: str):
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _lib(script: str, env_extra=None, path_prefix=None):
    env = os.environ.copy()
    if path_prefix:
        env['PATH'] = f"{path_prefix}:{env['PATH']}"
    env.update(env_extra or {})
    body = f'set -euo pipefail\nsource "{LIB}"\n{script}\n'
    return subprocess.run(['bash', '-c', body], env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


# --- scenario parsing / run ids (ODL-122) --------------------------------

@pytest.mark.parametrize('raw, want', [
    ('baseline,wind', ['baseline', 'wind']),
    ('mc_gps mc_gps', ['mc_gps', 'mc_gps']),
    (' a, b ,c  d ', ['a', 'b', 'c', 'd']),
    ('', []),
])
def test_split_scenarios(raw, want):
    r = _lib(f'reg_split_scenarios {raw!r}')
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == want


def test_run_ids_keep_first_name_and_number_repeats():
    r = _lib('reg_run_ids mc_gps baseline mc_gps mc_gps baseline')
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == [
        'mc_gps', 'baseline', 'mc_gps__run2', 'mc_gps__run3', 'baseline__run2']


# --- wait_dds (ODL-121) ---------------------------------------------------

def _docker_stub(tmp_path: Path, inspect: str, exec_out: str, exec_rc: int = 0) -> Path:
    bindir = tmp_path / 'bin'
    bindir.mkdir(exist_ok=True)
    _exe(bindir / 'docker', f'''#!/usr/bin/env bash
echo "$*" >> "{tmp_path}/docker.calls"
case "$1" in
  inspect) {inspect} ;;
  exec) printf '%b' {exec_out!r}; exit {exec_rc} ;;
esac
''')
    return bindir


def test_wait_dds_dead_container_is_not_up(tmp_path):
    # Container gone: inspect fails, exec fails with no output. The old
    # check treated the empty output as "DDS up (try 1)".
    bindir = _docker_stub(tmp_path, 'echo "Error: No such object" >&2; exit 1', '', 1)
    r = _lib('wait_dds', {'WAIT_DDS_TRIES': '3', 'WAIT_DDS_SLEEP': '0'}, str(bindir))
    assert r.returncode == 1
    assert 'DDS up' not in r.stdout
    assert 'not running' in r.stderr


def test_wait_dds_failed_exec_on_running_container_is_not_up(tmp_path):
    bindir = _docker_stub(tmp_path, 'echo true', '', 1)
    r = _lib('wait_dds', {'WAIT_DDS_TRIES': '3', 'WAIT_DDS_SLEEP': '0'}, str(bindir))
    assert r.returncode == 1
    assert 'DDS up' not in r.stdout
    assert 'PX4 DDS not ready' in r.stderr
    calls = (tmp_path / 'docker.calls').read_text().splitlines()
    assert sum(c.startswith('exec') for c in calls) == 3


@pytest.mark.parametrize('out, up', [('0\n', False), ('garbage', False), ('1\n', True), ('2', True)])
def test_wait_dds_needs_a_positive_count(tmp_path, out, up):
    bindir = _docker_stub(tmp_path, 'echo true', out)
    r = _lib('wait_dds', {'WAIT_DDS_TRIES': '2', 'WAIT_DDS_SLEEP': '0'}, str(bindir))
    assert (r.returncode == 0) is up, (r.stdout, r.stderr)
    assert ('DDS up (try 1)' in r.stdout) is up


# --- JSON writers (ODL-123) -----------------------------------------------

NASTY = "it's \"quoted\" ');import os;os._exit(3);('"


def test_judge_error_json_survives_quotes_and_injection(tmp_path):
    d = tmp_path / "pal's results"
    d.mkdir()
    out = d / 'judge_x.json'
    r = _lib(f'reg_write_judge_error {str(out)!r} "$S" "$S" "$S" flight_exit=7 "summary_dir=$S"',
             {'S': NASTY})
    assert r.returncode == 0, r.stderr
    j = json.loads(out.read_text())
    assert j == {'scenario': NASTY, 'run_id': NASTY, 'pass': False, 'error': NASTY,
                 'flight_exit': 7, 'summary_dir': NASTY}


def test_pytest_json_in_apostrophe_path(tmp_path):
    d = tmp_path / "pal's checkout"
    d.mkdir()
    out = d / 'pytest.json'
    r = _lib(f'reg_write_pytest_json {str(out)!r} 1 0 290 250')
    assert r.returncode == 0, r.stderr
    assert json.loads(out.read_text()) == {
        'step': 'pytest', 'pass': True, 'exit_code': 0, 'passed': 290, 'min_passed': 250}


def test_pytest_json_bad_min_is_null_not_crash(tmp_path):
    out = tmp_path / 'pytest.json'
    r = _lib(f'reg_write_pytest_json {str(out)!r} 0 0 290 ""')
    assert r.returncode == 0, r.stderr
    j = json.loads(out.read_text())
    assert j['pass'] is False and j['min_passed'] is None


def test_no_shell_values_inside_python_c():
    # Guard against the ODL-123 pattern coming back: a double-quoted
    # python3 -c program containing ${...}.
    import re
    src = (REPO / 'scripts' / 'run-regression.sh').read_text()
    src += (REPO / 'scripts' / 'regression-lib.sh').read_text()
    assert not re.search(r'python3 -c "[^"]*\$\{', src)


# --- end to end with stubs (ODL-122 / 125 / 138, ODL-123 paths) -----------

@pytest.fixture
def fake_repo(tmp_path):
    root = tmp_path / "pal's ws"
    repo = root / 'dronelab'
    data = root / 'dronelab-data'
    (repo / 'logs').mkdir(parents=True)
    data.mkdir()
    shutil.copytree(REPO / 'scripts', repo / 'scripts')
    shutil.copytree(REPO / 'config', repo / 'config')
    s = repo / 'scripts'
    calls = root / 'calls.log'
    for name in ('stop-all.sh', 'start-dds-agent.sh'):
        _exe(s / name, '#!/usr/bin/env bash\nexit 0\n')
    _exe(s / 'launch-sitl.sh', f'''#!/usr/bin/env bash
echo "launch WORLD=$WORLD MODEL=$MODEL" >> "{calls}"
[ "${{FAIL_LAUNCH:-0}}" = 1 ] && exit 1
exit 0
''')
    _exe(s / 'run-vio-stress.sh', f'''#!/usr/bin/env bash
n=$(ls -d "$ODL_DATA"/results/stub_* 2>/dev/null | wc -l)
d="$ODL_DATA/results/stub_${{n}}"
mkdir -p "$d"
echo '{{"mission": "success"}}' > "$d/summary.json"
echo "fly $1 BAG_DURATION=$BAG_DURATION" >> "{calls}"
echo "summary_dir=/data/results/stub_${{n}}"
''')
    bindir = root / 'bin'
    bindir.mkdir()
    # Stub docker: inspect -> running; exec -> DDS count 1; run judge ->
    # verdicts from JUDGE_VERDICTS (one per call, e.g. "fail pass").
    _exe(bindir / 'docker', f'''#!/usr/bin/env bash
case "$1" in
  inspect) echo true; exit 0 ;;
  rm) exit 0 ;;
  exec) echo 1; exit 0 ;;
  run)
    out=""; sc=""
    while [ $# -gt 0 ]; do
      case "$1" in --out) out="$2"; shift ;; --scenario) sc="$2"; shift ;; esac
      shift
    done
    [ -n "$out" ] || exit 0
    out="${{out/\\/data\\//$ODL_DATA/}}"
    k=$(cat "{root}/judge.n" 2>/dev/null || echo 0); echo $((k + 1)) > "{root}/judge.n"
    read -r -a v <<< "${{JUDGE_VERDICTS:-pass pass pass}}"
    p=false; [ "${{v[k]:-pass}}" = pass ] && p=true
    printf '{{"scenario": "%s", "pass": %s, "pass_at_1": %s, "checks": []}}\\n' "$sc" "$p" "$p" > "$out"
    [ "$p" = true ] ;;
esac
''')
    env = os.environ.copy()
    env.update({
        'PATH': f"{bindir}:{env['PATH']}",
        'ODL_ROOT': str(repo), 'ODL_DATA': str(data),
        'QGC_APPIMAGE': str(root / 'no-qgc.AppImage'), 'QGC_LOG': str(root / 'qgc.log'),
        'SKIP_PYTEST': '1', 'WAIT_DDS_SLEEP': '0',
    })
    for k in ('REPO_DIR', 'DATA_DIR', 'WORKSPACE_DIR', 'QGC_PROC_ROOT'):
        env.pop(k, None)
    return {'repo': repo, 'data': data, 'calls': calls, 'env': env}


def _run_reg(fr, **extra):
    env = dict(fr['env'], **extra)
    r = subprocess.run(['bash', str(fr['repo'] / 'scripts' / 'run-regression.sh')],
                       env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       check=False, timeout=120)
    reports = sorted((fr['data'] / 'results').glob('regression_*'))
    assert reports, r.stdout
    return r, reports[-1]


def test_duplicate_scenario_keeps_both_results(fake_repo):
    # First mc_gps fails, second passes: the old harness kept only the
    # second judge_mc_gps.json.
    r, rep = _run_reg(fake_repo, SCENARIOS='mc_gps mc_gps', JUDGE_VERDICTS='fail pass')
    assert r.returncode == 1, r.stdout
    assert json.loads((rep / 'judge_mc_gps.json').read_text())['pass'] is False
    assert json.loads((rep / 'judge_mc_gps__run2.json').read_text())['pass'] is True
    assert (rep / 'mc_gps' / 'summary.json').is_file()
    assert (rep / 'mc_gps__run2' / 'summary.json').is_file()
    assert (rep / 'flight_mc_gps__run2.log').is_file()
    report = json.loads((rep / 'report.json').read_text())
    assert report['overall_pass'] is False
    assert [(s['run_id'], s['pass']) for s in report['scenarios']] == [
        ('mc_gps', False), ('mc_gps__run2', True)]
    md = (rep / 'report.md').read_text()
    assert '| mc_gps | FAIL' in md and '| mc_gps (run 2) | PASS' in md


def test_duplicate_scenario_all_pass_is_pass(fake_repo):
    r, rep = _run_reg(fake_repo, SCENARIOS='mc_gps,mc_gps')
    assert r.returncode == 0, r.stdout
    assert json.loads((rep / 'report.json').read_text())['overall_pass'] is True


def test_launch_failure_stops_the_flight(fake_repo):
    # ODL-125: `if ! run_flight` disables set -e, so a failed launch used to
    # be ignored and the flight ran against nothing.
    r, rep = _run_reg(fake_repo, SCENARIOS='mc_gps', FAIL_LAUNCH='1')
    assert r.returncode == 1, r.stdout
    calls = fake_repo['calls'].read_text()
    assert 'launch ' in calls and 'fly ' not in calls
    j = json.loads((rep / 'judge_mc_gps.json').read_text())
    assert j['pass'] is False and j['error'] == 'launch_sitl failed'
    assert json.loads((rep / 'report.json').read_text())['overall_pass'] is False


def test_report_uses_per_scenario_bag_duration(fake_repo):
    # ODL-138: fw_mission's registry bag_duration (240) is what it records;
    # the report used to show only the global default.
    r, rep = _run_reg(fake_repo, SCENARIOS='mc_gps fw_mission', BAG_DURATION='100')
    assert r.returncode == 0, r.stdout
    calls = fake_repo['calls'].read_text()
    assert 'fly mc_gps BAG_DURATION=100' in calls
    assert 'fly fw_mission BAG_DURATION=240' in calls
    report = json.loads((rep / 'report.json').read_text())
    assert report['bag_duration_s'] == 100
    assert report['bag_duration_by_run'] == {'mc_gps': 100, 'fw_mission': 240}
    assert 'BAG_DURATION=100 (default; per-scenario: fw_mission=240)' in (rep / 'report.md').read_text()


def test_unknown_scenario_is_recorded(fake_repo):
    r, rep = _run_reg(fake_repo, SCENARIOS='nope')
    assert r.returncode == 1, r.stdout
    assert json.loads((rep / 'judge_nope.json').read_text())['error'] == 'unknown scenario'
