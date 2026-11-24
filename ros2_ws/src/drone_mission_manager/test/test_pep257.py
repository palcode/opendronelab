# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Test pep257 docstring compliance of this package."""
from pathlib import Path

import pytest

main = pytest.importorskip(
    'ament_pep257.main',
    reason='ament_pep257 not importable (source /opt/ros/jazzy/setup.bash)',
).main

PKG = Path(__file__).resolve().parents[1]


@pytest.mark.pep257
@pytest.mark.linter
@pytest.mark.xfail(
    strict=True,
    reason='known pep257 findings that predate this check; remove this mark '
           'once the package is clean (strict: a clean run fails until then)')
def test_pep257():
    """Check Python docstrings with pep257."""
    rc = main(argv=[str(PKG)])
    assert rc == 0, 'Found code style errors / warnings'
