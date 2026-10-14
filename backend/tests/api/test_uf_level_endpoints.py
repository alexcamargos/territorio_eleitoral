"""Tests for UF macro level map, indicator, and analysis endpoints."""

from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from territorio.api.main import create_app
from territorio.api.repository import SqlDataRepository


def test_election_map_uf_level(mocker: MockerFixture) -> None:
    """Verifies that `GET /api/v1/elections/.../map?level=uf` passes level to repo.

    Args:
        mocker: Pytest-mock fixture.
    """
    mock_repo = mocker.MagicMock(spec=SqlDataRepository)
    mock_repo.get_dataset_version_id.return_value = 1
    mock_repo.get_election_map.return_value = {
        "election": {"year": 2026, "office": "president", "round": 1},
        "level": "uf",
        "national_summary": {
            "eligible": 150000000,
            "attendance": 120000000,
            "valid_votes": 110000000,
            "abroad_valid_votes": 300000,
            "bloc_shares": {"left": 0.48, "center": 0.05, "right": 0.47},
            "municipalities_won": {"left": 13, "center": 0, "right": 14},
            "ufs_won": {"left": 13, "center": 0, "right": 14},
        },
        "quantiles": {"lr_balance": [-0.2, 0.0, 0.2]},
        "columns": [
            "uf",
            "uf_code",
            "name",
            "left_share",
            "center_share",
            "right_share",
            "lr_balance",
            "leading_bloc",
            "valid_votes",
            "turnout_pct",
            "leading_share",
        ],
        "rows": [
            [
                "SP",
                35,
                "São Paulo",
                0.46,
                0.08,
                0.46,
                0.00,
                "right",
                25000000,
                80.5,
                0.46,
            ],
            ["BA", 29, "Bahia", 0.65, 0.05, 0.30, -0.35, "left", 8000000, 78.2, 0.65],
        ],
    }

    app = create_app(repository=mock_repo)
    client = TestClient(app)

    resp = client.get("/api/v1/elections/2026/president/1/map?level=uf")
    assert resp.status_code == 200
    data = resp.json()
    assert data["level"] == "uf"
    assert "ufs_won" in data["national_summary"]
    assert len(data["rows"]) == 2
    assert data["rows"][0][0] == "SP"
    assert data["rows"][0][1] == 35

    mock_repo.get_election_map.assert_called_once_with(
        2026, "president", 1, uf=None, level="uf"
    )


def test_indicator_map_uf_level(mocker: MockerFixture) -> None:
    """Verifies that `GET /api/v1/indicators/.../map?level=uf` passes level to repo.

    Args:
        mocker: Pytest-mock fixture.
    """
    mock_repo = mocker.MagicMock(spec=SqlDataRepository)
    mock_repo.get_dataset_version_id.return_value = 1
    mock_repo.get_indicator_map.return_value = {
        "indicator": {"code": "gdp_per_capita", "ref_year": 2023},
        "level": "uf",
        "summary": {
            "count_valid": 27,
            "count_missing": 0,
            "min": 15000.0,
            "max": 90000.0,
        },
        "columns": ["uf", "uf_code", "name", "value"],
        "rows": [
            ["SP", 35, "São Paulo", 65000.0],
            ["BA", 29, "Bahia", 24000.0],
        ],
    }

    app = create_app(repository=mock_repo)
    client = TestClient(app)

    resp = client.get("/api/v1/indicators/gdp_per_capita/map?level=uf")
    assert resp.status_code == 200
    data = resp.json()
    assert data["level"] == "uf"
    assert len(data["rows"]) == 2
    assert data["rows"][0][0] == "SP"

    mock_repo.get_indicator_map.assert_called_once_with(
        "gdp_per_capita", ref_year=None, uf=None, level="uf"
    )


def test_analysis_uf_level(mocker: MockerFixture) -> None:
    """Verifies that `GET /api/v1/analysis?...&level=uf` passes level to repository.

    Args:
        mocker: Pytest-mock fixture.
    """
    mock_repo = mocker.MagicMock(spec=SqlDataRepository)
    mock_repo.get_dataset_version_id.return_value = 1
    mock_repo.get_analysis.return_value = {
        "scope": {
            "year": 2026,
            "office": "president",
            "round": 1,
            "bloc": "right",
            "uf": None,
            "level": "uf",
        },
        "indicator": {"code": "gdp_per_capita"},
        "sample": {"total_municipalities": 27, "valid_pairs": 27, "missing_pairs": 0},
        "correlation": {
            "spearman_rho": 0.55,
            "spearman_p": 0.003,
            "pearson_r": 0.52,
            "pearson_p": 0.005,
            "strength": "strong",
            "strength_label": "forte",
            "direction": "positive",
            "direction_label": "positiva",
        },
        "trendline": {
            "model": "linear",
            "points": [[20000.0, 0.35], [70000.0, 0.58]],
        },
        "deciles": [],
        "scatter": {
            "columns": ["uf", "uf_code", "name", "x", "y", "valid_votes", "region"],
            "rows": [
                ["SP", 35, "São Paulo", 65000.0, 0.46, 25000000, "Sudeste"],
                ["BA", 29, "Bahia", 24000.0, 0.30, 8000000, "Nordeste"],
            ],
        },
        "insights": [],
    }

    app = create_app(repository=mock_repo)
    client = TestClient(app)

    resp = client.get("/api/v1/analysis?indicator=gdp_per_capita&level=uf")
    assert resp.status_code == 200
    data = resp.json()
    assert data["scope"]["level"] == "uf"
    assert data["sample"]["total_municipalities"] == 27
    assert data["scatter"]["columns"][0] == "uf"

    mock_repo.get_analysis.assert_called_once_with(
        year=2026,
        office_str="president",
        round_num=1,
        indicator_code="gdp_per_capita",
        bloc_str="right",
        uf=None,
        level="uf",
    )


def test_sql_repo_get_election_map_uf_quantiles(mocker: MockerFixture) -> None:
    """Verifies that UF election map computes center quantiles.

    Args:
        mocker: Pytest mocker fixture.
    """
    mock_engine = mocker.MagicMock()
    mock_conn = mocker.MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn

    repo = SqlDataRepository(mock_engine)

    res_uf = mocker.MagicMock()
    res_uf.mappings.return_value.all.return_value = [
        {
            "uf": "SP",
            "eligible": 1000,
            "attendance": 800,
            "valid_votes": 750,
            "left_votes": 300,
            "center_votes": 150,
            "right_votes": 300,
        },
        {
            "uf": "RJ",
            "eligible": 800,
            "attendance": 600,
            "valid_votes": 500,
            "left_votes": 200,
            "center_votes": 50,
            "right_votes": 250,
        },
    ]
    res_abroad = mocker.MagicMock()
    res_abroad.scalar.return_value = 1000
    mock_conn.execute.side_effect = [res_uf, res_abroad]

    el_map = repo.get_election_map(2026, "president", 1, level="uf")
    assert el_map["level"] == "uf"
    assert "center_share" in el_map["quantiles"]
    assert len(el_map["quantiles"]["center_share"]) == 5
