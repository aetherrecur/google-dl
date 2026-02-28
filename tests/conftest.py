"""Shared test fixtures for gdrive_dl tests."""

import pytest


@pytest.fixture
def tmp_output_dir(tmp_path):
    """Temporary directory for download output."""
    output = tmp_path / "output"
    output.mkdir()
    return output
