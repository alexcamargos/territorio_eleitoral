"""Unit tests for IBGE Pesquisas / IBGE Cidades adapter (Source S6)."""

import numpy as np
import pandas as pd
import pytest
from pytest_mock import MockerFixture

from territorio.domain import HigherIs, ScaleHint, Theme, ValueType
from territorio.etl.reference import IndicatorSpec
from territorio.etl.sources.ibge_pesquisas import (
    IbgePesquisasExtractionError,
    fetch_ibge_pesquisas_indicator,
    parse_pesquisas_payload,
)


def test_parse_pesquisas_payload_converts_ibge6_and_sentinels() -> None:
    """Verifies 6-to-7 digit IBGE mapping and sentinel filtering."""
    master = [3550308, 3304557, 5101837]
    payload = [
        {
            "id": 60041,
            "res": [
                {"localidade": "355030", "res": {"2021": "6.2", "2023": "6.5"}},
                {
                    "localidade": "330455",
                    "res": {"2021": "5.8", "2023": "99999999999998"},
                },
                {"localidade": "510183", "res": {"2023": "-"}},
            ],
        }
    ]
    df = parse_pesquisas_payload(
        payload,
        master_ibge_codes=master,
        ref_year_policy="latest",
        value_type=ValueType.CONTINUOUS,
    )
    by_cd = df.set_index("cd_ibge")
    assert by_cd.loc[3550308, "ref_year"] == 2023
    assert by_cd.loc[3550308, "value"] == pytest.approx(6.5)
    assert np.isnan(by_cd.loc[3304557, "value"])
    assert by_cd.loc[3304557, "missing_reason"] == "sentinela_ibge"
    assert np.isnan(by_cd.loc[5101837, "value"])


def test_parse_pesquisas_payload_categorical_and_unknown_code() -> None:
    """Verifies categorical (`urban_hierarchy`) parsing and unknown locality failure."""
    master = [3550308, 3304557]
    cat_payload = [
        {
            "id": 87529,
            "res": [
                {"localidade": "355030", "res": {"2018": "Grande Metrópole Nacional"}},
                {"localidade": "330455", "res": {"2018": "99999999999999"}},
            ],
        }
    ]
    df = parse_pesquisas_payload(
        cat_payload,
        master_ibge_codes=master,
        ref_year_policy="fixed:2018",
        value_type=ValueType.CATEGORICAL,
    )
    by_cd = df.set_index("cd_ibge")
    assert by_cd.loc[3550308, "value_text"] == "Grande Metrópole Nacional"
    assert pd.isna(by_cd.loc[3304557, "value_text"])
    assert by_cd.loc[3304557, "missing_reason"] == "sentinela_ibge"

    bad_payload = [{"id": 1, "res": [{"localidade": "999999", "res": {"2022": "1.0"}}]}]
    with pytest.raises(IbgePesquisasExtractionError, match="not found in master"):
        parse_pesquisas_payload(bad_payload, master_ibge_codes=master)


def test_fetch_ibge_pesquisas_indicator_batches_by_uf(
    mocker: MockerFixture,
) -> None:
    """Verifies UF batching in `fetch_ibge_pesquisas_indicator`.

    Args:
        mocker: Pytest mocker fixture.
    """
    mock_client = mocker.MagicMock()
    mock_client.get_json.side_effect = [
        (
            [{"id": 60041, "res": [{"localidade": "330455", "res": {"2023": "5.9"}}]}],
            "h1",
        ),
        (
            [{"id": 60041, "res": [{"localidade": "355030", "res": {"2023": "6.4"}}]}],
            "h2",
        ),
    ]
    spec = IndicatorSpec(
        code="ideb_initial",
        label="IDEB",
        description="IDEB",
        theme=Theme.EDUCATION,
        tier=1,
        unit="0-10",
        value_type=ValueType.CONTINUOUS,
        higher_is=HigherIs.BETTER,
        scale_hint=ScaleHint.LINEAR,
        valid_range=(0.0, 10.0),
        adapter="ibge_pesquisas",
        source_params={"survey": 10058, "indicator_id": 60041, "period": "last"},
        source_name="IBGE Cidades",
        source_url="https://cidades.ibge.gov.br",
        license="LAI",
        citation="INEP",
        transform={"sentinel_min": 99999999999990},
        ref_year_policy="latest",
        min_coverage=0.9,
        caveat=None,
        verified=True,
    )
    df, _, sha = fetch_ibge_pesquisas_indicator(
        mock_client,
        spec,
        master_ibge_codes=[3304557, 3550308],
        uf_codes=[33, 35],
    )
    assert len(df) == 2
    assert len(sha) == 64
    assert mock_client.get_json.call_count == 2
