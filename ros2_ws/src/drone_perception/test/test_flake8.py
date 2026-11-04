"""Test flake8 style compliance."""
from ament_flake8.main import main_with_errors
import pytest


@pytest.mark.flake8
@pytest.mark.linter
def test_flake8():
    """Check Python style with flake8."""
    rc, errors = main_with_errors(argv=[])
    assert rc == 0, f'Found {len(errors)} flake8 errors:\n' + '\n'.join(errors)
