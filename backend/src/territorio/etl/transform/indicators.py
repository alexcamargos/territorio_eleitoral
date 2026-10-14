"""Post-extraction indicator transformations, coverage checks, and derived math."""

import ast
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from territorio.domain import ValueType
from territorio.etl.reference import CoverageExceptionRule, IndicatorSpec

MISSING_TOKENS_DEFAULT: frozenset[str] = frozenset(
    {"", "-", "..", "...", "X", "x", "null", "NULL", "NaN", "nan", "N/A", "#N/A"}
)


class IndicatorTransformError(ValueError):
    """Raised when an indicator fails range, join, or expression evaluation rules."""


class IndicatorCoverageError(IndicatorTransformError):
    """Raised when an indicator's valid municipal coverage is below `min_coverage`."""


@dataclass(frozen=True, slots=True)
class QualityIssueSummary:
    """Aggregated quality log record produced during indicator normalization.

    Attributes:
        indicator_code: Indicator identifier.
        severity: Issue severity ('info' or 'warn').
        check_name: Standardized check name (e.g. 'missing_values').
        cd_ibge: Specific municipality code if single-row, or None if aggregated.
        details: JSON-serializable details dictionary.
    """

    indicator_code: str
    severity: str
    check_name: str
    cd_ibge: int | None
    details: dict[str, object]


def parse_ibge_numeric_value(
    raw_val: object,
    *,
    sentinel_min: float | None = None,
) -> tuple[float | None, str | None]:
    """Parses a raw IBGE/SIDRA/SICONFI string or number into `(value, missing_reason)`.

    Handles Brazilian decimal commas, IBGE conventional signs (`'-'`, `'..'`,
    `'...'`, `'X'`), and IBGE Pesquisas sentinel numbers (`>= 99999999999990`).

    Args:
        raw_val: Raw scalar value from an API or file.
        sentinel_min: Optional lower bound above which numeric values are treated
            as IBGE sentinel missing codes.

    Returns:
        Tuple `(float_value, missing_reason)` where `float_value` is `None` when
        missing and `missing_reason` explains why.
    """
    if raw_val is None or (isinstance(raw_val, float) and np.isnan(raw_val)):
        return None, "ausente_na_fonte"

    if isinstance(raw_val, (int, float, np.number)):
        num = float(raw_val)
        if np.isnan(num):
            return None, "ausente_na_fonte"
        if sentinel_min is not None and num >= sentinel_min:
            return None, "sentinela_ibge"
        return num, None

    text = str(raw_val).strip()
    if not text or text in {"..", "...", "null", "NULL", "NaN", "nan", "#N/A", "N/A"}:
        return None, "ausente_na_fonte"
    if text == "-":
        return None, "zero_absoluto_ou_nao_aplicavel"
    if text.upper() == "X":
        return None, "sigilo_estatistico"

    normalized = text.replace(".", "").replace(",", ".") if "," in text else text
    try:
        num = float(normalized)
    except ValueError:
        return None, "valor_nao_numerico"

    if np.isnan(num):
        return None, "ausente_na_fonte"
    if sentinel_min is not None and num >= sentinel_min:
        return None, "sentinela_ibge"
    return num, None


def resolve_ref_year(policy: str, available_years: list[int] | set[int]) -> int:
    """Resolves the canonical reference year according to `ref_year_policy`.

    Args:
        policy: Policy string from `indicators.yaml` (`'latest'`,
            `'nearest_before_election'`, or `'fixed:YYYY'`).
        available_years: Non-empty collection of candidate reference years.

    Returns:
        Selected integer reference year.

    Raises:
        IndicatorTransformError: If `policy` is malformed or no matching year exists.
    """
    if policy.startswith("fixed:"):
        try:
            return int(policy.split(":", 1)[1])
        except ValueError as exc:
            raise IndicatorTransformError(
                f"Invalid fixed ref_year_policy: {policy!r}"
            ) from exc

    if not available_years:
        raise IndicatorTransformError(
            f"Cannot resolve ref_year_policy={policy!r} from empty year set."
        )

    if policy == "latest":
        return max(available_years)

    if policy == "nearest_before_election":
        eligible = [y for y in available_years if y <= 2026]
        if not eligible:
            raise IndicatorTransformError(
                f"No available years <= 2026 for policy={policy!r}: {available_years}"
            )
        return max(eligible)

    raise IndicatorTransformError(f"Unsupported ref_year_policy: {policy!r}")


