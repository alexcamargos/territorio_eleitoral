"""Unit tests for reference YAML catalogs."""

from pathlib import Path

import pandas as pd
import pytest

from territorio.etl.reference import (
    ReferenceCatalogError,
    load_indicators_catalog,
    load_offices_catalog,
    load_party_ideology_catalog,
    normalize_party_code,
)
from territorio.etl.schemas import IndicatorValueSchema, validate_dataframe


def test_load_party_ideology_catalog_validates_real_yaml(project_root: Path) -> None:
    """Verifies that `data/reference/party_ideology.yaml` is valid and complete.

    Args:
        project_root: Repository root fixture.
    """
    catalog = load_party_ideology_catalog(
        project_root / "data" / "reference" / "party_ideology.yaml"
    )
    active_2026 = catalog.active_parties_for_year(2026)
    assert len(active_2026) == 30
    assert "PT" in active_2026
    assert "PL" in active_2026
    assert "UNIAO" in active_2026
    assert "PRD" in active_2026
    assert "MISSAO" in active_2026
    assert "DEMOCRATA" in active_2026

    # Check normalization of aliases and accents
    assert normalize_party_code("PC do B", catalog.aliases) == "PCDOB"
    assert normalize_party_code("UNIÃO", catalog.aliases) == "UNIAO"
    assert normalize_party_code("MISSÃO", catalog.aliases) == "MISSAO"
    assert normalize_party_code("PMB", catalog.aliases) == "DEMOCRATA"


def test_load_party_ideology_catalog_rejects_inconsistent_bloc(
    tmp_path: Path,
) -> None:
    """Verifies that a party whose `bloc` contradicts its `score` raises an error.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    bad_yaml = tmp_path / "bad_party.yaml"
    bad_yaml.write_text(
        """
schema_version: 1
thresholds:
  left_max_exclusive: 4.00
  right_min_exclusive: 6.00
aliases: {}
parties:
  - party_code: PT
    number: 13
    name: Partido dos Trabalhadores
    score: 2.97
    bloc: right
    valid_from: 1980
    valid_to: null
    method: survey
    source: "Test"
""",
        encoding="utf-8",
    )
    with pytest.raises(ReferenceCatalogError, match="PT"):
        load_party_ideology_catalog(bad_yaml)


def test_load_indicators_catalog_validates_real_yaml(project_root: Path) -> None:
    """Verifies that `data/reference/indicators.yaml` passes all schema rules.

    Args:
        project_root: Repository root fixture.
    """
    catalog = load_indicators_catalog(
        project_root / "data" / "reference" / "indicators.yaml"
    )
    assert len(catalog.indicators) == 73
    tier1 = [ind for ind in catalog.indicators.values() if ind.tier == 1]
    tier2 = [ind for ind in catalog.indicators.values() if ind.tier == 2]
    assert len(tier1) == 47
    assert len(tier2) == 26
    assert all(len(ind.label) <= 32 for ind in catalog.indicators.values())
    assert len(catalog.coverage_exceptions) == 3


def test_load_offices_catalog_validates_real_yaml(project_root: Path) -> None:
    """Verifies that `data/reference/offices.yaml` loads all 8 2026 election entries.

    Args:
        project_root: Repository root fixture.
    """
    offices = load_offices_catalog(project_root / "data" / "reference" / "offices.yaml")
    assert len(offices) == 8
    senator = next(o for o in offices if o.office == "senator")
    assert senator.votes_per_voter == 2


def test_pandera_indicator_value_schema_validation() -> None:
    """Verifies Pandera schema validation on standardized indicator rows."""
    valid_df = pd.DataFrame(
        {
            "cd_ibge": [3550308, 5101837],
            "ref_year": [2023, 2023],
            "value": [89420.5, float("nan")],
            "value_text": [None, None],
            "missing_reason": [None, "municipio_inexistente_no_periodo"],
        }
    )
    validated = validate_dataframe(valid_df, IndicatorValueSchema)
    assert len(validated) == 2
