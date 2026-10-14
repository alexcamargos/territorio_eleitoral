"""Unit tests for acceptance verification (`verify.py`) and pipeline orchestration."""

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import sqlalchemy as sa
from pytest_mock import MockerFixture

from territorio.config import Settings
from territorio.domain import HigherIs, ScaleHint, StepResult, Theme, ValueType
from territorio.etl.pipeline import (
    _extract_single_indicator,
    run_indicators_step,
    run_pipeline,
    run_publish_step,
)
from territorio.etl.reference import (
    CoverageExceptionRule,
    IndicatorCatalog,
    IndicatorSpec,
)
from territorio.etl.verify import (
    VerificationError,
    run_database_verification,
    run_verification_cli,
)


def _make_sample_spec(
    code: str = "population", adapter: str = "sidra"
) -> IndicatorSpec:
    """Builds a valid `IndicatorSpec` for verification and pipeline unit tests.

    Args:
        code: Indicator code.
        adapter: Adapter name.

    Returns:
        Configured `IndicatorSpec`.
    """
    return IndicatorSpec(
        code=code,
        label="População",
        description="População residente",
        theme=Theme.SOCIAL,
        tier=1,
        unit="hab",
        value_type=ValueType.CONTINUOUS,
        higher_is=HigherIs.NEUTRAL,
        scale_hint=ScaleHint.LOG,
        valid_range=(0.0, 20_000_000.0),
        adapter=adapter,
        source_params={},
        source_name="IBGE",
        source_url="https://sidra.ibge.gov.br",
        license=None,
        citation=None,
        transform=None,
        ref_year_policy="latest",
        min_coverage=0.99,
        caveat=None,
        verified=True,
    )


def _make_mock_engine_for_verify(
    mocker: MockerFixture,
    *,
    mun_cnt: int = 5571,
    geom_total: int = 16713,
    geom_invalid: int = 0,
    uf_geom_cnt: int = 81,
    unclassified_parties: list[str] | None = None,
    mismatch_cnt: int = 0,
    ind_cov_rows: list[dict[str, Any]] | None = None,
    mv_bad_cnt: int = 0,
    warn_cnt: int = 2,
) -> sa.Engine:
    """Builds a mocked SQLAlchemy engine returning configured V1-V8 check results.

    Args:
        mocker: Pytest mocker fixture.
        mun_cnt: V1 municipality count.
        geom_total: V2 geometry count.
        geom_invalid: V2 invalid geometry count.
        uf_geom_cnt: V3 UF geometry count.
        unclassified_parties: V4 unclassified party list.
        mismatch_cnt: V5 vote sum mismatch count.
        ind_cov_rows: V6 indicator coverage rows.
        mv_bad_cnt: V7 out-of-bounds row count.
        warn_cnt: V8 warning count.

    Returns:
        Mocked SQLAlchemy `Engine`.
    """
    engine = mocker.MagicMock(spec=sa.Engine)
    conn = mocker.MagicMock()
    engine.connect.return_value.__enter__.return_value = conn

    def fake_execute(stmt: Any, params: Any = None) -> Any:
        sql = str(stmt)
        res = mocker.MagicMock()
        if "FROM municipality_geom" in sql:
            res.mappings.return_value.fetchone.return_value = {
                "total": geom_total,
                "invalid_cnt": geom_invalid,
            }
        elif "FROM municipality" in sql:
            res.scalar.return_value = mun_cnt
        elif "FROM uf_geom" in sql:
            res.scalar.return_value = uf_geom_cnt
        elif "LEFT JOIN party_ideology" in sql:
            res.scalars.return_value.all.return_value = unclassified_parties or []
        elif "WHERE s.valid_votes != s.pv_sum" in sql:
            res.scalar.return_value = mismatch_cnt
        elif "FROM mv_indicator_current" in sql:
            res.mappings.return_value.all.return_value = ind_cov_rows or []
        elif "FROM mv_election_mun_bloc" in sql:
            res.scalar.return_value = mv_bad_cnt
        elif "FROM data_quality_issue" in sql:
            res.scalar.return_value = warn_cnt
        return res

    conn.execute.side_effect = fake_execute
    return engine