def _eval_ast_node(
    node: ast.AST,
    variables: Mapping[str, pd.Series],
) -> pd.Series | float:
    """Recursively evaluates a safe arithmetic AST node over pandas Series.

    Args:
        node: Parsed Python AST node.
        variables: Mapping of variable identifier to pandas Series indexed by
            `cd_ibge`.

    Returns:
        Resulting pandas Series or float scalar.

    Raises:
        IndicatorTransformError: If the AST contains any unsupported construct.
    """
    if isinstance(node, ast.Expression):
        return _eval_ast_node(node.body, variables)

    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)

    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise IndicatorTransformError(
                f"Unknown variable {node.id!r} in derived expression."
            )
        return variables[node.id]

    if isinstance(node, ast.UnaryOp):
        operand = _eval_ast_node(node.operand, variables)
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise IndicatorTransformError(
            f"Unsupported unary operator: {type(node.op).__name__}"
        )

    if isinstance(node, ast.BinOp):
        left = _eval_ast_node(node.left, variables)
        right = _eval_ast_node(node.right, variables)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if isinstance(right, pd.Series):
                safe_right = right.where(right != 0.0, np.nan)
                return left / safe_right
            if right == 0.0:
                raise IndicatorTransformError("Division by zero in derived expression.")
            return left / right
        raise IndicatorTransformError(
            f"Unsupported binary operator: {type(node.op).__name__}"
        )

    raise IndicatorTransformError(
        f"Unsupported AST node in derived expression: {type(node).__name__}"
    )


