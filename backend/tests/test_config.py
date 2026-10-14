"""Unit tests for application settings, structured logging, and CLI commands."""

import json
import logging
from pathlib import Path

import pytest
from pytest_mock import MockerFixture
from typer.testing import CliRunner

from territorio.cli import app
from territorio.config import Settings
from territorio.domain import StepResult
from territorio.etl.crosswalk import CrosswalkReport
from territorio.etl.verify import CheckOutcome, VerificationReport
from territorio.logging import JsonLogFormatter, configure_logging, get_logger


def test_settings_derived_directories(tmp_path: Path) -> None:
    """Verifies that Settings resolves raw, manual, reference, and reports paths.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    cfg = Settings(
        database_url="postgresql+psycopg://u:p@localhost:5432/db",
        data_dir=tmp_path,
        api_cors_origins="http://localhost:5173,https://territorio.org",
    )
    assert cfg.raw_dir == tmp_path / "raw"
    assert cfg.manual_dir == tmp_path / "manual"
    assert cfg.reference_dir == tmp_path / "reference"
    assert cfg.reports_dir == tmp_path / "reports"
    assert cfg.cors_origin_list == [
        "http://localhost:5173",
        "https://territorio.org",
    ]
    cfg_override = Settings(
        data_dir=tmp_path, reference_dir_override=tmp_path / "custom_ref"
    )
    assert cfg_override.reference_dir == tmp_path / "custom_ref"


def test_settings_loads_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies that environment variables populate Settings fields.

    Args:
        monkeypatch: Pytest fixture for patching environment variables.
    """
    monkeypatch.setenv("TRANSPARENCIA_API_KEY", "env-key-123")
    monkeypatch.setenv("TRANSPARENCIA_RATE_PER_MIN", "95")
    monkeypatch.setenv("HTTP_TIMEOUT_S", "45")
    cfg = Settings(_env_file=None)
    assert cfg.transparencia_api_key == "env-key-123"
    assert cfg.transparencia_rate_per_min == 95
    assert cfg.http_timeout_s == 45.0


def test_structured_logging_and_formatter() -> None:
    """Verifies `configure_logging`, `JsonLogFormatter`, and `get_logger`."""
    configure_logging("DEBUG", json_output=True)
    configure_logging("INFO", json_output=False)
    lg1 = get_logger("etl")
    lg2 = get_logger("territorio.api")
    assert lg1.name == "territorio.etl"
    assert lg2.name == "territorio.api"

    formatter = JsonLogFormatter()
    rec = logging.LogRecord(
        name="territorio.etl",
        level=logging.INFO,
        pathname="pipeline.py",
        lineno=10,
        msg="Step done",
        args=(),
        exc_info=None,
    )
    rec.run_id = 5
    rec.step = "territory"
    out = json.loads(formatter.format(rec))
    assert out["run_id"] == 5
    assert out["step"] == "territory"
    assert out["message"] == "Step done"


def test_cli_commands_dispatch(mocker: MockerFixture, tmp_path: Path) -> None:
    """Verifies `territorio` Typer CLI commands (`db`, `crosswalk`, `etl`).

    Args:
        mocker: Pytest mocker fixture.
        tmp_path: Temporary directory path.
    """
    runner = CliRunner()
    mocker.patch("territorio.cli.upgrade_db")
    mocker.patch("territorio.cli.downgrade_db")
    mocker.patch(
        "territorio.etl.crosswalk.build_and_save_crosswalk",
        return_value=tmp_path / "de_para.csv",
    )
    mocker.patch(
        "territorio.etl.crosswalk.run_crosswalk_validation_cli",
        return_value=CrosswalkReport(total_pairs=5571, name_warnings=[]),
    )
    mocker.patch(
        "territorio.etl.pipeline.run_pipeline",
        return_value=[StepResult(step="territory", rows_in=5571, rows_out=5571)],
    )

    assert runner.invoke(app, ["db", "upgrade"]).exit_code == 0
    assert runner.invoke(app, ["db", "downgrade"]).exit_code == 0
    assert runner.invoke(app, ["crosswalk", "build"]).exit_code == 0
    assert runner.invoke(app, ["crosswalk", "validate"]).exit_code == 0
    assert runner.invoke(app, ["etl", "run", "--all"]).exit_code == 0
    assert runner.invoke(app, ["etl", "run"]).exit_code != 0

    mocker.patch(
        "territorio.etl.verify.run_verification_cli",
        return_value=VerificationReport(
            generated_at="2026-10-12T00:00:00Z",
            all_blocking_passed=True,
            checks=(),
            markdown_path=tmp_path / "quality.md",
        ),
    )
    assert runner.invoke(app, ["etl", "verify"]).exit_code == 0

    mocker.patch(
        "territorio.etl.verify.run_verification_cli",
        return_value=VerificationReport(
            generated_at="2026-10-12T00:00:00Z",
            all_blocking_passed=False,
            checks=(
                CheckOutcome(
                    code="V1",
                    name="Count",
                    passed=False,
                    blocking=True,
                    details={},
                ),
            ),
            markdown_path=tmp_path / "quality.md",
        ),
    )
    assert runner.invoke(app, ["etl", "verify"]).exit_code == 1
