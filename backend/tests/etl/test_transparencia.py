"""Unit tests for Portal da Transparência REST adapter (Source S7)."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from territorio.domain import HigherIs, ScaleHint, Theme, ValueType
from territorio.etl.reference import IndicatorSpec
from territorio.etl.sources.transparencia import (
    TransparenciaConfigurationError,
    compute_rolling_months,
    fetch_transparencia_indicator,
)


def _transp_spec(
    code: str,
    params: dict[str, object],
) -> IndicatorSpec:
    """Helper to build a Portal da Transparência `IndicatorSpec` for testing.

    Args:
        code: Indicator code.
        params: Source parameters dictionary.

    Returns:
        Configured `IndicatorSpec`.
    """
    return IndicatorSpec(
        code=code,
        label="Transp Test",
        description="Test",
        theme=Theme.TRANSFERS,
        tier=1,
        unit="R$",
        value_type=ValueType.CONTINUOUS,
        higher_is=HigherIs.NEUTRAL,
        scale_hint=ScaleHint.LINEAR,
        valid_range=(0.0, 10000.0),
        adapter="transparencia",
        source_params=params,
        source_name="CGU",
        source_url="https://portaldatransparencia.gov.br",
        license="LAI",
        citation="CGU",
        transform=None,
        ref_year_policy="nearest_before_election",
        min_coverage=0.9,
        caveat=None,
        verified=True,
    )


def test_compute_rolling_months_crosses_year_boundary() -> None:
    """Verifies 12-month window calculation ending at `202609`."""
    months = compute_rolling_months("202609", 12)
    assert len(months) == 12
    assert months[0] == "202510"
    assert months[2] == "202512"
    assert months[3] == "202601"
    assert months[-1] == "202609"


def test_fetch_transparencia_requires_api_key(mocker: MockerFixture) -> None:
    """Verifies that a missing API key raises `TransparenciaConfigurationError`.

    Args:
        mocker: Pytest mocker fixture.
    """
    mock_client = mocker.MagicMock()
    spec = _transp_spec(
        "bolsa_familia_pc",
        {
            "endpoint": "novo-bolsa-familia-por-municipio",
            "field": "valor",
            "ref_month": "202609",
            "months": 1,
        },
    )
    with pytest.raises(TransparenciaConfigurationError):
        fetch_transparencia_indicator(
            mock_client, spec, master_ibge_codes=[3550308], api_key=""
        )


def test_fetch_transparencia_checkpoint_resume_and_seasonal_zero(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """Verifies disk checkpoint resume and 12-month seasonal aggregation.

    Args:
        tmp_path: Temporary directory provided by pytest.
        mocker: Pytest mocker fixture.
    """
    mock_client = mocker.MagicMock()
    mock_client.get_json.side_effect = [
        ([{"quantidadeBeneficiados": 10}], "sha1"),
        ([], "sha2"),
    ]
    spec = _transp_spec(
        "garantia_safra_coverage",
        {
            "endpoint": "safra-por-municipio",
            "field": "quantidadeBeneficiados",
            "ref_month": "202609",
            "months": 2,
            "agg": "sum",
            "zero_when_absent": True,
        },
    )
    df1, _, _ = fetch_transparencia_indicator(
        mock_client,
        spec,
        master_ibge_codes=[3550308],
        api_key="secret-token",
        cache_dir=tmp_path,
        resume=True,
    )
    assert df1.loc[0, "value"] == 10.0
    assert mock_client.get_json.call_count == 2

    # Second run with resume=True must read from disk cache without HTTP calls
    df2, _, _ = fetch_transparencia_indicator(
        mock_client,
        spec,
        master_ibge_codes=[3550308],
        api_key="secret-token",
        cache_dir=tmp_path,
        resume=True,
    )
    assert df2.loc[0, "value"] == 10.0
    assert mock_client.get_json.call_count == 2
