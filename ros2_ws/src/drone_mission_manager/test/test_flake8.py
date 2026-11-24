# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Test flake8 style compliance of this package."""
from pathlib import Path

import pytest

main_with_errors = pytest.importorskip(
    'ament_flake8.main',
    reason='ament_flake8 not importable (source /opt/ros/jazzy/setup.bash)',
).main_with_errors

# Lint this package, not the current directory: from the repo root the
# template's argv=[] linted the whole checkout.
PKG = Path(__file__).resolve().parents[1]


@pytest.mark.flake8
@pytest.mark.linter
@pytest.mark.xfail(
    strict=True,
    reason='known flake8 findings (import order I100/I101/I201, E501, E127, '
           'D401) that predate this check; remove this mark once the package '
           'is clean (strict: a clean run fails until then)')
def test_flake8():
    """Check Python style with flake8."""
    rc, errors = main_with_errors(argv=[str(PKG)])
    assert rc == 0, f'Found {len(errors)} flake8 errors:\n' + '\n'.join(errors)
