"""Deterministic narrative insight generator with safety guards G1-G3."""

from dataclasses import dataclass

from territorio.analytics.formatting import (
    format_indicator_value_pt,
    format_integer_pt,
    format_p_value_pt,
    format_pct_pt,
    format_pp_diff_pt,
    format_rho_pt,
)
from territorio.domain import (
    Bloc,
    CorrelationDirection,
    CorrelationStats,
    CorrelationStrength,
    DecileStat,
    InsightCard,
    Office,
    QuintileExtremesContrast,
    ValueType,
)

MIN_SAMPLE_SIZE_G1 = 30
MIN_COVERAGE_RATIO_G2 = 0.85

STRENGTH_LABELS_PT: dict[CorrelationStrength, str] = {
    CorrelationStrength.NEGLIGIBLE: "desprezível",
    CorrelationStrength.WEAK: "fraca",
    CorrelationStrength.MODERATE: "moderada",
    CorrelationStrength.STRONG: "forte",
    CorrelationStrength.VERY_STRONG: "muito forte",
}

DIRECTION_LABELS_PT: dict[CorrelationDirection, str] = {
    CorrelationDirection.POSITIVE: "positiva",
    CorrelationDirection.NEGATIVE: "negativa",
    CorrelationDirection.NEUTRAL: "neutra",
}


@dataclass(frozen=True, slots=True)
class CategoryShareSummary:
    """Electoral summary for one category of a categorical/ordinal indicator.

    Attributes:
        category: Category label (`value_text`).
        municipality_count: Number of municipalities in this category.
        weighted_share: Vote-weighted bloc share in `[0.0, 1.0]`.
    """

    category: str
    municipality_count: int
    weighted_share: float


def build_macro_overview_card(
    *,
    year: int,
    round_num: int,
    office: Office,
    leading_bloc: Bloc,
    national_share: float,
    municipalities_won: int,
    total_municipalities: int,
) -> InsightCard:
    """Renders the `macro_overview` insight card for Stage 1 and Stage 2 headers.

    Args:
        year: Election year (e.g. 2026).
        round_num: Election round (1 or 2).
        office: Electoral office enum.
        leading_bloc: Leading ideological bloc at the scope level.
        national_share: Vote-weighted share of `leading_bloc` in `[0.0, 1.0]`.
        municipalities_won: Number of municipalities where `leading_bloc` led.
        total_municipalities: Total municipalities in the current scope.

    Returns:
        Rendered `InsightCard` with `template_id == 'macro_overview'`.
    """
    office_label = office.label_pt
    leading_bloc_label = leading_bloc.label_pt.lower()
    share_pct = format_pct_pt(national_share, is_ratio=True)
    mun_won_fmt = format_integer_pt(municipalities_won)
    total_mun_fmt = format_integer_pt(total_municipalities)

    text = (
        f"Em {year} ({round_num}º turno, {office_label}), o bloco de "
        f"**{leading_bloc_label}** somou **{share_pct}** dos votos válidos nos "
        f"municípios brasileiros, liderando em **{mun_won_fmt}** dos "
        f"**{total_mun_fmt}** municípios."
    )
    return InsightCard(
        template_id="macro_overview",
        severity="headline",
        title="Panorama Nacional por Blocos",
        text=text,
        params={
            "year": year,
            "round": round_num,
            "office_label": office_label,
            "leading_bloc_label": leading_bloc_label,
            "national_share_pct": share_pct,
            "municipalities_won": municipalities_won,
            "total_municipalities": total_municipalities,
        },
    )


def build_ecological_reminder_card() -> InsightCard:
    """Renders the mandatory `ecological_reminder` methodological card.

    Returns:
        Rendered `InsightCard` with `template_id == 'ecological_reminder'`.
    """
    return InsightCard(
        template_id="ecological_reminder",
        severity="caveat",
        title="Interpretação Ecológica",
        text=(
            "Estes resultados descrevem padrões agregados **entre municípios** e "
            "não permitem inferir o voto individual de moradores (evitando falácia "
            "ecológica)."
        ),
        params={},
    )


