"""Unit tests for indicator transformation, coverage exceptions, and derived math."""

import numpy as np
import pandas as pd
import pytest

from territorio.domain import HigherIs, ScaleHint, Theme, ValueType
from territorio.etl.reference import CoverageExceptionRule, IndicatorSpec
from territorio.etl.transform.indicators import (
    IndicatorCoverageError,
    IndicatorTransformError,
    compute_derived_indicator,
    evaluate_arithmetic_expr,
    finalize_indicator_dataframe,
    parse_ibge_numeric_value,
    resolve_ref_year,
)


def _make_spec(
    code: str = "test_ind",
    *,
    adapter: str = "sidra",
    value_type: ValueType = ValueType.CONTINUOUS,
    valid_range: tuple[float, float] | None = (0.0, 1000.0),
    transform: dict[str, object] | None = None,
    source_params: dict[str, object] | None = None,
    ref_year_policy: str = "fixed:2022",
    min_coverage: float = 0.8,
) -> IndicatorSpec:
    """Helper to construct an `IndicatorSpec` for unit testing.

    Args:
        code: Indicator code.
        adapter: Adapter name.
        value_type: Value type enum.
        valid_range: Optional `(min_val, max_val)` bounds.
        transform: Optional transform dictionary.
        source_params: Optional source parameters dictionary.
        ref_year_policy: Reference year selection policy.
        min_coverage: Minimum required coverage ratio.

    Returns:
        Configured `IndicatorSpec` instance.
    """
    return IndicatorSpec(
        code=code,
        label="Indicador Teste",
        description="Descrição de teste",
        theme=Theme.ECONOMY,
        tier=1,
        unit="R$",
        value_type=value_type,
        higher_is=HigherIs.NEUTRAL,
        scale_hint=ScaleHint.LINEAR,
        valid_range=valid_range,
        adapter=adapter,
        source_params=source_params or {},
        source_name="Fonte Teste",
        source_url="https://example.org",
        license="LAI",
        citation="Citação",
        transform=transform,
        ref_year_policy=ref_year_policy,
        min_coverage=min_coverage,
        caveat=None,
        verified=True,
    )


def test_parse_ibge_numeric_value_handles_conventions_and_sentinels() -> None:
    """Verifies parsing of Brazilian decimals, IBGE signs, and sentinel codes."""
    assert parse_ibge_numeric_value("1.234,56") == (1234.56, None)
    assert parse_ibge_numeric_value("-") == (None, "zero_absoluto_ou_nao_aplicavel")
    assert parse_ibge_numeric_value("X") == (None, "sigilo_estatistico")
    assert parse_ibge_numeric_value("..") == (None, "ausente_na_fonte")
    assert parse_ibge_numeric_value(99999999999998, sentinel_min=99999999999990) == (
        None,
        "sentinela_ibge",
    )


def test_resolve_ref_year_policies() -> None:
    """Verifies `fixed:YYYY`, `latest`, and `nearest_before_election` policies."""
    assert resolve_ref_year("fixed:2022", [2020, 2024]) == 2022
    assert resolve_ref_year("latest", [2021, 2024, 2023]) == 2024
    assert resolve_ref_year("nearest_before_election", [2024, 2026, 2027]) == 2026
    with pytest.raises(IndicatorTransformError):
        resolve_ref_year("unknown_policy", [2022])


