"""Shared pytest fixtures for the Território Eleitoral test suite."""

from pathlib import Path

import pytest

from territorio.config import Settings


@pytest.fixture
def project_root() -> Path:
    """Returns the repository root directory.

    Returns:
        Path to the repository root.
    """
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def test_settings(tmp_path: Path, project_root: Path) -> Settings:
    """Creates an isolated Settings instance pointing to temporary cache directories.

    Args:
        tmp_path: Temporary directory created by pytest.
        project_root: Repository root containing versioned reference files.

    Returns:
        Configured Settings instance for unit tests.
    """
    data_dir = tmp_path / "data"
    (data_dir / "raw").mkdir(parents=True, exist_ok=True)
    (data_dir / "manual").mkdir(parents=True, exist_ok=True)
    (data_dir / "reports").mkdir(parents=True, exist_ok=True)
    return Settings(
        database_url="postgresql+psycopg://territorio:territorio@localhost:5432/territorio",
        data_dir=data_dir,
        reference_dir_override=project_root / "data" / "reference",
        transparencia_api_key="test-cgu-api-key",
        transparencia_rate_per_min=120,
        http_timeout_s=15.0,
        api_cors_origins="http://localhost:5173",
        log_level="DEBUG",
    )
