"""Deterministic bivariate correlation, trendline, decile, and quantile math."""

from collections.abc import Sequence

import numpy as np
from scipy import stats as sp_stats

from territorio.domain import (
    CorrelationDirection,
    CorrelationStats,
    CorrelationStrength,
    DecileStat,
    QuintileExtremesContrast,
    ScaleHint,
    classify_correlation_direction,
    classify_correlation_strength,
)


def _filter_valid_pairs(
    x: Sequence[float] | np.ndarray,
    y: Sequence[float] | np.ndarray,
    valid_votes: Sequence[int] | np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Applies pairwise deletion for finite `(x, y)` and `valid_votes > 0`.

    Args:
        x: Indicator numeric values.
        y: Electoral share values.
        valid_votes: Optional municipal valid vote counts.

    Returns:
        Tuple `(x_clean, y_clean)` of 1-D float64 numpy arrays.
    """
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    mask = np.isfinite(x_arr) & np.isfinite(y_arr)
    if valid_votes is not None:
        v_arr = np.asarray(valid_votes, dtype=float)
        mask = mask & np.isfinite(v_arr) & (v_arr > 0)
    return x_arr[mask], y_arr[mask]


def compute_correlation(
    x: Sequence[float] | np.ndarray,
    y: Sequence[float] | np.ndarray,
    valid_votes: Sequence[int] | np.ndarray | None = None,
    *,
    scale_hint: ScaleHint = ScaleHint.LINEAR,
) -> CorrelationStats:
    """Computes Spearman rank and Pearson linear correlation over valid pairs.

    When `scale_hint == ScaleHint.LOG` and all valid `x > 0`, Pearson `r` is
    computed over `log10(x)`.

    Args:
        x: Municipal indicator values.
        y: Municipal electoral share values.
        valid_votes: Optional municipal valid vote counts (`> 0` required).
        scale_hint: Indicator visualization scale hint.

    Returns:
        Deterministic `CorrelationStats` object.
    """
    x_valid, y_valid = _filter_valid_pairs(x, y, valid_votes)
    n_valid = int(x_valid.size)
    if n_valid < 3:
        return CorrelationStats(
            spearman_rho=0.0,
            spearman_p=1.0,
            pearson_r=0.0,
            pearson_p=1.0,
            strength=CorrelationStrength.NEGLIGIBLE,
            direction=CorrelationDirection.NEUTRAL,
            n_valid=n_valid,
        )

    # Check if either vector is constant
    if np.all(x_valid == x_valid[0]) or np.all(y_valid == y_valid[0]):
        return CorrelationStats(
            spearman_rho=0.0,
            spearman_p=1.0,
            pearson_r=0.0,
            pearson_p=1.0,
            strength=CorrelationStrength.NEGLIGIBLE,
            direction=CorrelationDirection.NEUTRAL,
            n_valid=n_valid,
        )

    sp_res = sp_stats.spearmanr(x_valid, y_valid)
    spearman_rho = float(sp_res.statistic) if np.isfinite(sp_res.statistic) else 0.0
    spearman_p = float(sp_res.pvalue) if np.isfinite(sp_res.pvalue) else 1.0

    x_for_pearson = (
        np.log10(x_valid)
        if (scale_hint == ScaleHint.LOG and np.all(x_valid > 0.0))
        else x_valid
    )
    pr_res = sp_stats.pearsonr(x_for_pearson, y_valid)
    pearson_r = float(pr_res.statistic) if np.isfinite(pr_res.statistic) else 0.0
    pearson_p = float(pr_res.pvalue) if np.isfinite(pr_res.pvalue) else 1.0

    return CorrelationStats(
        spearman_rho=spearman_rho,
        spearman_p=spearman_p,
        pearson_r=pearson_r,
        pearson_p=pearson_p,
        strength=classify_correlation_strength(spearman_rho),
        direction=classify_correlation_direction(spearman_rho),
        n_valid=n_valid,
    )


def compute_trendline(
    x: Sequence[float] | np.ndarray,
    y: Sequence[float] | np.ndarray,
    valid_votes: Sequence[int] | np.ndarray | None = None,
    *,
    scale_hint: ScaleHint = ScaleHint.LINEAR,
    num_points: int = 25,
) -> list[tuple[float, float]]:
    """Computes OLS trendline points `(x_k, y_hat_k)` between p1 and p99 of `x`.

    Fits `y = alpha + beta * log10(x)` when `scale_hint == ScaleHint.LOG` and
    `min(x) > 0`; otherwise fits `y = alpha + beta * x`.

    Args:
        x: Municipal indicator values.
        y: Municipal electoral share values.
        valid_votes: Optional municipal valid vote counts.
        scale_hint: Indicator scale hint (`linear` or `log`).
        num_points: Number of points to generate along `[p1, p99]` (default 25).

    Returns:
        List of `(x_val, y_hat)` tuples, or empty list if `n_valid < 3`.
    """
    x_valid, y_valid = _filter_valid_pairs(x, y, valid_votes)
    if x_valid.size < 3 or np.all(x_valid == x_valid[0]):
        return []

    p1, p99 = np.percentile(x_valid, [1.0, 99.0])
    if p1 == p99:
        p1, p99 = float(np.min(x_valid)), float(np.max(x_valid))
        if p1 == p99:
            return []

    use_log = scale_hint == ScaleHint.LOG and float(np.min(x_valid)) > 0.0 and p1 > 0.0
    if use_log:
        reg = sp_stats.linregress(np.log10(x_valid), y_valid)
        x_grid = np.geomspace(p1, p99, num=num_points)
        y_grid = reg.intercept + reg.slope * np.log10(x_grid)
    else:
        reg = sp_stats.linregress(x_valid, y_valid)
        x_grid = np.linspace(p1, p99, num=num_points)
        y_grid = reg.intercept + reg.slope * x_grid

    return [(float(xk), float(yk)) for xk, yk in zip(x_grid, y_grid, strict=True)]


def compute_decile_shares(
    cd_ibge: Sequence[int] | np.ndarray,
    indicator_values: Sequence[float] | np.ndarray,
    bloc_votes: Sequence[int] | np.ndarray,
    valid_votes: Sequence[int] | np.ndarray,
) -> list[DecileStat]:
    """Computes vote-weighted and unweighted shares across 10 indicator deciles.

    Municipalities are sorted deterministically by `(indicator_value, cd_ibge)`
    and partitioned into 10 groups `D_1 .. D_10` via `np.array_split`.

    Args:
        cd_ibge: Canonical 7-digit IBGE municipality codes.
        indicator_values: Municipal indicator values.
        bloc_votes: Total votes for the target ideological bloc per municipality.
        valid_votes: Total valid votes per municipality.

    Returns:
        List of 10 `DecileStat` objects (or empty list if fewer than 10 valid rows).
    """
    cd_arr = np.asarray(cd_ibge, dtype=np.int64)
    x_arr = np.asarray(indicator_values, dtype=float)
    b_arr = np.asarray(bloc_votes, dtype=np.int64)
    v_arr = np.asarray(valid_votes, dtype=np.int64)

    mask = np.isfinite(x_arr) & (v_arr > 0)
    if int(np.sum(mask)) < 10:
        return []

    cd_valid = cd_arr[mask]
    x_valid = x_arr[mask]
    b_valid = b_arr[mask]
    v_valid = v_arr[mask]

    # Deterministic tie-breaking by cd_ibge ascending, primary sort by x_valid ascending
    order = np.lexsort((cd_valid, x_valid))
    splits = np.array_split(order, 10)

    results: list[DecileStat] = []
    for idx, group_indices in enumerate(splits, start=1):
        gx = x_valid[group_indices]
        gb = b_valid[group_indices]
        gv = v_valid[group_indices]

        sum_valid = int(np.sum(gv))
        sum_bloc = int(np.sum(gb))
        weighted_share = float(sum_bloc / sum_valid) if sum_valid > 0 else 0.0
        mun_shares = gb.astype(float) / gv.astype(float)
        unweighted_mean = float(np.mean(mun_shares))

        results.append(
            DecileStat(
                decile=idx,
                municipality_count=int(group_indices.size),
                indicator_min=float(np.min(gx)),
                indicator_max=float(np.max(gx)),
                indicator_median=float(np.median(gx)),
                valid_votes=sum_valid,
                bloc_votes=sum_bloc,
                weighted_share=weighted_share,
                unweighted_mean_share=unweighted_mean,
            )
        )
    return results


def compute_extremes_contrast(
    deciles: Sequence[DecileStat],
) -> QuintileExtremesContrast | None:
    """Computes vote-weighted contrast between bottom 20% (D1+D2) and top 20% (D9+D10).

    Args:
        deciles: Sequence of 10 DecileStat objects ordered from D1 to D10.

    Returns:
        QuintileExtremesContrast if 10 deciles provided, else None.
    """
    if len(deciles) != 10:
        return None

    # Bottom 20% = D1 + D2
    d1, d2 = deciles[0], deciles[1]
    bottom_valid_votes = d1.valid_votes + d2.valid_votes
    bottom_bloc_votes = d1.bloc_votes + d2.bloc_votes
    bottom_share = (
        float(bottom_bloc_votes / bottom_valid_votes) if bottom_valid_votes > 0 else 0.0
    )
    bottom_range = (
        min(d1.indicator_min, d2.indicator_min),
        max(d1.indicator_max, d2.indicator_max),
    )
    bottom_count = d1.municipality_count + d2.municipality_count

    # Top 20% = D9 + D10
    d9, d10 = deciles[8], deciles[9]
    top_valid_votes = d9.valid_votes + d10.valid_votes
    top_bloc_votes = d9.bloc_votes + d10.bloc_votes
    top_share = float(top_bloc_votes / top_valid_votes) if top_valid_votes > 0 else 0.0
    top_range = (
        min(d9.indicator_min, d10.indicator_min),
        max(d9.indicator_max, d10.indicator_max),
    )
    top_count = d9.municipality_count + d10.municipality_count

    diff_pp = (top_share - bottom_share) * 100.0

    # Tipping point detection:
    # 1. First decile where weighted_share >= 0.50 (if crossing < 0.5 to >= 0.5)
    #    or first decile where weighted_share < 0.50 (if descending from >= 0.5)
    tipping_point_decile: int | None = None
    tipping_point_threshold: float | None = None

    for idx in range(1, len(deciles)):
        prev_share = deciles[idx - 1].weighted_share
        curr_share = deciles[idx].weighted_share
        if (prev_share < 0.50 <= curr_share) or (prev_share >= 0.50 > curr_share):
            tipping_point_decile = deciles[idx].decile
            tipping_point_threshold = deciles[idx].indicator_min
            break

    # 2. If no 50% crossing, find decile with maximum jump in share
    if tipping_point_decile is None:
        max_jump = -1.0
        for idx in range(1, len(deciles)):
            jump = abs(deciles[idx].weighted_share - deciles[idx - 1].weighted_share)
            if jump > max_jump:
                max_jump = jump
                tipping_point_decile = deciles[idx].decile
                tipping_point_threshold = deciles[idx].indicator_min

    return QuintileExtremesContrast(
        bottom_quintile_share=bottom_share,
        top_quintile_share=top_share,
        diff_pp=diff_pp,
        bottom_indicator_range=bottom_range,
        top_indicator_range=top_range,
        bottom_municipality_count=bottom_count,
        top_municipality_count=top_count,
        tipping_point_decile=tipping_point_decile,
        tipping_point_threshold=tipping_point_threshold,
    )


def compute_quantiles(
    values: Sequence[float] | np.ndarray,
    probs: Sequence[float] = (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0),
) -> list[float]:
    """Computes empirical quantiles over finite indicator values.

    Args:
        values: Numeric indicator values.
        probs: Quantile probabilities in `[0.0, 1.0]`.

    Returns:
        List of quantile values corresponding to `probs`, or empty list if no
        finite values exist.
    """
    arr = np.asarray(values, dtype=float)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return []
    q = np.quantile(finite, probs)
    return [float(val) for val in q]
