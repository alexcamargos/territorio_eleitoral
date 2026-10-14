"""Provenance tracking (`etl_run`, `etl_failure`, `data_quality_issue`) and SHA-256."""

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa

from territorio.db.tables import data_quality_issue, etl_failure, etl_run
from territorio.domain import Severity, StepResult


def compute_file_sha256(path: Path) -> str:
    """Computes the SHA-256 hex digest of a file in chunks.

    Args:
        path: Path to the file on disk.

    Returns:
        Lowercase hexadecimal SHA-256 string.

    Raises:
        FileNotFoundError: If `path` does not exist.
    """
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class EtlRunTracker:
    """Mutable handle yielded inside `track_etl_run` to record step completion metrics.

    Attributes:
        run_id: Database primary key of the active `etl_run` row.
        result: StepResult populated via `complete()`.
    """

    def __init__(self, run_id: int) -> None:
        """Initializes the tracker for a specific run ID.

        Args:
            run_id: Primary key of the `etl_run` row.
        """
        self.run_id = run_id
        self.result: StepResult | None = None

    def complete(self, result: StepResult) -> None:
        """Registers the completed StepResult metrics for the run.

        Args:
            result: StepResult containing row counts and provenance digests.
        """
        self.result = result


@contextmanager
def track_etl_run(
    engine: sa.Engine,
    *,
    step: str,
    source: str | None = None,
    dataset: str | None = None,
    source_url: str | None = None,
    params: dict[str, Any] | None = None,
) -> Iterator[EtlRunTracker]:
    """Context manager that logs the lifecycle of an ETL step in `etl_run`.

    Args:
        engine: SQLAlchemy Engine connected to the database.
        step: Pipeline step name (e.g. 'reference', 'territory', 'elections').
        source: Source identifier (e.g. 'tse', 'ibge_sidra').
        dataset: Dataset or indicator code being processed.
        source_url: Initial source URL if known at start time.
        params: Optional dictionary of execution parameters.

    Yields:
        EtlRunTracker containing `run_id` and `complete(StepResult)`.

    Raises:
        Exception: Re-raises any exception raised inside the context block.
    """
    with engine.begin() as conn:
        stmt = (
            sa.insert(etl_run)
            .values(
                step=step,
                source=source,
                dataset=dataset,
                source_url=source_url,
                params=params or {},
                status="running",
                started_at=datetime.now(UTC),
            )
            .returning(etl_run.c.id)
        )
        run_id = int(conn.execute(stmt).scalar_one())

    tracker = EtlRunTracker(run_id=run_id)
    try:
        yield tracker
    except Exception as exc:
        with engine.begin() as conn:
            conn.execute(
                sa.update(etl_run)
                .where(etl_run.c.id == run_id)
                .values(
                    status="failed",
                    error=str(exc),
                    finished_at=datetime.now(UTC),
                )
            )
        raise

    res = tracker.result
    with engine.begin() as conn:
        conn.execute(
            sa.update(etl_run)
            .where(etl_run.c.id == run_id)
            .values(
                status="success",
                rows_in=res.rows_in if res else None,
                rows_out=res.rows_out if res else None,
                dropped=res.dropped if res else {},
                source_url=(res.source_url if res and res.source_url else source_url),
                source_version=res.source_version if res else None,
                sha256=res.sha256 if res else None,
                finished_at=datetime.now(UTC),
            )
        )


def record_etl_failure(
    conn: sa.Connection,
    *,
    run_id: int,
    item_key: str,
    error: str,
) -> None:
    """Records a per-item extraction failure in `etl_failure` to support `--resume`.

    Args:
        conn: Active SQLAlchemy Connection.
        run_id: Foreign key to `etl_run.id`.
        item_key: Identifier of the failed item (e.g. `3550308:202609`).
        error: Error message description.
    """
    conn.execute(
        sa.insert(etl_failure).values(
            run_id=run_id,
            item_key=item_key,
            error=error,
        )
    )


def record_quality_issue(
    conn: sa.Connection,
    *,
    run_id: int,
    check_name: str,
    severity: Severity,
    detail: dict[str, Any],
    cd_ibge: int | None = None,
) -> None:
    """Inserts a data quality finding into `data_quality_issue`.

    Args:
        conn: Active SQLAlchemy Connection.
        run_id: Foreign key to `etl_run.id`.
        check_name: Identifier of the quality check (e.g. 'X6', 'E1', 'COVERAGE').
        severity: Severity level ('blocking', 'warning', 'info').
        detail: Structured JSON payload with details of the finding.
        cd_ibge: Optional 7-digit municipality code associated with the issue.
    """
    conn.execute(
        sa.insert(data_quality_issue).values(
            run_id=run_id,
            check_name=check_name,
            severity=str(severity),
            cd_ibge=cd_ibge,
            detail=detail,
        )
    )
