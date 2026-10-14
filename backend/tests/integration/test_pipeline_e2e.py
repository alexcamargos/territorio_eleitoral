"""End-to-end PostGIS integration test for the ETL pipeline and verification."""

from pathlib import Path

import pytest
import sqlalchemy as sa

from territorio.config import get_settings
from territorio.db.engine import create_db_engine, upgrade_db
from territorio.etl.reference import sync_reference_to_db
from territorio.etl.verify import run_database_verification


@pytest.mark.integration
def test_pipeline_reference_sync_and_verification_queries(
    tmp_path: Path,
) -> None:
    """Verifies reference sync and V1-V8 SQL execution against PostGIS.

    Args:
        tmp_path: Pytest temporary directory for quality reports.
    """
    settings = get_settings()
    engine = create_db_engine(settings.database_url)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except Exception as exc:
        engine.dispose()
        pytest.skip(f"PostGIS database unavailable: {exc}")

    upgrade_db(settings.database_url, revision="head")
    step_res = sync_reference_to_db(engine, settings.reference_dir)
    assert step_res.step == "reference"
    assert step_res.rows_out >= 90

    with engine.connect() as conn:
        pi_cnt = int(
            conn.execute(sa.text("SELECT COUNT(*) FROM party_ideology")).scalar() or 0
        )
        el_cnt = int(
            conn.execute(sa.text("SELECT COUNT(*) FROM election")).scalar() or 0
        )
        ind_cnt = int(
            conn.execute(sa.text("SELECT COUNT(*) FROM indicator")).scalar() or 0
        )
    assert pi_cnt >= 30
    assert el_cnt >= 6
    assert ind_cnt >= 28

    report = run_database_verification(
        engine,
        expected_municipalities=0,
        reports_dir=tmp_path,
        run_id="e2e",
        raise_on_failure=False,
    )
    assert len(report.checks) == 8
    assert (tmp_path / "quality_e2e.json").exists()
    assert (tmp_path / "quality_e2e.md").exists()
    engine.dispose()
