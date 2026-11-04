"""Test copyright headers."""
from ament_copyright.main import main
import pytest


@pytest.mark.copyright
@pytest.mark.linter
def test_copyright():
    """Check copyright headers (permissive check)."""
    rc = main(argv=['.', 'test'])
    assert rc == 0, 'Found errors'