def test_finalize_indicator_multiply_per_capita_and_coverage_exceptions() -> None:
    """Verifies `multiply`, `per_capita`, and `coverage_exceptions` stamping."""
    master = [3550308, 3304557, 5101837]
    raw_df = pd.DataFrame(
        {
            "cd_ibge": [3550308, 3304557],
            "value": [100.0, 200.0],
            "ref_year": [2022, 2022],
        }
    )
    spec = _make_spec(
        "gdp_per_capita",
        valid_range=(1.0, 100000.0),
        transform={
            "multiply": 1000,
            "per_capita": {"population": "population_estimate", "same_year": True},
        },
        min_coverage=0.99,
    )
    exc = (
        CoverageExceptionRule(
            cd_ibge=5101837,
            name="Boa Esperança do Norte",
            uf="MT",
            missing_reason="municipio_inexistente_no_periodo",
            applies_to_ref_years_before=2025,
        ),
    )
    denom = {3550308: 100.0, 3304557: 50.0}

    final_df, issues = finalize_indicator_dataframe(
        raw_df,
        spec,
        master_ibge_codes=master,
        coverage_exceptions=exc,
        denominator_by_ibge=denom,
    )
    by_cd = final_df.set_index("cd_ibge")
    assert by_cd.loc[3550308, "value"] == pytest.approx(1000.0)
    assert by_cd.loc[3304557, "value"] == pytest.approx(4000.0)
    assert np.isnan(by_cd.loc[5101837, "value"])
    assert by_cd.loc[5101837, "missing_reason"] == "municipio_inexistente_no_periodo"
    assert len(issues) == 1
    assert issues[0].severity == "info"


def test_finalize_indicator_rejects_out_of_range_and_low_coverage() -> None:
    """Verifies that values outside `valid_range` or below `min_coverage` fail."""
    master = [3550308, 3304557]
    bad_range_df = pd.DataFrame(
        {"cd_ibge": [3550308, 3304557], "value": [50.0, 5000.0]}
    )
    spec = _make_spec("bounded", valid_range=(0.0, 100.0), min_coverage=0.5)
    with pytest.raises(IndicatorTransformError, match="outside valid_range"):
        finalize_indicator_dataframe(bad_range_df, spec, master_ibge_codes=master)

    low_cov_df = pd.DataFrame({"cd_ibge": [3550308], "value": [50.0]})
    strict_spec = _make_spec("strict", valid_range=(0.0, 100.0), min_coverage=0.9)
    with pytest.raises(IndicatorCoverageError, match="below min_coverage"):
        finalize_indicator_dataframe(low_cov_df, strict_spec, master_ibge_codes=master)


def test_compute_derived_indicator_from_inputs_and_election_summary() -> None:
    """Verifies safe AST evaluation for both indicator inputs and election_summary."""
    master = [3550308, 3304557]
    pop_df = pd.DataFrame(
        {"cd_ibge": master, "value": [1000.0, 2000.0], "ref_year": [2022, 2022]}
    )
    area_df = pd.DataFrame(
        {"cd_ibge": master, "value": [10.0, 200.0], "ref_year": [2025, 2025]}
    )
    density_spec = _make_spec(
        "density",
        adapter="derived",
        valid_range=(0.01, 10000.0),
        source_params={
            "expr": "population / area_km2",
            "inputs": {"population": "population", "area_km2": "area_km2"},
        },
        ref_year_policy="fixed:2022",
    )
    df_dens, _ = compute_derived_indicator(
        density_spec,
        master_ibge_codes=master,
        indicator_frames={"population": pop_df, "area_km2": area_df},
    )
    assert df_dens.set_index("cd_ibge").loc[master, "value"].tolist() == [100.0, 10.0]

    turnout_df = pd.DataFrame(
        {
            "cd_ibge": master,
            "round": [1, 1],
            "tse_cd_cargo": [1, 1],
            "eligible_voters": [1000, 2000],
            "turnout": [800, 1500],
            "abstention": [200, 500],
            "valid_votes": [750, 1400],
            "blank_votes": [20, 40],
            "null_votes": [30, 60],
        }
    )
    turnout_spec = _make_spec(
        "turnout_pct",
        adapter="derived",
        valid_range=(0.0, 100.0),
        source_params={
            "table": "election_summary",
            "office": "president",
            "round": 1,
            "expr": "turnout / eligible_voters * 100",
        },
        ref_year_policy="fixed:2026",
    )
    df_turn, _ = compute_derived_indicator(
        turnout_spec,
        master_ibge_codes=master,
        election_turnout_df=turnout_df,
    )
    assert df_turn.set_index("cd_ibge").loc[master, "value"].tolist() == [80.0, 75.0]

    with pytest.raises(IndicatorTransformError):
        evaluate_arithmetic_expr(
            "__import__('os').system('echo bad')",
            {"population": pd.Series([1.0], index=[3550308])},
        )
