"""Unit tests for TSE-to-IBGE crosswalk building, validation (X1-X6), and mapping."""

import pandas as pd
import pytest

from territorio.etl.crosswalk import (
    CrosswalkError,
    build_crosswalk_dataframe,
    map_tse_to_ibge,
    normalize_municipality_name,
    validate_crosswalk,
)


def _sample_master() -> pd.DataFrame:
    """Returns a 3-municipality IBGE master DataFrame for testing.

    Returns:
        DataFrame with `cd_ibge`, `name`, and `uf`.
    """
    return pd.DataFrame(
        {
            "cd_ibge": [1200013, 3550308, 5101837],
            "name": ["Acrelândia", "São Paulo", "Boa Esperança do Norte"],
            "uf": ["AC", "SP", "MT"],
        }
    )


def _sample_crosswalk() -> pd.DataFrame:
    """Returns a valid 3-municipality crosswalk DataFrame.

    Returns:
        DataFrame with `cd_tse`, `cd_ibge`, `uf`, `name_tse`, `name_ibge`, `source`.
    """
    return pd.DataFrame(
        {
            "cd_tse": [1120, 71072, 73709],
            "cd_ibge": [1200013, 3550308, 5101837],
            "uf": ["AC", "SP", "MT"],
            "name_tse": ["ACRELÂNDIA", "SÃO PAULO", "BOA ESPERANÇA DO NORTE"],
            "name_ibge": ["Acrelândia", "São Paulo", "Boa Esperança do Norte"],
            "source": [
                "betafcc@master",
                "betafcc@master",
                "manual:instalado_2025",
            ],
        }
    )


def _sample_tse_observed() -> pd.DataFrame:
    """Returns observed TSE municipality codes matching `_sample_crosswalk`.

    Returns:
        DataFrame with `cd_tse`, `uf`, `name_tse`.
    """
    return pd.DataFrame(
        {
            "cd_tse": [1120, 71072, 73709],
            "uf": ["AC", "SP", "MT"],
            "name_tse": ["ACRELÂNDIA", "SÃO PAULO", "BOA ESPERANÇA DO NORTE"],
        }
    )


def test_normalize_municipality_name_strips_diacritics_and_punctuation() -> None:
    """Verifies normalization for rule X6 name similarity."""
    assert (
        normalize_municipality_name("Olho-d'Água do Borges") == "OLHO D AGUA DO BORGES"
    )
    assert normalize_municipality_name("  São   Paulo ") == "SAO PAULO"


def test_validate_crosswalk_passes_all_rules() -> None:
    """Verifies that a complete 1:1 crosswalk passes X1-X6 with zero warnings."""
    report = validate_crosswalk(
        _sample_crosswalk(),
        _sample_master(),
        _sample_tse_observed(),
    )
    assert report.total_pairs == 3
    assert report.name_warnings == []


def test_validate_crosswalk_rule_x1_duplicate_cd_tse_raises() -> None:
    """Verifies that duplicate `cd_tse` violates blocking rule X1."""
    xw = _sample_crosswalk()
    xw.loc[1, "cd_tse"] = 1120
    with pytest.raises(CrosswalkError, match="X1"):
        validate_crosswalk(xw, _sample_master(), _sample_tse_observed())


def test_validate_crosswalk_rule_x2_duplicate_cd_ibge_raises() -> None:
    """Verifies that duplicate `cd_ibge` violates blocking rule X2."""
    xw = _sample_crosswalk()
    xw.loc[1, "cd_ibge"] = 1200013
    with pytest.raises(CrosswalkError, match="X2"):
        validate_crosswalk(xw, _sample_master(), _sample_tse_observed())


def test_validate_crosswalk_rule_x3_missing_master_municipality_raises() -> None:
    """Verifies that a crosswalk missing an IBGE municipality violates rule X3."""
    xw = _sample_crosswalk().iloc[:2].copy()
    with pytest.raises(CrosswalkError, match="X3"):
        validate_crosswalk(xw, _sample_master(), _sample_tse_observed().iloc[:2])


def test_validate_crosswalk_rule_x4_unmapped_tse_code_raises() -> None:
    """Verifies that an observed TSE code absent from the crosswalk violates rule X4."""
    tse_obs = pd.concat(
        [
            _sample_tse_observed(),
            pd.DataFrame(
                {"cd_tse": [99999], "uf": ["SP"], "name_tse": ["MUNICIPIO FANTASMA"]}
            ),
        ],
        ignore_index=True,
    )
    with pytest.raises(CrosswalkError, match="X4"):
        validate_crosswalk(_sample_crosswalk(), _sample_master(), tse_obs)


def test_validate_crosswalk_rule_x5_uf_divergence_raises() -> None:
    """Verifies that a UF mismatch between TSE and IBGE violates rule X5."""
    xw = _sample_crosswalk()
    xw.loc[0, "uf"] = "AM"
    with pytest.raises(CrosswalkError, match="X5"):
        validate_crosswalk(xw, _sample_master(), _sample_tse_observed())


def test_validate_crosswalk_rule_x6_records_name_warning_without_raising() -> None:
    """Verifies that spelling changes below 0.85 similarity produce X6 warnings."""
    xw = _sample_crosswalk()
    xw.loc[0, "name_tse"] = "VILA ANTIGA DO ACRE"
    report = validate_crosswalk(xw, _sample_master(), _sample_tse_observed())
    assert len(report.name_warnings) == 1
    assert report.name_warnings[0]["cd_ibge"] == 1200013


def test_build_crosswalk_dataframe_merges_seed_and_overrides() -> None:
    """Verifies that overrides supplement/replace rows in the community seed."""
    seed_df = pd.DataFrame(
        {
            "codigo_tse": [1120, 71072],
            "uf": ["AC", "SP"],
            "nome_municipio": ["ACRELÂNDIA", "SÃO PAULO"],
            "codigo_ibge": [1200013, 3550308],
        }
    )
    overrides_df = pd.DataFrame(
        {
            "cd_tse": [73709],
            "cd_ibge": [5101837],
            "uf": ["MT"],
            "name_tse": ["BOA ESPERANÇA DO NORTE"],
            "source": ["manual:instalado_2025"],
        }
    )
    built = build_crosswalk_dataframe(seed_df, overrides_df, _sample_master())
    assert len(built) == 3
    assert set(built["cd_ibge"]) == {1200013, 3550308, 5101837}


def test_map_tse_to_ibge_converts_and_raises_on_unmapped() -> None:
    """Verifies `map_tse_to_ibge` conversion and strict failure on unknown TSE codes."""
    xw = _sample_crosswalk()
    votes = pd.DataFrame({"cd_tse": [1120, 71072, 73709], "votes": [10, 20, 30]})
    mapped = map_tse_to_ibge(votes, xw)
    assert "cd_tse" not in mapped.columns
    assert list(mapped["cd_ibge"]) == [1200013, 3550308, 5101837]

    bad_votes = pd.DataFrame({"cd_tse": [1120, 88888], "votes": [10, 5]})
    with pytest.raises(CrosswalkError, match="88888"):
        map_tse_to_ibge(bad_votes, xw)
