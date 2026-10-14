"""Unit tests for ETL provenance tracking and SHA-256 hashing."""

import hashlib
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from territorio.domain import Severity, StepResult
from territorio.etl.provenance import (
    compute_file_sha256,
    record_etl_failure,
    record_quality_issue,
    track_etl_run,
)


def test_compute_file_sha256(tmp_path: Path) -> None:
    """Verifies SHA-256 digest computation on a local file.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    sample = tmp_path / "sample.txt"
    content = b"Territorio Eleitoral 2026"
    sample.write_bytes(content)

    assert compute_file_sha256(sample) == hashlib.sha256(content).hexdigest()


def test_track_etl_run_records_success(mocker: MockerFixture) -> None:
    """Verifies that `track_etl_run` inserts running state and updates to success.

    Args:
        mocker: Pytest-mock fixture used to mock the SQLAlchemy engine and connection.
    """
    conn = mocker.MagicMock()
    insert_result = mocker.MagicMock()
    insert_result.scalar_one.return_value = 42
    conn.execute.return_value = insert_result

    engine = mocker.MagicMock()
    begin_ctx = mocker.MagicMock()
    begin_ctx.__enter__.return_value = conn
    begin_ctx.__exit__.return_value = False
    engine.begin.return_value = begin_ctx

    with track_etl_run(
        engine,
        step="reference",
        source="yaml",
        dataset="party_ideology",
    ) as tracker:
        assert tracker.run_id == 42
        tracker.complete(
            StepResult(
                step="reference",
                rows_in=30,
                rows_out=30,
                dropped={},
                sha256="abc1234",
            )
        )

    assert conn.execute.call_count == 2


def test_track_etl_run_records_failure_and_reraises(mocker: MockerFixture) -> None:
    """Verifies that `track_etl_run` logs status='failed' when an exception occurs.

    Args:
        mocker: Pytest-mock fixture.
    """
    conn = mocker.MagicMock()
    insert_result = mocker.MagicMock()
    insert_result.scalar_one.return_value = 99
    conn.execute.return_value = insert_result

    engine = mocker.MagicMock()
    begin_ctx = mocker.MagicMock()
    begin_ctx.__enter__.return_value = conn
    begin_ctx.__exit__.return_value = False
    engine.begin.return_value = begin_ctx

    with (
        pytest.raises(RuntimeError, match="Simulated ETL failure"),
        track_etl_run(engine, step="territory", source="ibge") as _tracker,
    ):
        raise RuntimeError("Simulated ETL failure")

    assert conn.execute.call_count == 2
    record_etl_failure(conn, run_id=99, item_key="3550308", error="timeout")
    record_quality_issue(
        conn,
        run_id=99,
        check_name="X1",
        severity=Severity.BLOCKING,
        cd_ibge=3550308,
        detail={"msg": "duplicate"},
    )
    assert conn.execute.call_count == 4
