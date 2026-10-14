"""Unit tests for SICONFI DCA adapter (Source S8)."""

from pathlib import Path

import numpy as np
import pytest
from pytest_mock import MockerFixture

from territorio.domain import HigherIs, ScaleHint, Theme, ValueType
from territorio.etl.reference import IndicatorSpec
from territorio.etl.sources.siconfi import (
    fetch_siconfi_indicator,
    parse_siconfi_municipality_items,
)


def test_parse_siconfi_ratio_and_function_prefix() -> None:
    """Verifies ratio accounts (`Anexo I-C`) and prefix filtering (`Anexo I-E`)."""
    anexo_ic = [
        {
            "coluna": "Receitas Brutas Realizadas",
            "cod_conta": "RO1.1.0.0.00.0.0",
            "conta": "1.1.0.0.00.0.0 - Impostos, Taxas e Contribuições",
            "valor": 250.0,
        },
        {
            "coluna": "Receitas Brutas Realizadas",
            "cod_conta": "RO1.0.0.0.00.0.0",
            "conta": "1.0.0.0.00.0.0 - Receitas Correntes",
            "valor": 1000.0,
        },
    ]
    ratio, reason = parse_siconfi_municipality_items(
        anexo_ic,
        coluna="Receitas Brutas Realizadas",
        numerator_cod_conta="RO1.1.0.0.00.0.0",
        denominator_cod_conta="RO1.0.0.0.00.0.0",
    )
    assert ratio == pytest.approx(0.25)
    assert reason is None

    anexo_ie = [
        {
            "coluna": "Despesas Empenhadas",
            "cod_conta": "TotalDespesas",
            "conta": "10 - Saúde",
            "valor": 500000.0,
        },
        {
            "coluna": "Despesas Empenhadas",
            "cod_conta": "TotalDespesas",
            "conta": "12 - Educação",
            "valor": 700000.0,
        },
    ]
    health_val, _ = parse_siconfi_municipality_items(
        anexo_ie,
        coluna="Despesas Empenhadas",
        cod_conta="TotalDespesas",
        conta_prefix="10 - Saúde",
    )
    assert health_val == pytest.approx(500000.0)

    empty_val, empty_reason = parse_siconfi_municipality_items(
        [], coluna="Receitas Brutas Realizadas", cod_conta="RO1.0.0.0.00.0.0"
    )
    assert empty_val is None
    assert empty_reason == "nao_declarado"


def test_fetch_siconfi_indicator_caches_by_municipality(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """Verifies SICONFI DCA extraction and disk checkpoint reuse.

    Args:
        tmp_path: Temporary directory provided by pytest.
        mocker: Pytest mocker fixture.
    """
    mock_client = mocker.MagicMock()
    mock_client.get_json.side_effect = [
        (
            {
                "items": [
                    {
                        "coluna": "Receitas Brutas Realizadas",
                        "cod_conta": "RO1.0.0.0.00.0.0",
                        "valor": 10000.0,
                    }
                ]
            },
            "sha_sp",
        ),
        ({"items": []}, "sha_df"),
    ]
    spec = IndicatorSpec(
        code="revenue_pc",
        label="Receita",
        description="Receita",
        theme=Theme.FISCAL,
        tier=1,
        unit="R$",
        value_type=ValueType.CONTINUOUS,
        higher_is=HigherIs.NEUTRAL,
        scale_hint=ScaleHint.LOG,
        valid_range=(100.0, 100000.0),
        adapter="siconfi",
        source_params={
            "anexo": "DCA-Anexo I-C",
            "coluna": "Receitas Brutas Realizadas",
            "cod_conta": "RO1.0.0.0.00.0.0",
        },
        source_name="SICONFI",
        source_url="https://siconfi.tesouro.gov.br",
        license="LAI",
        citation="STN",
        transform=None,
        ref_year_policy="latest",
        min_coverage=0.5,
        caveat=None,
        verified=True,
    )
    df, _, _ = fetch_siconfi_indicator(
        mock_client,
        spec,
        master_ibge_codes=[3550308, 5300108],
        ref_year=2024,
        cache_dir=tmp_path,
        resume=True,
    )
    by_cd = df.set_index("cd_ibge")
    assert by_cd.loc[3550308, "value"] == 10000.0
    assert np.isnan(by_cd.loc[5300108, "value"])
    assert by_cd.loc[5300108, "missing_reason"] == "nao_declarado"
