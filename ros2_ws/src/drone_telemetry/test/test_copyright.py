# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Test license headers of this package.

ament_copyright cannot check this project: its license list (apache2,
bsd*, gplv3, lgplv3, mit, ...) has no AGPL-3.0, so it reported
license=<unknown> for every file and could never pass. This checks the
project's actual header instead: an SPDX AGPL-3.0-only line and a
copyright line near the top of every Python file in the package.
"""
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1]
SKIP_DIRS = {'__pycache__', 'build', 'install', 'log', '.pytest_cache'}


def _py_files():
    return sorted(
        p for p in PKG.rglob('*.py')
        if not SKIP_DIRS.intersection(p.relative_to(PKG).parts))


@pytest.mark.copyright
@pytest.mark.linter
def test_copyright():
    """Every Python file carries the SPDX AGPL-3.0-only and copyright lines."""
    files = _py_files()
    assert files
    bad = []
    for p in files:
        head = p.read_text(errors='replace').splitlines()[:5]
        if not any(line.strip() == '# SPDX-License-Identifier: AGPL-3.0-only'
                   for line in head) or not any('Copyright (C)' in line for line in head):
            bad.append(str(p.relative_to(PKG)))
    assert not bad, 'missing SPDX/copyright header: ' + ', '.join(bad)
