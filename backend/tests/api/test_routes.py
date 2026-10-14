"""Unit tests for FastAPI routes, ETag caching, error envelopes, and repository."""

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from territorio.api.errors import ApiError
from territorio.api.main import create_app
from territorio.api.repository import (
    SqlDataRepository,
    validate_bloc,
    validate_office_round_uf,
    zoom_to_lod,
)
from territorio.domain import Bloc, Office


def test_zoom_to_lod_and_validators() -> None:
    """Verifies LOD zoom mapping and parameter validation helpers."""
    assert zoom_to_lod(0) == 0
    assert zoom_to_lod(5) == 0
    assert zoom_to_lod(6) == 1
    assert zoom_to_lod(8) == 1
    assert zoom_to_lod(9) == 2
    assert zoom_to_lod(12) == 2

    with pytest.raises(ApiError) as exc_info:
        zoom_to_lod(13)
    assert exc_info.value.status_code == 404

    off, rnd, uf = validate_office_round_uf("president", 2, "sp")
    assert off == Office.PRESIDENT
    assert rnd == 2
    assert uf == "SP"

    with pytest.raises(ApiError) as exc_round:
        validate_office_round_uf("senator", 2)
    assert exc_round.value.status_code == 400
    assert exc_round.value.code == "INVALID_PARAMETER"

    with pytest.raises(ApiError):
        validate_office_round_uf("invalid_office", 1)

    with pytest.raises(ApiError):
        validate_office_round_uf("president", 3)

    with pytest.raises(ApiError):
        validate_office_round_uf("president", 1, "XX")

    assert validate_bloc("LEFT") == Bloc.LEFT
    with pytest.raises(ApiError):
        validate_bloc("far_left")


