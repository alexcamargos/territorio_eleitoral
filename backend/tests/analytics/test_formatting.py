"""Unit tests for locale-independent `pt-BR` number formatting."""

import math

from territorio.analytics.formatting import (
    format_currency_pt,
    format_indicator_value_pt,
    format_integer_pt,
    format_number_pt,
    format_p_value_pt,
    format_pct_pt,
    format_pp_diff_pt,
    format_rho_pt,
)


def test_format_number_and_integer_pt() -> None:
    """Verifies `.` thousands separator and `,` decimal separator."""
    assert format_number_pt(1234567.89, decimals=2) == "1.234.567,89"
    assert format_number_pt(float("nan")) == "—"
    assert format_integer_pt(5571) == "5.571"


def test_format_pct_and_pp_diff_pt() -> None:
    """Verifies percentage and percentage-point difference formatting."""
    assert format_pct_pt(0.703, is_ratio=True) == "70,3%"
    assert format_pct_pt(70.3, is_ratio=False) == "70,3%"
    assert format_pp_diff_pt(0.142, is_ratio=True) == "+14,2 p.p."
    assert format_pp_diff_pt(-0.085, is_ratio=True) == "-8,5 p.p."
    assert format_pp_diff_pt(-8.5, is_ratio=False) == "-8,5 p.p."


def test_format_rho_and_p_value_pt() -> None:
    """Verifies correlation rho and p-value formatting rules."""
    assert format_rho_pt(0.641) == "+0,64"
    assert format_rho_pt(-0.412) == "-0,41"
    assert format_rho_pt(math.nan) == "—"
    assert format_p_value_pt(0.0001) == "< 0,001"
    assert format_p_value_pt(0.042) == "= 0,042"
    assert format_p_value_pt(math.nan) == "= —"


def test_format_currency_and_indicator_value_pt() -> None:
    """Verifies `R$` threshold (`>= 100` vs `< 100`) and unit-based formatting."""
    assert format_currency_pt(42150.4) == "R$ 42.150"
    assert format_currency_pt(68.5) == "R$ 68,50"
    assert format_currency_pt(-45.2) == "-R$ 45,20"
    assert format_currency_pt(math.nan) == "—"

    assert format_indicator_value_pt(42150.0, "R$") == "R$ 42.150"
    assert format_indicator_value_pt(68.5, "R$/hab. no mês") == "R$ 68,50"
    assert format_indicator_value_pt(72.4, "%") == "72,4%"
    assert format_indicator_value_pt(12500, "pessoas") == "12.500"
    assert format_indicator_value_pt(0.785, "índice 0-1") == "0,785"
    assert format_indicator_value_pt(6.4, "índice 0-10") == "6,4"
