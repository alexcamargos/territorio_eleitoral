"""Unit tests for IBGE SIDRA REST adapter (Source S5)."""

import numpy as np
from pytest_mock import MockerFixture

from territorio.domain import HigherIs, ScaleHint, Theme, ValueType
from territorio.etl.reference import IndicatorSpec
from territorio.etl.sources.ibge_sidra import (
    build_sidra_url,
    fetch_sidra_indicator,
    parse_sidra_payload,
)


def _sidra_spec(
    code: str,
    params: dict[str, object],
    transform: dict[str, object] | None = None,
) -> IndicatorSpec:
    """Helper to build a SIDRA `IndicatorSpec` for testing.

    Args:
        code: Indicator code.
        params: SIDRA source parameters.
        transform: Optional transform dictionary.

    Returns:
        Configured `IndicatorSpec`.
    """
    return IndicatorSpec(
        code=code,
        label="SIDRA Test",
        description="Test",
        theme=Theme.SOCIAL,
        tier=1,
        unit="%",
        value_type=ValueType.CONTINUOUS,
        higher_is=HigherIs.NEUTRAL,
        scale_hint=ScaleHint.LINEAR,
        valid_range=(0.0, 100.0),
        adapter="sidra",
        source_params=params,
        source_name="IBGE SIDRA",
        source_url="https://sidra.ibge.gov.br",
        license="LAI",
        citation="IBGE",
        transform=transform,
        ref_year_policy="fixed:2022",
        min_coverage=0.5,
        caveat=None,
        verified=True,
    )


def test_build_sidra_url_with_classifications() -> None:
    """Verifies SIDRA URL construction with table, variable, period, and categories."""
    url = build_sidra_url(
        table=9605,
        variable=1000093,
        period="2022",
        classifications={"c86": "2777,2779"},
    )
    assert (
        url
        == "https://apisidra.ibge.gov.br/values/t/9605/n6/all/v/1000093/p/2022/c86/2777,2779"
    )


def test_parse_sidra_payload_with_sum_aggregation_and_missing_signs() -> None:
    """Verifies header skipping, category summing (`agg: 'sum'`), and `'-'` handling."""
    payload = [
        {"D1C": "Município (Código)", "D3C": "Ano", "V": "Valor"},
        {"D1C": "3550308", "D3C": "2022", "V": "12.5"},
        {"D1C": "3550308", "D3C": "2022", "V": "30.5"},
        {"D1C": "5101837", "D3C": "2022", "V": "..."},
    ]
    df = parse_sidra_payload(payload, agg="sum")
    by_cd = df.set_index("cd_ibge")
    assert by_cd.loc[3550308, "value"] == 43.0
    assert np.isnan(by_cd.loc[5101837, "value"])
    assert by_cd.loc[5101837, "missing_reason"] == "ausente_na_fonte"


def test_fetch_sidra_indicator_with_denominator(mocker: MockerFixture) -> None:
    """Verifies two-table SIDRA ratio extraction (`favela_households_pct`).

    Args:
        mocker: Pytest mocker fixture.
    """
    mock_client = mocker.MagicMock()
    num_payload = [
        {"D1C": "Município (Código)", "D3C": "Ano", "V": "Valor"},
        {"D1C": "3550308", "D3C": "2022", "V": "250"},
        {"D1C": "3304557", "D3C": "2022", "V": "-"},
    ]
    denom_payload = [
        {"D1C": "Município (Código)", "D3C": "Ano", "V": "Valor"},
        {"D1C": "3550308", "D3C": "2022", "V": "1000"},
        {"D1C": "3304557", "D3C": "2022", "V": "2000"},
    ]
    mock_client.get_json.side_effect = [
        (num_payload, "sha_num"),
        (denom_payload, "sha_denom"),
    ]

    spec = _sidra_spec(
        "favela_households_pct",
        params={
            "table": 10172,
            "variable": 13548,
            "period": "2022",
            "denominator": {"table": 9922, "variable": 381, "period": "2022"},
        },
        transform={"multiply": 100},
    )
    df, _, sha = fetch_sidra_indicator(mock_client, spec)
    assert sha == "sha_num"
    by_cd = df.set_index("cd_ibge")
    assert by_cd.loc[3550308, "value"] == 0.25
    assert np.isnan(by_cd.loc[3304557, "value"])
