"""Locale-independent Brazilian Portuguese (`pt-BR`) number formatting helpers."""

import math


def format_number_pt(value: float | int, decimals: int = 1) -> str:
    """Formats a number using `pt-BR` separators (`.` for thousands, `,` for decimals).

    Never relies on the operating system's `locale` settings.

    Args:
        value: Numeric value to format.
        decimals: Number of digits after the decimal comma (`>= 0`).

    Returns:
        Formatted `pt-BR` number string.
    """
    if math.isnan(float(value)):
        return "—"
    decimals = max(0, int(decimals))
    us_formatted = f"{float(value):,.{decimals}f}"
    return us_formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def format_integer_pt(value: int | float) -> str:
    """Formats an integer with `.` thousands separator (`5.571`).

    Args:
        value: Integer (or float rounded to integer) to format.

    Returns:
        Formatted `pt-BR` integer string.
    """
    return format_number_pt(round(float(value)), decimals=0)


def format_pct_pt(
    value: float,
    *,
    is_ratio: bool = True,
    decimals: int = 1,
) -> str:
    """Formats a share or percentage with 1 decimal place (`70,3%`).

    Args:
        value: Proportion in `[0, 1]` when `is_ratio=True`, or percentage in
            `[0, 100]` when `is_ratio=False`.
        is_ratio: Whether `value` is a ratio in `[0, 1]` that should be
            multiplied by `100.0`.
        decimals: Number of decimal digits (defaults to 1).

    Returns:
        Formatted percentage string ending with `'%'`.
    """
    scaled = float(value) * 100.0 if is_ratio else float(value)
    return f"{format_number_pt(scaled, decimals=decimals)}%"


def format_pp_diff_pt(
    diff: float,
    *,
    is_ratio: bool = True,
    decimals: int = 1,
) -> str:
    """Formats a percentage-point difference with explicit sign (`+14,2 p.p.`).

    Args:
        diff: Difference in proportions (`[-1, +1]`) if `is_ratio=True`, or in
            percentage points (`[-100, +100]`) if `is_ratio=False`.
        is_ratio: Whether `diff` is a ratio in `[-1, +1]` to multiply by 100.
        decimals: Number of decimal digits (defaults to 1).

    Returns:
        Signed percentage-point string (e.g. `'+14,2 p.p.'` or `'-8,5 p.p.'`).
    """
    scaled = float(diff) * 100.0 if is_ratio else float(diff)
    sign = "+" if scaled >= 0.0 else "-"
    return f"{sign}{format_number_pt(abs(scaled), decimals=decimals)} p.p."


def format_rho_pt(rho: float) -> str:
    """Formats a correlation coefficient with 2 decimal places and explicit sign.

    Args:
        rho: Correlation coefficient in `[-1.0, +1.0]`.

    Returns:
        Signed string such as `'+0,64'` or `'-0,41'`.
    """
    if math.isnan(rho):
        return "—"
    sign = "+" if rho >= 0.0 else "-"
    return f"{sign}{format_number_pt(abs(rho), decimals=2)}"


def format_p_value_pt(p_value: float) -> str:
    """Formats a two-sided p-value for display inside `$p {p_fmt}$`.

    Args:
        p_value: Probability value in `[0.0, 1.0]`.

    Returns:
        String `'< 0,001'` when `p_value < 0.001`, otherwise `'= 0,042'`.
    """
    if math.isnan(p_value):
        return "= —"
    if p_value < 0.001:
        return "< 0,001"
    return f"= {format_number_pt(p_value, decimals=3)}"


def format_currency_pt(value: float) -> str:
    """Formats a Brazilian Real (`R$`) amount per methodology rules.

    Values `>= 100` are formatted with 0 decimal places (`R$ 42.150`); values
    `< 100` are formatted with 2 decimal places (`R$ 68,50`).

    Args:
        value: Monetary value in `R$`.

    Returns:
        Formatted `R$` currency string.
    """
    if math.isnan(value):
        return "—"
    sign = "-" if value < 0 else ""
    abs_val = abs(float(value))
    if abs_val >= 100.0:
        return f"{sign}R$ {format_number_pt(abs_val, decimals=0)}"
    return f"{sign}R$ {format_number_pt(abs_val, decimals=2)}"


def format_indicator_value_pt(value: float, unit: str) -> str:
    """Formats an indicator numeric value according to its catalog `unit`.

    Args:
        value: Numeric indicator value.
        unit: Indicator unit string from `indicators.yaml` (`'R$'`, `'%'`, etc.).

    Returns:
        Human-readable formatted value string in `pt-BR`.
    """
    u = unit.strip()
    if u.startswith("R$"):
        return format_currency_pt(value)
    if u == "%":
        return format_pct_pt(value, is_ratio=False, decimals=1)
    if u == "pessoas":
        return format_integer_pt(value)
    if "0-1" in u and "0-10" not in u and "0-100" not in u:
        return format_number_pt(value, decimals=3)
    return format_number_pt(value, decimals=1)