def evaluate_arithmetic_expr(
    expr: str,
    variables: Mapping[str, pd.Series],
) -> pd.Series:
    """Evaluates a safe arithmetic expression over municipal Series.

    Args:
        expr: Arithmetic formula (e.g. `'population / area_km2'`).
        variables: Mapping from variable name in `expr` to a numeric `pd.Series`
            indexed by `cd_ibge`.

    Returns:
        Evaluated float `pd.Series` indexed by `cd_ibge`.

    Raises:
        IndicatorTransformError: If `expr` has syntax errors or disallowed AST nodes.
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise IndicatorTransformError(
            f"Syntax error in derived expression {expr!r}: {exc}"
        ) from exc

    res = _eval_ast_node(tree, variables)
    if isinstance(res, pd.Series):
        return res.astype(float)
    first_series = next(iter(variables.values()))
    return pd.Series(float(res), index=first_series.index, dtype=float)


def finalize_indicator_dataframe(
    raw_df: pd.DataFrame,
    spec: IndicatorSpec,
    *,
    master_ibge_codes: list[int] | set[int] | tuple[int, ...],
    coverage_exceptions: tuple[CoverageExceptionRule, ...] = (),
    denominator_by_ibge: Mapping[int, float] | None = None,
    ref_year_override: int | None = None,
) -> tuple[pd.DataFrame, list[QualityIssueSummary]]:
    """Applies declarative transforms, coverage exceptions, and validation rules.

    Aligns `raw_df` against the canonical `master_ibge_codes` universe using a
    validated `one_to_one` merge (`indicator=True`), applies `sentinel_min`,
    `multiply`, and `per_capita` transformations, stamps `missing_reason` for
    exempt and missing municipalities, validates `valid_range`, and enforces
    `min_coverage`.

    Args:
        raw_df: Extracted DataFrame with columns `['cd_ibge']` and at least one of
            `['value', 'value_text', 'ref_year', 'missing_reason']`.
        spec: Indicator specification from `indicators.yaml`.
        master_ibge_codes: Canonical 7-digit IBGE municipality codes (e.g. 5,571).
        coverage_exceptions: Documented exception rules from `indicators.yaml`.
        denominator_by_ibge: Optional mapping `cd_ibge -> population` required when
            `spec.transform` defines `per_capita`.
        ref_year_override: Explicit reference year if not present in `raw_df`.

    Returns:
        Tuple `(final_df, quality_issues)` where `final_df` has columns
        `['indicator_code', 'ref_year', 'cd_ibge', 'value', 'value_text',
        'missing_reason']`.

    Raises:
        IndicatorTransformError: On duplicate `cd_ibge`, unknown `cd_ibge` outside
            `master_ibge_codes`, missing `per_capita` denominator map, or values
            outside `spec.valid_range`.
        IndicatorCoverageError: If non-null coverage is below `spec.min_coverage`.
    """
    master_sorted = sorted({int(c) for c in master_ibge_codes})
    if not master_sorted:
        raise IndicatorTransformError("master_ibge_codes cannot be empty.")

    master_frame = pd.DataFrame({"cd_ibge": master_sorted})

    if raw_df.empty:
        ref_year = (
            ref_year_override
            if ref_year_override is not None
            else resolve_ref_year(spec.ref_year_policy, [2022])
        )
        work = master_frame.copy()
        work["value"] = np.nan
        work["value_text"] = None
        work["missing_reason"] = "ausente_na_fonte"
    else:
        df = raw_df.copy()
        df["cd_ibge"] = pd.to_numeric(df["cd_ibge"], errors="raise").astype(int)
        if df["cd_ibge"].duplicated().any():
            dups = df.loc[df["cd_ibge"].duplicated(), "cd_ibge"].unique().tolist()
            raise IndicatorTransformError(
                f"Indicator {spec.code!r} has duplicate cd_ibge rows: {dups[:5]}"
            )

        unknown_codes = set(df["cd_ibge"].tolist()) - set(master_sorted)
        if unknown_codes:
            raise IndicatorTransformError(
                f"Indicator {spec.code!r} contains cd_ibge not in master list: "
                f"{sorted(unknown_codes)[:5]}"
            )

        if ref_year_override is not None:
            ref_year = int(ref_year_override)
        elif "ref_year" in df.columns and df["ref_year"].notna().any():
            years = [int(y) for y in df["ref_year"].dropna().unique().tolist()]
            ref_year = resolve_ref_year(spec.ref_year_policy, years)
        else:
            ref_year = resolve_ref_year(spec.ref_year_policy, [2022])

        if "value" not in df.columns:
            df["value"] = np.nan
        if "value_text" not in df.columns:
            df["value_text"] = None
        if "missing_reason" not in df.columns:
            df["missing_reason"] = None

        merged = master_frame.merge(
            df[["cd_ibge", "value", "value_text", "missing_reason"]],
            on="cd_ibge",
            how="left",
            validate="one_to_one",
            indicator=True,
        )
        unmatched_mask = merged["_merge"] != "both"
        merged.loc[unmatched_mask, "missing_reason"] = "ausente_na_fonte"
        work = merged.drop(columns=["_merge"])

    transform = spec.transform or {}
    sentinel_min = transform.get("sentinel_min")

    if spec.value_type == ValueType.CONTINUOUS:
        parsed_vals: list[float] = []
        parsed_reasons: list[str | None] = []
        for val, reason in zip(
            work["value"].tolist(), work["missing_reason"].tolist(), strict=True
        ):
            clean_reason = (
                str(reason) if (reason is not None and not pd.isna(reason)) else None
            )
            num, p_reason = parse_ibge_numeric_value(
                val,
                sentinel_min=float(sentinel_min) if sentinel_min is not None else None,
            )
            if num is None:
                parsed_vals.append(np.nan)
                parsed_reasons.append(
                    clean_reason if clean_reason is not None else p_reason
                )
            else:
                parsed_vals.append(num)
                parsed_reasons.append(None)
        work["value"] = pd.Series(parsed_vals, index=work.index, dtype=float)
        work["missing_reason"] = parsed_reasons
        work["value_text"] = None
    else:
        # Ordinal or categorical
        cleaned_texts: list[str | None] = []
        cleaned_reasons: list[str | None] = []
        for txt, val, reason in zip(
            work["value_text"].tolist(),
            work["value"].tolist(),
            work["missing_reason"].tolist(),
            strict=True,
        ):
            clean_reason = (
                str(reason) if (reason is not None and not pd.isna(reason)) else None
            )
            candidate = txt if (txt is not None and not pd.isna(txt)) else val
            if candidate is None or pd.isna(candidate):
                cleaned_texts.append(None)
                cleaned_reasons.append(clean_reason or "ausente_na_fonte")
                continue
            s_val = str(candidate).strip()
            if (
                sentinel_min is not None
                and s_val.isdigit()
                and float(s_val) >= float(sentinel_min)
            ):
                cleaned_texts.append(None)
                cleaned_reasons.append("sentinela_ibge")
            elif not s_val or s_val in {"-", "..", "...", "null", "NULL", "NaN"}:
                cleaned_texts.append(None)
                cleaned_reasons.append(clean_reason or "ausente_na_fonte")
            else:
                cleaned_texts.append(s_val)
                cleaned_reasons.append(None)
        work["value_text"] = cleaned_texts
        work["missing_reason"] = cleaned_reasons
        if spec.value_type == ValueType.ORDINAL:
            allowed = spec.source_params.get("allowed_values")
            if isinstance(allowed, list) and allowed:
                rank_map = {
                    str(v): float(len(allowed) - idx) for idx, v in enumerate(allowed)
                }
                work["value"] = [
                    rank_map.get(t, np.nan) if t is not None else np.nan
                    for t in cleaned_texts
                ]
            else:
                work["value"] = pd.to_numeric(work["value"], errors="coerce")
        else:
            work["value"] = np.nan

    # Apply multiply and per_capita for continuous indicators
    if spec.value_type == ValueType.CONTINUOUS:
        if "multiply" in transform and transform["multiply"] is not None:
            factor = float(transform["multiply"])
            work["value"] = work["value"] * factor

        if "per_capita" in transform and transform["per_capita"] is not None:
            if denominator_by_ibge is None:
                raise IndicatorTransformError(
                    f"Indicator {spec.code!r} requires per_capita denominator_by_ibge."
                )
            new_vals: list[float] = []
            new_reasons: list[str | None] = []
            for cd, val, reason in zip(
                work["cd_ibge"].tolist(),
                work["value"].tolist(),
                work["missing_reason"].tolist(),
                strict=True,
            ):
                clean_reason = (
                    str(reason)
                    if (reason is not None and not pd.isna(reason))
                    else None
                )
                if np.isnan(val):
                    new_vals.append(np.nan)
                    new_reasons.append(clean_reason)
                    continue
                pop = denominator_by_ibge.get(int(cd))
                if pop is None or np.isnan(pop) or pop <= 0.0:
                    new_vals.append(np.nan)
                    new_reasons.append("denominador_ausente")
                else:
                    new_vals.append(float(val) / float(pop))
                    new_reasons.append(None)
            work["value"] = pd.Series(new_vals, index=work.index, dtype=float)
            work["missing_reason"] = new_reasons

    # Apply documented coverage exceptions for missing rows
    exempt_codes: set[int] = set()
    exc_by_ibge: dict[int, str] = {}
    for exc in coverage_exceptions:
        if exc.matches(adapter=spec.adapter, ref_year=ref_year):
            exempt_codes.add(exc.cd_ibge)
            exc_by_ibge[exc.cd_ibge] = exc.missing_reason

    final_reasons: list[str | None] = []
    for cd, val, txt, reason in zip(
        work["cd_ibge"].tolist(),
        work["value"].tolist(),
        work["value_text"].tolist(),
        work["missing_reason"].tolist(),
        strict=True,
    ):
        clean_reason = (
            str(reason) if (reason is not None and not pd.isna(reason)) else None
        )
        is_missing = (
            bool(pd.isna(val))
            if spec.value_type == ValueType.CONTINUOUS
            else bool(pd.isna(txt))
        )
        if not is_missing:
            final_reasons.append(None)
        elif int(cd) in exc_by_ibge:
            final_reasons.append(exc_by_ibge[int(cd)])
        else:
            final_reasons.append(clean_reason or "ausente_na_fonte")
    work["missing_reason"] = final_reasons

    # Check valid_range for continuous values
    if spec.value_type == ValueType.CONTINUOUS and spec.valid_range is not None:
        low, high = spec.valid_range
        valid_series = work["value"].dropna()
        out_of_bounds = valid_series[(valid_series < low) | (valid_series > high)]
        if not out_of_bounds.empty:
            bad_idx = out_of_bounds.index[0]
            bad_cd = int(work.loc[bad_idx, "cd_ibge"])
            bad_val = float(out_of_bounds.iloc[0])
            raise IndicatorTransformError(
                f"Indicator {spec.code!r} value {bad_val} at cd_ibge={bad_cd} "
                f"is outside valid_range=[{low}, {high}]."
            )

    # Check min_coverage
    if spec.value_type == ValueType.CONTINUOUS:
        valid_count = int(work["value"].notna().sum())
    else:
        valid_count = int(work["value_text"].notna().sum())

    eligible_total = max(1, len(master_sorted) - len(exempt_codes))
    coverage_ratio = valid_count / eligible_total
    if coverage_ratio < spec.min_coverage:
        raise IndicatorCoverageError(
            f"Indicator {spec.code!r} coverage {coverage_ratio:.4f} "
            f"({valid_count}/{eligible_total}) is below "
            f"min_coverage={spec.min_coverage}."
        )

    work["indicator_code"] = spec.code
    work["ref_year"] = int(ref_year)

    # Build quality issues summary for missing values
    quality_issues: list[QualityIssueSummary] = []
    missing_rows = work[work["missing_reason"].notna()]
    if not missing_rows.empty:
        counts_by_reason = missing_rows["missing_reason"].value_counts().to_dict()
        quality_issues.append(
            QualityIssueSummary(
                indicator_code=spec.code,
                severity="info" if len(missing_rows) <= len(exempt_codes) else "warn",
                check_name="missing_values_summary",
                cd_ibge=None,
                details={
                    "ref_year": int(ref_year),
                    "missing_total": len(missing_rows),
                    "valid_total": valid_count,
                    "coverage_ratio": round(coverage_ratio, 6),
                    "reasons": {str(k): int(v) for k, v in counts_by_reason.items()},
                },
            )
        )

    final_cols = [
        "indicator_code",
        "ref_year",
        "cd_ibge",
        "value",
        "value_text",
        "missing_reason",
    ]
    return work[final_cols].sort_values("cd_ibge").reset_index(
        drop=True
    ), quality_issues


def compute_derived_indicator(
    spec: IndicatorSpec,
    *,
    master_ibge_codes: list[int] | set[int] | tuple[int, ...],
    coverage_exceptions: tuple[CoverageExceptionRule, ...] = (),
    indicator_frames: Mapping[str, pd.DataFrame] | None = None,
    election_turnout_df: pd.DataFrame | None = None,
    seasonal_bonus_by_ibge: Mapping[int, float] | None = None,
) -> tuple[pd.DataFrame, list[QualityIssueSummary]]:
    """Computes a derived indicator (`adapter: derived`) and finalizes its DataFrame.

    Supports both indicator-to-indicator formulas (`density`, `income_transfers_pc`)
    and electoral summary formulas (`turnout_pct`, `blank_null_pct`).

    Args:
        spec: Derived indicator specification from `indicators.yaml`.
        master_ibge_codes: Canonical 7-digit IBGE municipality codes.
        coverage_exceptions: Documented coverage exception rules.
        indicator_frames: Mapping of already-computed `indicator_code -> DataFrame`.
        election_turnout_df: Turnout DataFrame for `table: "election_summary"`
            derived indicators.
        seasonal_bonus_by_ibge: Optional per-capita monthly average from seasonal
            transfer programs (`safra-por-municipio`, `seguro-defeso-por-municipio`)
            added to `income_transfers_pc`.

    Returns:
        Tuple `(final_df, quality_issues)`.

    Raises:
        IndicatorTransformError: If required inputs or turnout data are missing.
    """
    if spec.adapter != "derived":
        raise IndicatorTransformError(
            f"Indicator {spec.code!r} has adapter={spec.adapter!r}, expected 'derived'."
        )

    master_sorted = sorted({int(c) for c in master_ibge_codes})
    idx = pd.Index(master_sorted, name="cd_ibge")
    expr = str(spec.source_params.get("expr", "")).strip()
    if not expr:
        raise IndicatorTransformError(
            f"Derived indicator {spec.code!r} is missing source.params.expr."
        )

    if spec.source_params.get("table") == "election_summary":
        if election_turnout_df is None or election_turnout_df.empty:
            raise IndicatorTransformError(
                f"Derived indicator {spec.code!r} requires election_turnout_df."
            )
        tdf = election_turnout_df.copy()
        target_round = int(spec.source_params.get("round", 1))
        if "round" in tdf.columns:
            tdf = tdf[tdf["round"].astype(int) == target_round]
        if (
            "tse_cd_cargo" in tdf.columns
            and spec.source_params.get("office") == "president"
        ):
            tdf = tdf[tdf["tse_cd_cargo"].astype(int) == 1]

        tdf = tdf.set_index("cd_ibge").reindex(idx)
        variables: dict[str, pd.Series] = {}
        for col in (
            "eligible_voters",
            "turnout",
            "abstention",
            "valid_votes",
            "blank_votes",
            "null_votes",
        ):
            if col in tdf.columns:
                variables[col] = pd.to_numeric(tdf[col], errors="coerce").astype(float)

        computed = evaluate_arithmetic_expr(expr, variables)
        raw_df = pd.DataFrame(
            {
                "cd_ibge": idx.to_numpy(),
                "value": computed.to_numpy(),
                "ref_year": 2026,
            }
        )
        return finalize_indicator_dataframe(
            raw_df,
            spec,
            master_ibge_codes=master_sorted,
            coverage_exceptions=coverage_exceptions,
            ref_year_override=2026,
        )

    inputs_map = spec.source_params.get("inputs")
    if not isinstance(inputs_map, dict) or not inputs_map:
        raise IndicatorTransformError(
            f"Derived indicator {spec.code!r} is missing source.params.inputs."
        )
    if indicator_frames is None:
        raise IndicatorTransformError(
            f"Derived indicator {spec.code!r} requires indicator_frames."
        )

    variables = {}
    candidate_years: list[int] = []
    for var_name, dep_code_raw in inputs_map.items():
        dep_code = str(dep_code_raw)
        if dep_code not in indicator_frames:
            raise IndicatorTransformError(
                f"Derived indicator {spec.code!r} missing input {dep_code!r}."
            )
        dep_df = indicator_frames[dep_code]
        if "ref_year" in dep_df.columns and dep_df["ref_year"].notna().any():
            candidate_years.extend(
                int(y) for y in dep_df["ref_year"].dropna().unique().tolist()
            )
        s = dep_df.set_index("cd_ibge")["value"].reindex(idx).astype(float)
        variables[str(var_name)] = s

    computed = evaluate_arithmetic_expr(expr, variables)
    if seasonal_bonus_by_ibge:
        bonus_series = pd.Series(
            [float(seasonal_bonus_by_ibge.get(c, 0.0)) for c in master_sorted],
            index=idx,
            dtype=float,
        )
        computed = computed + bonus_series

    ref_year = resolve_ref_year(
        spec.ref_year_policy,
        candidate_years if candidate_years else [2026],
    )
    raw_df = pd.DataFrame(
        {
            "cd_ibge": idx.to_numpy(),
            "value": computed.to_numpy(),
            "ref_year": ref_year,
        }
    )
    return finalize_indicator_dataframe(
        raw_df,
        spec,
        master_ibge_codes=master_sorted,
        coverage_exceptions=coverage_exceptions,
        ref_year_override=ref_year,
    )
