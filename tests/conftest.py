"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def temp_artifacts_dir(tmp_path: Path) -> Path:
    """Isolated directory for model artifact round-trip tests."""
    return tmp_path / "temp"