def test_fastapi_routes_etag_and_error_envelopes(mocker: MockerFixture) -> None:
    """Verifies all `/api/v1/*` and `/tiles/*` routes, ETag 304, and RFC 9457 errors.

    Args:
        mocker: Pytest mocker fixture.
    """
    mock_repo = mocker.MagicMock(spec=SqlDataRepository)
    mock_repo.get_dataset_version_id.return_value = 3
    mock_repo.get_health.return_value = {
        "status": "ok",
        "postgis_version": "3.5",
        "dataset_version": 3,
        "published_at": "2026-10-12T10:00:00Z",
        "municipality_count": 5571,
    }
    mock_repo.get_meta.return_value = {
        "dataset_version": 3,
        "default_selection": {
            "year": 2026,
            "round": 1,
            "office": "president",
            "bloc": "right",
            "indicator": "gdp_per_capita",
        },
        "elections": [],
        "indicators": [],
        "ufs": [],
        "party_ideology": [],
    }
    mock_repo.get_election_map.return_value = {
        "election": {"year": 2026, "office": "president", "round": 1},
        "national_summary": {},
        "quantiles": {},
        "columns": [
            "cd_ibge",
            "left_share",
            "center_share",
            "right_share",
            "lr_balance",
            "leading_bloc",
            "valid_votes",
        ],
        "rows": [[3550308, 0.47, 0.09, 0.44, -0.03, "left", 6812440]],
    }
    mock_repo.get_indicator_map.return_value = {
        "indicator": {"code": "gdp_per_capita", "ref_year": 2023},
        "summary": {"count_valid": 5570, "count_missing": 1},
        "columns": ["cd_ibge", "value"],
        "rows": [[3550308, 89420.5]],
    }
    mock_repo.get_analysis.return_value = {
        "scope": {
            "year": 2026,
            "office": "president",
            "round": 1,
            "bloc": "right",
            "uf": None,
        },
        "indicator": {"code": "gdp_per_capita"},
        "sample": {
            "total_municipalities": 5571,
            "valid_pairs": 5570,
            "missing_pairs": 1,
        },
        "correlation": {"spearman_rho": 0.42},
        "trendline": {"model": "log10", "points": []},
        "deciles": [],
        "scatter": {
            "columns": ["cd_ibge", "x", "y", "valid_votes", "region"],
            "rows": [],
        },
        "insights": [],
    }
    mock_repo.search_municipalities.return_value = [
        {
            "cd_ibge": 3550308,
            "name": "São Paulo",
            "uf": "SP",
            "region": "Sudeste",
            "bbox": [-46.8, -24.0, -46.3, -23.3],
        }
    ]
    mock_repo.get_municipality_detail.return_value = {
        "municipality": {"cd_ibge": 3550308, "name": "São Paulo"},
        "elections": {},
        "indicators": [],
    }
    mock_repo.get_mvt_tile.return_value = b"\x1a\x03mvt"

    app = create_app(repository=mock_repo)
    client = TestClient(app)

    # 1. Health & Meta + ETag 304
    r_health = client.get("/api/v1/health")
    assert r_health.status_code == 200
    assert r_health.json()["municipality_count"] == 5571

    r_meta = client.get("/api/v1/meta")
    assert r_meta.status_code == 200
    etag = r_meta.headers["etag"]
    assert etag.startswith('W/"dv3-')
    assert r_meta.headers["x-dataset-version"] == "3"

    r_meta_304 = client.get("/api/v1/meta", headers={"If-None-Match": etag})
    assert r_meta_304.status_code == 304
    assert mock_repo.get_meta.call_count == 1  # Not called again on 304!

    # 2. Elections map & Indicator map
    r_el = client.get("/api/v1/elections/2026/president/1/map")
    assert r_el.status_code == 200
    assert r_el.json()["rows"][0][0] == 3550308

    r_ind = client.get("/api/v1/indicators/gdp_per_capita/map")
    assert r_ind.status_code == 200

    # 3. Analysis & Validation error (422)
    r_an = client.get(
        "/api/v1/analysis?year=2026&office=president&round=1&indicator=gdp_per_capita"
    )
    assert r_an.status_code == 200

    r_422 = client.get("/api/v1/analysis?year=bad_int")
    assert r_422.status_code == 422
    assert r_422.json()["error"]["code"] == "VALIDATION_ERROR"

    # 4. Municipalities search & detail
    r_search = client.get("/api/v1/municipalities/search?q=Sao")
    assert r_search.status_code == 200
    assert r_search.json()["items"][0]["cd_ibge"] == 3550308

    r_mun = client.get("/api/v1/municipalities/3550308")
    assert r_mun.status_code == 200
    assert r_mun.json()["municipality"]["cd_ibge"] == 3550308

    # 5. Vector tiles & ETag 304
    r_tile = client.get("/tiles/municipalities/4/5/8.pbf")
    assert r_tile.status_code == 200
    assert r_tile.headers["content-type"] == "application/vnd.mapbox-vector-tile"
    tile_etag = r_tile.headers["etag"]

    r_tile_304 = client.get(
        "/tiles/municipalities/4/5/8.pbf", headers={"If-None-Match": tile_etag}
    )
    assert r_tile_304.status_code == 304

    # 6. Domain ApiError handling (404)
    mock_repo.get_indicator_map.side_effect = ApiError(
        status_code=404,
        code="INDICATOR_NOT_FOUND",
        message="Não encontrado",
        details={"indicator_code": "foo"},
    )
    r_404 = client.get("/api/v1/indicators/foo/map")
    assert r_404.status_code == 404
    assert r_404.json()["error"]["code"] == "INDICATOR_NOT_FOUND"