def test_run_database_verification_passes_and_writes_reports(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Verifies V1-V8 passing checks and `.json`/`.md` report generation.

    Args:
        mocker: Pytest mocker fixture.
        tmp_path: Temporary directory path.
    """
    spec = _make_sample_spec("population", "sidra")
    catalog = IndicatorCatalog(
        indicators={"population": spec},
        coverage_exceptions=(
            CoverageExceptionRule(
                cd_ibge=4314548,
                name="Pinto Bandeira",
                uf="RS",
                missing_reason="Criado em 2013",
                applies_to_ref_years_before=2013,
                applies_to_adapters=("sidra",),
            ),
        ),
    )
    engine = _make_mock_engine_for_verify(
        mocker,
        ind_cov_rows=[
            {
                "indicator_code": "population",
                "ref_year": 2022,
                "valid_cnt": 5570,
                "total_cnt": 5571,
            }
        ],
        warn_cnt=3,
    )

    report = run_database_verification(
        engine,
        indicator_catalog=catalog,
        reports_dir=tmp_path,
        run_id=42,
    )
    assert report.all_blocking_passed is True
    assert report.blocking_count == 0
    assert report.warning_count == 3
    assert report.markdown_path == tmp_path / "quality_42.md"

    json_file = tmp_path / "quality_42.json"
    md_file = tmp_path / "quality_42.md"
    assert json_file.exists()
    assert md_file.exists()

    payload = json.loads(json_file.read_text(encoding="utf-8"))
    assert payload["all_blocking_passed"] is True
    assert len(payload["checks"]) == 8
    assert "APROVADO" in md_file.read_text(encoding="utf-8")


def test_run_database_verification_raises_on_blocking_failure(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Verifies that failing V1, V4, or V6 raises `VerificationError`.

    Args:
        mocker: Pytest mocker fixture.
        tmp_path: Temporary directory path.
    """
    spec = _make_sample_spec("population", "sidra")
    catalog = IndicatorCatalog(
        indicators={"population": spec},
        coverage_exceptions=(),
    )
    engine = _make_mock_engine_for_verify(
        mocker,
        mun_cnt=5570,
        unclassified_parties=["NOVO_PARTIDO"],
        ind_cov_rows=[
            {
                "indicator_code": "population",
                "ref_year": 2022,
                "valid_cnt": 1000,
                "total_cnt": 5571,
            }
        ],
    )

    with pytest.raises(VerificationError, match="V1"):
        run_database_verification(
            engine,
            indicator_catalog=catalog,
            reports_dir=tmp_path,
            run_id="fail",
        )


def test_run_verification_cli_returns_report_without_raising(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Verifies `run_verification_cli` returns report even when checks fail.

    Args:
        mocker: Pytest mocker fixture.
        tmp_path: Temporary directory path.
    """
    engine = _make_mock_engine_for_verify(mocker, mun_cnt=5000)
    mocker.patch("territorio.etl.verify.create_db_engine", return_value=engine)
    mocker.patch(
        "territorio.etl.verify.load_indicators_catalog",
        return_value=IndicatorCatalog(indicators={}, coverage_exceptions=()),
    )
    settings = Settings(data_dir=tmp_path / "data")
    report = run_verification_cli(settings)
    assert report.all_blocking_passed is False
    assert report.blocking_count == 1


def test_run_pipeline_dispatches_steps(mocker: MockerFixture, tmp_path: Path) -> None:
    """Verifies `run_pipeline` dispatches `--all` and individual `--step` calls.

    Args:
        mocker: Pytest mocker fixture.
        tmp_path: Temporary directory path.
    """
    engine = mocker.MagicMock(spec=sa.Engine)
    settings = Settings(data_dir=tmp_path / "data")

    m_terr = mocker.patch(
        "territorio.etl.pipeline.run_territory_step",
        return_value=StepResult(step="territory", rows_in=5571, rows_out=5571),
    )
    m_elec = mocker.patch(
        "territorio.etl.pipeline.run_elections_step",
        return_value=StepResult(step="elections", rows_in=100, rows_out=100),
    )
    m_ind = mocker.patch(
        "territorio.etl.pipeline.run_indicators_step",
        return_value=StepResult(step="indicators", rows_in=50, rows_out=50),
    )
    m_pub = mocker.patch(
        "territorio.etl.pipeline.run_publish_step",
        return_value=1,
    )

    res_all = run_pipeline(settings=settings, all_steps=True, engine=engine)
    assert [r.step for r in res_all] == [
        "territory",
        "elections",
        "indicators",
        "publish",
    ]
    assert m_terr.call_count == 1
    assert m_elec.call_count == 1
    assert m_ind.call_count == 1
    assert m_pub.call_count == 1

    mocker.patch(
        "territorio.etl.pipeline.sync_reference_to_db",
        return_value=StepResult(step="reference", rows_in=36, rows_out=36),
    )
    res_ref = run_pipeline(settings=settings, step="reference", engine=engine)
    assert res_ref[0].step == "reference"
    assert res_ref[0].rows_out == 36

    with pytest.raises(ValueError, match="Unknown ETL step"):
        run_pipeline(settings=settings, step="invalid_step", engine=engine)


def test_run_indicators_step_and_publish_step(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Verifies `run_indicators_step` ordering and `run_publish_step`.

    Args:
        mocker: Pytest mocker fixture.
        tmp_path: Temporary directory path.
    """
    engine = mocker.MagicMock(spec=sa.Engine)
    conn = mocker.MagicMock()
    engine.connect.return_value.__enter__.return_value = conn

    res_codes = mocker.MagicMock()
    res_codes.scalars.return_value.all.return_value = [1100015, 3550308]
    res_existing = mocker.MagicMock()
    res_existing.mappings.return_value.all.return_value = []
    conn.execute.side_effect = [res_codes, res_existing]

    mocker.patch("territorio.etl.pipeline.sync_reference_to_db")
    spec = _make_sample_spec("area_km2", "ibge_geo")
    cat = IndicatorCatalog(
        indicators={"area_km2": spec},
        coverage_exceptions=(),
    )
    mocker.patch("territorio.etl.pipeline.load_indicators_catalog", return_value=cat)
    fake_df = pd.DataFrame(
        {
            "indicator_code": ["area_km2", "area_km2"],
            "ref_year": [2025, 2025],
            "cd_ibge": [1100015, 3550308],
            "value": [100.0, 200.0],
            "value_text": [None, None],
            "missing_reason": [None, None],
        }
    )
    mocker.patch(
        "territorio.etl.pipeline._extract_single_indicator",
        return_value=fake_df,
    )

    settings = Settings(data_dir=tmp_path / "data")
    step_res = run_indicators_step(engine, settings, only_indicators=["area_km2"])
    assert step_res.rows_out == 2

    conn.execute.side_effect = [res_codes, res_existing]
    with pytest.raises(ValueError, match="Unknown indicator code"):
        run_indicators_step(engine, settings, indicator_code="non_existent")


def test_extract_single_indicator_ibge_geo_and_publish(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Verifies `_extract_single_indicator` for `ibge_geo` and `run_publish_step`.

    Args:
        mocker: Pytest mocker fixture.
        tmp_path: Temporary directory path.
    """
    sqlite_engine = sa.create_engine("sqlite:///:memory:")
    with sqlite_engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                CREATE TABLE etl_run (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    step TEXT,
                    source TEXT,
                    dataset TEXT,
                    source_url TEXT,
                    source_version TEXT,
                    sha256 TEXT,
                    params TEXT,
                    status TEXT,
                    rows_in INTEGER,
                    rows_out INTEGER,
                    dropped TEXT,
                    error TEXT,
                    started_at TEXT,
                    finished_at TEXT
                )
                """
            )
        )
        conn.execute(
            sa.text("CREATE TABLE municipality (cd_ibge INTEGER, area_km2 REAL)")
        )
        conn.execute(
            sa.text(
                "INSERT INTO municipality VALUES (1100015, 7067.0), (3550308, 1521.0)"
            )
        )

    mocker.patch("territorio.etl.pipeline.replace_indicator_values", return_value=2)
    spec = _make_sample_spec("area_km2", "ibge_geo")
    cat = IndicatorCatalog(
        indicators={"area_km2": spec},
        coverage_exceptions=(),
    )
    settings = Settings(data_dir=tmp_path / "data")
    df = _extract_single_indicator(
        spec,
        engine=sqlite_engine,
        settings=settings,
        master_ibge_codes=[1100015, 3550308],
        catalog=cat,
        loaded_frames={},
    )
    assert len(df) == 2

    mocker.patch("territorio.etl.pipeline.load_indicators_catalog", return_value=cat)
    mocker.patch("territorio.etl.pipeline.publish_dataset_version", return_value=7)
    mocker.patch("territorio.etl.pipeline.run_database_verification")
    dv_id = run_publish_step(sqlite_engine, settings)
    assert dv_id == 7


def test_load_election_contest_and_indicator_values(
    mocker: MockerFixture,
) -> None:
    """Verifies `replace_election_contest_data`, `replace_indicator_values`, publish.

    Args:
        mocker: Pytest mocker fixture.
    """
    from territorio.etl.load import (
        publish_dataset_version,
        replace_election_contest_data,
        replace_indicator_values,
    )

    conn = mocker.MagicMock(spec=sa.Connection)
    res_cand = mocker.MagicMock()
    res_cand.all.return_value = [(1001, 501)]
    conn.execute.return_value = res_cand

    turnout_df = pd.DataFrame(
        [
            {
                "cd_ibge": 3550308,
                "eligible": 1000,
                "attendance": 800,
                "abstentions": 200,
                "valid": 750,
                "blank": 20,
                "null_votes": 30,
                "annulled": 0,
            }
        ]
    )
    party_vote_df = pd.DataFrame(
        [
            {
                "cd_ibge": 3550308,
                "party_code": "PT",
                "nominal_votes": 700,
                "legend_votes": 50,
            }
        ]
    )
    candidates_df = pd.DataFrame(
        [
            {
                "uf": "SP",
                "sq_candidato": 1001,
                "number": 13,
                "ballot_name": "CAND A",
                "party_code": "PT",
                "federation": None,
                "coalition": "COLIG",
                "result_status": "ELEITO",
            }
        ]
    )
    candidate_vote_df = pd.DataFrame(
        [{"cd_ibge": 3550308, "sq_candidato": 1001, "votes": 700}]
    )
    abroad_df = pd.DataFrame([{"party_code": "PT", "votes": 120}])

    written = replace_election_contest_data(
        conn,
        election_id=1,
        turnout_df=turnout_df,
        party_vote_df=party_vote_df,
        candidates_df=candidates_df,
        candidate_vote_df=candidate_vote_df,
        abroad_df=abroad_df,
    )
    assert written == 4

    ind_df = pd.DataFrame(
        [
            {
                "cd_ibge": 3550308,
                "ref_year": 2023,
                "value": 85000.0,
                "value_text": None,
                "missing_reason": None,
            },
            {
                "cd_ibge": 3304557,
                "ref_year": 2023,
                "value": float("nan"),
                "value_text": "Metrópole",
                "missing_reason": "nao_informado",
            },
        ]
    )
    assert replace_indicator_values(conn, indicator_code="gdp", values_df=ind_df) == 2
    assert (
        replace_indicator_values(conn, indicator_code="gdp", values_df=pd.DataFrame())
        == 0
    )

    engine = mocker.MagicMock(spec=sa.Engine)
    tx_conn = mocker.MagicMock()
    engine.begin.return_value.__enter__.return_value = tx_conn
    res_dv = mocker.MagicMock()
    res_dv.scalar_one.return_value = 9
    tx_conn.execute.return_value = res_dv
    assert publish_dataset_version(engine, etl_run_id=1) == 9
