"""Unit tests for deterministic narrative insights and guards G1-G3."""

from territorio.analytics.insights import (
    CategoryShareSummary,
    build_macro_overview_card,
    generate_analysis_insights,
)
from territorio.domain import (
    Bloc,
    CorrelationDirection,
    CorrelationStats,
    CorrelationStrength,
    DecileStat,
    Office,
    QuintileExtremesContrast,
    ValueType,
)

FORBIDDEN_INDIVIDUAL_TERMS = ("eleitores pobres", "pessoas votam", "moradores votaram")


def _sample_deciles() -> list[DecileStat]:
    """Builds 10 synthetic `DecileStat` objects for insight testing.

    Returns:
        List of 10 `DecileStat` instances.
    """
    return [
        DecileStat(
            decile=d,
            municipality_count=557,
            indicator_min=float(d * 100),
            indicator_max=float((d + 1) * 100),
            indicator_median=float(d * 100 + 50),
            valid_votes=1_000_000,
            bloc_votes=int(1_000_000 * (0.30 + d * 0.03)),
            weighted_share=0.30 + d * 0.03,
            unweighted_mean_share=0.28 + d * 0.03,
        )
        for d in range(1, 11)
    ]


def test_build_macro_overview_card_exact_template() -> None:
    """Verifies exact Portuguese rendering of `macro_overview`."""
    card = build_macro_overview_card(
        year=2026,
        round_num=1,
        office=Office.PRESIDENT,
        leading_bloc=Bloc.RIGHT,
        national_share=0.512,
        municipalities_won=3120,
        total_municipalities=5571,
    )
    assert card.template_id == "macro_overview"
    assert "51,2%" in card.text
    assert "3.120" in card.text
    assert "5.571" in card.text
    for forbidden in FORBIDDEN_INDIVIDUAL_TERMS:
        assert forbidden not in card.text.lower()


def test_guard_g1_min_sample_returns_only_insufficient_data() -> None:
    """Verifies Guard G1 (`n_valid < 30`) suppresses correlation and decile cards."""
    cards = generate_analysis_insights(
        year=2026,
        round_num=1,
        office=Office.GOVERNOR,
        bloc=Bloc.LEFT,
        indicator_label="PIB per capita",
        indicator_unit="R$",
        value_type=ValueType.CONTINUOUS,
        ref_year=2023,
        source_name="IBGE",
        caveat=None,
        n_valid=15,
        n_scope_total=15,
    )
    assert len(cards) == 1
    assert cards[0].template_id == "insufficient_data"
    assert "15" in cards[0].text


def test_continuous_insights_with_g2_low_coverage_and_temporal_caveat() -> None:
    """Verifies `decile_top_vs_bottom`, `correlation_summary`, G2, and caveats."""
    corr = CorrelationStats(
        spearman_rho=0.64,
        spearman_p=0.0002,
        pearson_r=0.59,
        pearson_p=0.0005,
        strength=CorrelationStrength.STRONG,
        direction=CorrelationDirection.POSITIVE,
        n_valid=872,
    )
    cards = generate_analysis_insights(
        year=2026,
        round_num=1,
        office=Office.PRESIDENT,
        bloc=Bloc.LEFT,
        indicator_label="População em áreas de risco",
        indicator_unit="%",
        value_type=ValueType.CONTINUOUS,
        ref_year=2010,
        source_name="IBGE / CEMADEN",
        caveat="Apenas 872 municípios monitorados.",
        n_valid=872,
        n_scope_total=5571,
        correlation=corr,
        deciles=_sample_deciles(),
    )
    ids = [c.template_id for c in cards]
    assert ids == [
        "decile_top_vs_bottom",
        "correlation_summary",
        "low_coverage_warning",
        "temporal_caveat",
        "ecological_reminder",
    ]
    assert "+27,0 p.p." in cards[0].text
    assert "+0,64" in cards[1].text
    assert "< 0,001" in cards[1].text
    for c in cards:
        for forbidden in FORBIDDEN_INDIVIDUAL_TERMS:
            assert forbidden not in c.text.lower()


def test_guard_g3_categorical_uses_category_breakdown() -> None:
    """Verifies Guard G3 (`value_type != continuous`) renders `category_breakdown`."""
    cards = generate_analysis_insights(
        year=2026,
        round_num=1,
        office=Office.PRESIDENT,
        bloc=Bloc.RIGHT,
        indicator_label="Nota CAPAG",
        indicator_unit="ordinal A>B>C>D",
        value_type=ValueType.ORDINAL,
        ref_year=2025,
        source_name="Tesouro Nacional",
        caveat=None,
        n_valid=5000,
        n_scope_total=5571,
        category_summaries=[
            CategoryShareSummary("A+", 300, 0.58),
            CategoryShareSummary("C", 1800, 0.44),
        ],
    )
    ids = [c.template_id for c in cards]
    assert "category_breakdown" in ids
    assert "decile_top_vs_bottom" not in ids
    assert "correlation_summary" not in ids


def test_extremes_two_brazils_insight_card() -> None:
    """Verifies `extremes_two_brazils` card with tipping point and ecological rules."""
    contrast = QuintileExtremesContrast(
        bottom_quintile_share=0.33,
        top_quintile_share=0.62,
        diff_pp=29.0,
        bottom_indicator_range=(10.0, 50.0),
        top_indicator_range=(200.0, 800.0),
        bottom_municipality_count=1114,
        top_municipality_count=1114,
        tipping_point_decile=6,
        tipping_point_threshold=120.0,
    )
    cards = generate_analysis_insights(
        year=2026,
        round_num=1,
        office=Office.PRESIDENT,
        bloc=Bloc.RIGHT,
        indicator_label="PIB per capita",
        indicator_unit="R$",
        value_type=ValueType.CONTINUOUS,
        ref_year=2023,
        source_name="IBGE",
        caveat=None,
        n_valid=5570,
        n_scope_total=5571,
        deciles=_sample_deciles(),
        extremes_contrast=contrast,
    )
    ids = [c.template_id for c in cards]
    assert "extremes_two_brazils" in ids
    two_brazils_card = next(c for c in cards if c.template_id == "extremes_two_brazils")
    assert "62,0%" in two_brazils_card.text
    assert "33,0%" in two_brazils_card.text
    assert "+29,0 p.p." in two_brazils_card.text
    assert "Decil D6" in two_brazils_card.text
    for forbidden in FORBIDDEN_INDIVIDUAL_TERMS:
        assert forbidden not in two_brazils_card.text.lower()