def test_sql_data_repository_methods_with_mock_engine(
    mocker: MockerFixture,
) -> None:
    """Exercises `SqlDataRepository` query logic against a mocked SQLAlchemy engine.

    Args:
        mocker: Pytest mocker fixture.
    """
    mock_engine = mocker.MagicMock()
    mock_conn = mocker.MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn

    repo = SqlDataRepository(mock_engine)

    # 1. get_dataset_version_id: success and 503 when None
    mock_conn.execute.return_value.fetchone.return_value = (5,)
    assert repo.get_dataset_version_id() == 5

    mock_conn.execute.return_value.fetchone.return_value = None
    with pytest.raises(ApiError) as exc_503:
        repo.get_dataset_version_id()
    assert exc_503.value.status_code == 503

    # 2. get_health
    res_pg = mocker.MagicMock()
    res_pg.scalar.return_value = "3.5"
    res_cnt = mocker.MagicMock()
    res_cnt.scalar.return_value = 5571
    res_dv = mocker.MagicMock()
    res_dv.fetchone.return_value = (5, datetime(2026, 10, 12, tzinfo=UTC))
    mock_conn.execute.side_effect = [res_pg, res_cnt, res_dv]
    health = repo.get_health()
    assert health["dataset_version"] == 5
    assert health["municipality_count"] == 5571

    # 3. get_meta
    res_dv_id = mocker.MagicMock()
    res_dv_id.fetchone.return_value = (5,)
    res_el = mocker.MagicMock()
    res_el.mappings.return_value.all.return_value = [
        {
            "id": 1,
            "year": 2026,
            "round": 1,
            "office": "president",
            "system": "majoritarian",
            "scope": "national",
            "votes_per_voter": 1,
            "election_date": date(2026, 10, 4),
            "source_version": "v1",
        }
    ]
    res_ind = mocker.MagicMock()
    res_ind.mappings.return_value.all.return_value = [
        {
            "code": "gdp_per_capita",
            "label": "PIB per capita",
            "description": "PIB",
            "theme": "economy",
            "tier": 1,
            "unit": "R$",
            "value_type": "continuous",
            "higher_is": "neutral",
            "scale_hint": "log",
            "source_name": "IBGE",
            "source_url": "https://ibge.gov.br",
            "caveat": None,
            "ref_year": 2023,
            "coverage": 0.9998,
        }
    ]
    res_pi = mocker.MagicMock()
    res_pi.mappings.return_value.all.return_value = [
        {
            "party_code": "PT",
            "score": 2.97,
            "bloc": "left",
            "method": "survey",
            "source": "Bolognesi",
        }
    ]
    mock_conn.execute.side_effect = [res_dv_id, res_el, res_ind, res_pi]
    meta_out = repo.get_meta()
    assert meta_out["dataset_version"] == 5
    assert len(meta_out["elections"]) == 1
    assert len(meta_out["indicators"]) == 1
    assert len(meta_out["ufs"]) == 27

    # 4. get_election_map
    res_map = mocker.MagicMock()
    res_map.mappings.return_value.all.return_value = [
        {
            "cd_ibge": 3550308,
            "eligible": 1000,
            "attendance": 800,
            "valid_votes": 750,
            "left_votes": 300,
            "center_votes": 150,
            "right_votes": 300,
            "left_share": 0.4,
            "center_share": 0.2,
            "right_share": 0.4,
            "lr_balance": 0.0,
            "leading_bloc": "right",
        }
    ]
    res_abroad = mocker.MagicMock()
    res_abroad.scalar.return_value = 5000
    mock_conn.execute.side_effect = [res_map, res_abroad]
    el_map = repo.get_election_map(2026, "president", 1)
    assert el_map["national_summary"]["abroad_valid_votes"] == 5000
    assert len(el_map["rows"]) == 1
    assert "center_share" in el_map["quantiles"]

    # 5. get_analysis
    res_ind_meta = mocker.MagicMock()
    res_ind_meta.mappings.return_value.fetchone.return_value = {
        "code": "gdp_per_capita",
        "label": "PIB per capita",
        "unit": "R$",
        "value_type": "continuous",
        "scale_hint": "log",
        "source_name": "IBGE",
        "caveat": None,
    }
    res_joined = mocker.MagicMock()
    res_joined.mappings.return_value.all.return_value = [
        {
            "cd_ibge": 3500000 + i,
            "region": "Sudeste",
            "valid_votes": 1000,
            "left_votes": 400,
            "center_votes": 100,
            "right_votes": 500,
            "left_share": 0.4,
            "center_share": 0.1,
            "right_share": 0.5,
            "ref_year": 2023,
            "ind_value": float((i + 1) * 1000),
            "ind_text": None,
        }
        for i in range(35)
    ]
    mock_conn.execute.side_effect = [res_ind_meta, res_joined]
    analysis_out = repo.get_analysis(
        year=2026,
        office_str="president",
        round_num=1,
        indicator_code="gdp_per_capita",
        bloc_str="right",
    )
    assert analysis_out["sample"]["valid_pairs"] == 35
    assert len(analysis_out["deciles"]) == 10
    assert len(analysis_out["insights"]) >= 3

    # 6. get_mvt_tile & out-of-bounds check
    res_tile = mocker.MagicMock()
    res_tile.scalar.return_value = b"\x1a\x02ok"
    mock_conn.execute.side_effect = [res_tile]
    assert repo.get_mvt_tile(5, 2, 1, 1) == b"\x1a\x02ok"
    assert repo.get_mvt_tile(5, 2, 1, 1) == b"\x1a\x02ok"

    with pytest.raises(ApiError) as exc_coord:
        repo.get_mvt_tile(5, 2, 99, 0)
    assert exc_coord.value.status_code == 404

    # 7. get_indicator_map (continuous)
    res_ind_m = mocker.MagicMock()
    res_ind_m.mappings.return_value.fetchone.return_value = {
        "code": "gdp_per_capita",
        "label": "PIB per capita",
        "theme": "economy",
        "unit": "R$",
        "value_type": "continuous",
        "higher_is": "better",
        "scale_hint": "log",
        "source_name": "IBGE",
        "caveat": None,
    }
    res_max_yr = mocker.MagicMock()
    res_max_yr.scalar.return_value = 2023
    res_ind_rows = mocker.MagicMock()
    res_ind_rows.mappings.return_value.all.return_value = [
        {"cd_ibge": 3550308, "value": 85000.0, "value_text": None},
        {"cd_ibge": 3304557, "value": None, "value_text": None},
    ]
    mock_conn.execute.side_effect = [res_ind_m, res_max_yr, res_ind_rows]
    ind_map = repo.get_indicator_map("gdp_per_capita")
    assert ind_map["summary"]["count_valid"] == 1
    assert ind_map["summary"]["count_missing"] == 1

    # 8. search_municipalities & get_municipality_detail
    res_search = mocker.MagicMock()
    res_search.mappings.return_value.all.return_value = [
        {
            "cd_ibge": 3550308,
            "name": "São Paulo",
            "uf": "SP",
            "region": "Sudeste",
            "bbox": [-46.8, -24.0, -46.3, -23.3],
        }
    ]
    mock_conn.execute.side_effect = [res_search]
    found = repo.search_municipalities("São Paulo", limit=5)
    assert len(found) == 1

    res_mun_row = mocker.MagicMock()
    res_mun_row.mappings.return_value.fetchone.return_value = {
        "cd_ibge": 3550308,
        "name": "São Paulo",
        "uf": "SP",
        "uf_code": 35,
        "region": "Sudeste",
        "is_capital": True,
        "area_km2": 1521.2,
        "bbox": [-46.8, -24.0, -46.3, -23.3],
        "label_point": [-46.63, -23.55],
    }
    res_el_mun = mocker.MagicMock()
    res_el_mun.mappings.return_value.all.return_value = [
        {
            "election_id": 1,
            "office": "president",
            "eligible": 1000,
            "attendance": 800,
            "valid_votes": 750,
            "blank_votes": 20,
            "null_votes": 30,
            "turnout_pct": 80.0,
            "blank_null_pct": 6.25,
            "left_share": 0.4667,
            "center_share": 0.1333,
            "right_share": 0.4000,
        }
    ]
    res_cv_mun = mocker.MagicMock()
    res_cv_mun.mappings.return_value.all.return_value = [
        {
            "ballot_name": "CANDIDATO A",
            "party_code": "PT",
            "bloc": "left",
            "votes": 300,
        }
    ]
    res_ind_mun = mocker.MagicMock()
    res_ind_mun.mappings.return_value.all.return_value = [
        {
            "code": "gdp_per_capita",
            "label": "PIB per capita",
            "unit": "R$",
            "ref_year": 2023,
            "value": 85000.0,
            "value_text": None,
            "national_percentile": 0.95,
        }
    ]
    mock_conn.execute.side_effect = [
        res_mun_row,
        res_el_mun,
        res_cv_mun,
        res_ind_mun,
    ]
    detail = repo.get_municipality_detail(3550308, year=2026, round_num=1)
    assert detail["municipality"]["cd_ibge"] == 3550308
    assert "president" in detail["elections"]
    assert len(detail["indicators"]) == 1


def test_api_pydantic_schemas() -> None:
    """Verifies Pydantic response schemas in `territorio.api.schemas`."""
    from territorio.api.schemas import (
        ErrorDetailModel,
        ErrorResponse,
        HealthResponse,
        MunicipalitySearchItem,
        MunicipalitySearchResponse,
    )

    h = HealthResponse(
        status="ok",
        postgis_version="3.5",
        dataset_version=1,
        published_at=None,
        municipality_count=5571,
    )
    assert h.status == "ok"
    sr = MunicipalitySearchResponse(
        items=[
            MunicipalitySearchItem(
                cd_ibge=3550308,
                name="São Paulo",
                uf="SP",
                region="Sudeste",
                bbox=[-46.8, -24.0, -46.3, -23.3],
            )
        ]
    )
    assert len(sr.items) == 1
    er = ErrorResponse(error=ErrorDetailModel(code="ERR", message="msg", details={}))
    assert er.error.code == "ERR"
