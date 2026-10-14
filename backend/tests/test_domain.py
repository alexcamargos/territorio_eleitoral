"""Unit tests for domain enums, value objects, and UF metadata."""

import pytest

from territorio.domain import (
    UF_BY_CODE,
    UF_BY_SIGLA,
    Bloc,
    CorrelationDirection,
    CorrelationStrength,
    DecileStat,
    InsightCard,
    Office,
    StepResult,
    Theme,
    classify_bloc_from_score,
)


def test_office_labels_and_majoritarian_flags() -> None:
    """Verifies electoral office labels and system classifications."""
    assert Office.PRESIDENT.label_pt == "Presidente"
    assert Office.STATE_OR_DISTRICT_DEPUTY.label_pt == "Deputado Estadual / Distrital"
    assert Office.PRESIDENT.is_majoritarian is True
    assert Office.SENATOR.is_majoritarian is True
    assert Office.FEDERAL_DEPUTY.is_majoritarian is False


@pytest.mark.parametrize(
    ("score", "expected_bloc"),
    [
        (0.0, Bloc.LEFT),
        (2.97, Bloc.LEFT),
        (3.99, Bloc.LEFT),
        (4.00, Bloc.CENTER),
        (5.50, Bloc.CENTER),
        (6.00, Bloc.CENTER),
        (6.01, Bloc.RIGHT),
        (7.78, Bloc.RIGHT),
        (10.00, Bloc.RIGHT),
    ],
)
def test_classify_bloc_from_score(score: float, expected_bloc: Bloc) -> None:
    """Verifies deterministic mapping from ideological score (0-10) to Bloc.

    Args:
        score: Continuous ideological score between 0 and 10.
        expected_bloc: Expected discrete ideological bloc.
    """
    assert classify_bloc_from_score(score) == expected_bloc


def test_classify_bloc_from_score_out_of_bounds_raises() -> None:
    """Verifies that scores outside [0, 10] raise ValueError."""
    with pytest.raises(ValueError, match=r"between 0\.0 and 10\.0"):
        classify_bloc_from_score(-0.1)
    with pytest.raises(ValueError, match=r"between 0\.0 and 10\.0"):
        classify_bloc_from_score(10.01)


def test_uf_metadata_completeness() -> None:
    """Verifies that all 27 Brazilian UFs are present with valid IBGE codes."""
    assert len(UF_BY_SIGLA) == 27
    assert len(UF_BY_CODE) == 27
    assert UF_BY_SIGLA["SP"].uf_code == 35
    assert UF_BY_SIGLA["SP"].region == "Sudeste"
    assert UF_BY_SIGLA["SP"].capital_cd_ibge == 3550308
    assert UF_BY_SIGLA["DF"].uf_code == 53
    assert UF_BY_SIGLA["DF"].capital_cd_ibge == 5300108


def test_value_objects_are_frozen_dataclasses() -> None:
    """Verifies that domain value objects are immutable."""
    step = StepResult(step="reference", rows_in=10, rows_out=10, dropped={})
    assert step.step == "reference"
    with pytest.raises(AttributeError):
        step.rows_in = 20  # type: ignore[misc]

    decile = DecileStat(
        decile=1,
        municipality_count=557,
        indicator_min=10.0,
        indicator_max=20.0,
        indicator_median=15.0,
        valid_votes=100000,
        bloc_votes=45000,
        weighted_share=0.45,
        unweighted_mean_share=0.46,
    )
    assert decile.weighted_share == 0.45

    card = InsightCard(
        template_id="ecological_reminder",
        severity="caveat",
        title="Nota metodológica",
        text="Padrões entre municípios.",
        params={},
    )
    assert card.template_id == "ecological_reminder"
    assert Theme.ECONOMY.label_pt == "Economia e renda"
    assert CorrelationStrength.STRONG.label_pt == "forte"
    assert CorrelationDirection.NEGATIVE.label_pt == "negativa"