def generate_analysis_insights(
    *,
    year: int,
    round_num: int,
    office: Office,
    bloc: Bloc,
    indicator_label: str,
    indicator_unit: str,
    value_type: ValueType,
    ref_year: int,
    source_name: str,
    caveat: str | None,
    n_valid: int,
    n_scope_total: int,
    correlation: CorrelationStats | None = None,
    deciles: list[DecileStat] | None = None,
    extremes_contrast: QuintileExtremesContrast | None = None,
    category_summaries: list[CategoryShareSummary] | None = None,
) -> list[InsightCard]:
    """Generates deterministic narrative insight cards enforcing guards G1-G3.

    Guards:
    - `G1_MIN_SAMPLE`: If `n_valid < 30`, returns only `insufficient_data`.
    - `G2_MIN_COVERAGE`: If `n_valid / n_scope_total < 0.85`, adds
      `low_coverage_warning`.
    - `G3_CATEGORICAL`: If `value_type != ValueType.CONTINUOUS`, uses
      `category_breakdown` instead of `decile_top_vs_bottom` and
      `correlation_summary`.

    Args:
        year: Election year (e.g. 2026).
        round_num: Election round (1 or 2).
        office: Electoral office enum.
        bloc: Target ideological bloc (`left`, `center`, `right`).
        indicator_label: Display label of the indicator in Portuguese.
        indicator_unit: Measurement unit of the indicator.
        value_type: Statistical type (`continuous`, `ordinal`, `categorical`).
        ref_year: Indicator reference year.
        source_name: Official source name of the indicator.
        caveat: Optional methodological caveat from `indicators.yaml`.
        n_valid: Number of municipalities with valid indicator and vote values.
        n_scope_total: Total number of municipalities in the selected geographic scope.
        correlation: Computed `CorrelationStats` (for continuous indicators).
        deciles: Computed 10 `DecileStat` objects (for continuous indicators).
        extremes_contrast: Computed `QuintileExtremesContrast` (bottom 20% vs top 20%).
        category_summaries: Category breakdown (for categorical/ordinal indicators).

    Returns:
        Ordered list of deterministic `InsightCard` objects.
    """
    office_label = office.label_pt
    bloc_label = bloc.label_pt.lower()

    is_state_level = n_scope_total <= 27
    min_required = 20 if is_state_level else MIN_SAMPLE_SIZE_G1
    unit_noun = "estados" if is_state_level else "municípios"

    # Guard G1: Minimum sample size
    if n_valid < min_required:
        n_val_fmt = format_integer_pt(n_valid)
        return [
            InsightCard(
                template_id="insufficient_data",
                severity="caveat",
                title="Amostra Insuficiente",
                text=(
                    f"O recorte selecionado possui apenas **{n_val_fmt}** "
                    f"{unit_noun} com dados válidos para **{indicator_label}** "
                    f"(mínimo exigido: {min_required} {unit_noun} para análise "
                    "estatística confiável)."
                ),
                params={
                    "n_valid": n_valid,
                    "min_required": min_required,
                    "indicator_label": indicator_label,
                },
            )
        ]

    cards: list[InsightCard] = []

    # Guard G3: Categorical / ordinal vs continuous
    if value_type != ValueType.CONTINUOUS:
        if category_summaries:
            sorted_cats = sorted(
                category_summaries, key=lambda c: c.weighted_share, reverse=True
            )
            top_cat = sorted_cats[0]
            bottom_cat = sorted_cats[-1]
            top_pct = format_pct_pt(top_cat.weighted_share, is_ratio=True)
            bot_pct = format_pct_pt(bottom_cat.weighted_share, is_ratio=True)
            top_cnt_fmt = format_integer_pt(top_cat.municipality_count)
            cards.append(
                InsightCard(
                    template_id="category_breakdown",
                    severity="headline",
                    title="Votação por Categoria Municipal",
                    text=(
                        f"Em {year} ({round_num}º turno, {office_label}), os "
                        f"municípios classificados como **{top_cat.category}** em "
                        f"**{indicator_label}** ({top_cnt_fmt} municípios) "
                        f"direcionaram **{top_pct}** de seus votos válidos ao bloco de "
                        f"**{bloc_label}**, frente a **{bot_pct}** nos municípios "
                        f"classificados como **{bottom_cat.category}**."
                    ),
                    params={
                        "year": year,
                        "round": round_num,
                        "office_label": office_label,
                        "indicator_label": indicator_label,
                        "bloc_label": bloc_label,
                        "top_category": top_cat.category,
                        "top_share_pct": top_pct,
                        "bottom_category": bottom_cat.category,
                        "bottom_share_pct": bot_pct,
                    },
                )
            )
    else:
        if deciles and len(deciles) >= 2:
            d_bottom = deciles[0]
            d_top = deciles[-1]
            n_top_fmt = format_integer_pt(d_top.municipality_count)
            top_min_fmt = format_indicator_value_pt(d_top.indicator_min, indicator_unit)
            top_max_fmt = format_indicator_value_pt(d_top.indicator_max, indicator_unit)
            share_top_pct = format_pct_pt(d_top.weighted_share, is_ratio=True)
            share_bottom_pct = format_pct_pt(d_bottom.weighted_share, is_ratio=True)
            diff_pp = format_pp_diff_pt(
                d_top.weighted_share - d_bottom.weighted_share, is_ratio=True
            )

            cards.append(
                InsightCard(
                    template_id="decile_top_vs_bottom",
                    severity="headline",
                    title="Comparação entre Extremos (10% Maior vs. 10% Menor)",
                    text=(
                        f"Em {year} ({round_num}º turno, {office_label}), os 10% dos "
                        f"municípios com maior **{indicator_label}** ({n_top_fmt} "
                        f"municípios, de {top_min_fmt} a {top_max_fmt}) direcionaram "
                        f"**{share_top_pct}** de seus votos válidos ao bloco de "
                        f"**{bloc_label}**, contra **{share_bottom_pct}** nos 10% dos "
                        f"municípios com menor valor do indicador ({diff_pp})."
                    ),
                    params={
                        "year": year,
                        "round": round_num,
                        "office_label": office_label,
                        "indicator_label": indicator_label,
                        "n_top": d_top.municipality_count,
                        "top_min": top_min_fmt,
                        "top_max": top_max_fmt,
                        "share_top_pct": share_top_pct,
                        "bloc_label": bloc_label,
                        "share_bottom_pct": share_bottom_pct,
                        "diff_pp": diff_pp,
                    },
                )
            )

        if extremes_contrast is not None:
            q_bot_share = format_pct_pt(
                extremes_contrast.bottom_quintile_share, is_ratio=True
            )
            q_top_share = format_pct_pt(
                extremes_contrast.top_quintile_share, is_ratio=True
            )
            q_diff = format_pp_diff_pt(extremes_contrast.diff_pp, is_ratio=False)
            bot_cnt = format_integer_pt(extremes_contrast.bottom_municipality_count)
            top_cnt = format_integer_pt(extremes_contrast.top_municipality_count)
            bot_min = format_indicator_value_pt(
                extremes_contrast.bottom_indicator_range[0], indicator_unit
            )
            bot_max = format_indicator_value_pt(
                extremes_contrast.bottom_indicator_range[1], indicator_unit
            )
            top_min = format_indicator_value_pt(
                extremes_contrast.top_indicator_range[0], indicator_unit
            )
            top_max = format_indicator_value_pt(
                extremes_contrast.top_indicator_range[1], indicator_unit
            )

            tipping_note = ""
            if (
                extremes_contrast.tipping_point_decile is not None
                and extremes_contrast.tipping_point_threshold is not None
            ):
                th_fmt = format_indicator_value_pt(
                    extremes_contrast.tipping_point_threshold, indicator_unit
                )
                tip_dec = extremes_contrast.tipping_point_decile
                tipping_note = f" Ponto de inflexão no Decil D{tip_dec} ({th_fmt})."

            cards.append(
                InsightCard(
                    template_id="extremes_two_brazils",
                    severity="finding",
                    title="Contraste dos 'Dois Brasis' (20% Topo vs. 20% Base)",
                    text=(
                        f"Em {year} ({round_num}º turno, {office_label}), nos 20% "
                        f"dos municípios com maior **{indicator_label}** "
                        f"({top_cnt} municípios, de {top_min} a {top_max}), o bloco de "
                        f"**{bloc_label}** obteve **{q_top_share}** dos votos válidos, "
                        f"contra **{q_bot_share}** nos 20% dos municípios de menor "
                        f"valor ({bot_cnt} municípios, de {bot_min} a {bot_max}) "
                        f"— saldo de **{q_diff}**.{tipping_note}"
                    ),
                    params={
                        "year": year,
                        "round": round_num,
                        "office_label": office_label,
                        "indicator_label": indicator_label,
                        "bloc_label": bloc_label,
                        "top_quintile_share": q_top_share,
                        "bottom_quintile_share": q_bot_share,
                        "diff_pp": q_diff,
                        "tipping_point_decile": extremes_contrast.tipping_point_decile
                        or 0,
                    },
                )
            )

        if correlation is not None:
            n_fmt = format_integer_pt(correlation.n_valid)
            strength_label = STRENGTH_LABELS_PT[correlation.strength]
            direction_label = DIRECTION_LABELS_PT[correlation.direction]
            rho_fmt = format_rho_pt(correlation.spearman_rho)
            p_fmt = format_p_value_pt(correlation.spearman_p)

            corr_title = (
                "Correlação entre Estados"
                if is_state_level
                else "Correlação entre Municípios"
            )
            cards.append(
                InsightCard(
                    template_id="correlation_summary",
                    severity="finding",
                    title=corr_title,
                    text=(
                        f"Considerando os {n_fmt} {unit_noun} com dados disponíveis "
                        f"para **{indicator_label}** (ano-base {ref_year}), a "
                        f"correlação com o percentual de votos no bloco de "
                        f"**{bloc_label}** é **{strength_label}** e "
                        f"**{direction_label}** ($\\rho = {rho_fmt}$, $p {p_fmt}$)."
                    ),
                    params={
                        "n": correlation.n_valid,
                        "indicator_label": indicator_label,
                        "ref_year": ref_year,
                        "bloc_label": bloc_label,
                        "strength_label": strength_label,
                        "direction_label": direction_label,
                        "rho_fmt": rho_fmt,
                        "p_fmt": p_fmt,
                    },
                )
            )

    # Guard G2: Low coverage warning
    scope_denom = max(1, n_scope_total)
    coverage_ratio = n_valid / scope_denom
    if coverage_ratio < MIN_COVERAGE_RATIO_G2:
        n_missing = max(0, n_scope_total - n_valid)
        cov_pct = format_pct_pt(coverage_ratio, is_ratio=True)
        cards.append(
            InsightCard(
                template_id="low_coverage_warning",
                severity="caveat",
                title="Cobertura Parcial de Municípios",
                text=(
                    f"Atenção: o indicador **{indicator_label}** está disponível para "
                    f"**{format_integer_pt(n_valid)}** de "
                    f"**{format_integer_pt(n_scope_total)}** municípios ({cov_pct}); "
                    f"**{format_integer_pt(n_missing)}** municípios não possuem valor "
                    "divulgado na fonte oficial."
                ),
                params={
                    "n_valid": n_valid,
                    "n_scope_total": n_scope_total,
                    "n_missing": n_missing,
                    "coverage_pct": cov_pct,
                },
            )
        )

    # Temporal / methodological caveat
    if ref_year <= year - 4 or caveat is not None:
        extra_caveat = f" {caveat}" if caveat else ""
        cards.append(
            InsightCard(
                template_id="temporal_caveat",
                severity="caveat",
                title="Nota Metodológica e Temporal",
                text=(
                    f"Nota metodológica: o indicador **{indicator_label}** tem ano de "
                    f"referência **{ref_year}** ({source_name}).{extra_caveat}"
                ),
                params={
                    "indicator_label": indicator_label,
                    "ref_year": ref_year,
                    "source_name": source_name,
                    "caveat": caveat or "",
                },
            )
        )

    cards.append(build_ecological_reminder_card())
    return cards
