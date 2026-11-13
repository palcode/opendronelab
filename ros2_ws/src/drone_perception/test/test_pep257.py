# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Test pep257 docstring compliance."""
from ament_pep257.main import main
import pytest


@pytest.mark.pep257
@pytest.mark.linter
def test_pep257():
    """Check Python docstrings with pep257."""
    rc = main(argv=['.', 'test'])
    assert rc == 0, 'Found code style errors / warnings'
