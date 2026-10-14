"""Unit tests for bivariate correlation, trendline, deciles, and quantiles."""

import numpy as np
import pytest

from territorio.analytics.stats import (
    compute_correlation,
    compute_decile_shares,
    compute_extremes_contrast,
    compute_quantiles,
    compute_trendline,
)
from territorio.domain import (
    CorrelationDirection,
    CorrelationStrength,
    ScaleHint,
)


def test_compute_correlation_linear_and_log_scales() -> None:
    """Verifies Spearman and Pearson correlation with pairwise deletion and log."""
    x = [10.0, 100.0, 1000.0, 10000.0, 100000.0, float("nan")]
    y = [0.1, 0.2, 0.3, 0.4, 0.5, 0.9]
    votes = [100, 200, 300, 400, 500, 600]

    res = compute_correlation(x, y, votes, scale_hint=ScaleHint.LOG)
    assert res.n_valid == 5
    assert res.spearman_rho == pytest.approx(1.0)
    assert res.pearson_r == pytest.approx(1.0)
    assert res.strength == CorrelationStrength.VERY_STRONG
    assert res.direction == CorrelationDirection.POSITIVE

    # Small sample (< 3) returns negligible neutral correlation
    small = compute_correlation([1.0, 2.0], [0.2, 0.4])
    assert small.n_valid == 2
    assert small.strength == CorrelationStrength.NEGLIGIBLE
    assert small.direction == CorrelationDirection.NEUTRAL

    # Constant vector returns 0.0 safely
    const = compute_correlation([5.0, 5.0, 5.0, 5.0], [0.1, 0.2, 0.3, 0.4])
    assert const.spearman_rho == 0.0


def test_compute_trendline_linear_and_log() -> None:
    """Verifies 25-point OLS trendline generation on linear and log scales."""
    x = np.geomspace(10.0, 10000.0, num=40)
    y = 0.1 + 0.15 * np.log10(x)

    pts_log = compute_trendline(x, y, scale_hint=ScaleHint.LOG, num_points=25)
    assert len(pts_log) == 25
    assert pts_log[0][0] < pts_log[-1][0]
    assert pts_log[0][1] < pts_log[-1][1]

    pts_lin = compute_trendline(x, y, scale_hint=ScaleHint.LINEAR, num_points=25)
    assert len(pts_lin) == 25

    assert compute_trendline([1.0, 2.0], [0.1, 0.2]) == []


def test_compute_decile_shares_weighted_vs_unweighted_and_tie_breaking() -> None:
    """Proves `weighted_share != unweighted_mean_share` when electorate sizes differ."""
    # 20 municipalities: 2 per decile
    cd_ibge = list(range(3500001, 3500021))
    indicator_vals = [float(i // 2) for i in range(20)]  # Tied pairs!
    valid_votes = [1000] * 20
    bloc_votes = [200] * 20  # 20% share in most municipalities

    # In decile 10 (indices 18 and 19):
    # Municipality 18 has 1,000 valid votes and 100 bloc votes (10% share)
    # Municipality 19 (metropolis) has 999,000 valid votes and 899,900 bloc votes
    valid_votes[18] = 1000
    bloc_votes[18] = 100
    valid_votes[19] = 999000
    bloc_votes[19] = 899900

    deciles = compute_decile_shares(
        cd_ibge=cd_ibge,
        indicator_values=indicator_vals,
        bloc_votes=bloc_votes,
        valid_votes=valid_votes,
    )
    assert len(deciles) == 10
    d10 = deciles[-1]
    assert d10.decile == 10
    assert d10.municipality_count == 2
    assert d10.valid_votes == 1_000_000
    assert d10.bloc_votes == 900_000
    assert d10.weighted_share == pytest.approx(0.90)
    # Unweighted mean is (0.10 + 899900/999000) / 2 ~= 0.5004
    assert d10.unweighted_mean_share == pytest.approx((0.10 + 899900 / 999000) / 2)
    assert d10.weighted_share != pytest.approx(d10.unweighted_mean_share)

    # Fewer than 10 valid rows returns empty list
    assert compute_decile_shares([1, 2], [1.0, 2.0], [1, 1], [2, 2]) == []


def test_compute_quantiles() -> None:
    """Verifies empirical quantile calculation ignoring NaNs."""
    vals = [0.0, 10.0, 20.0, 30.0, 40.0, float("nan")]
    q = compute_quantiles(vals, probs=(0.0, 0.5, 1.0))
    assert q == [0.0, 20.0, 40.0]
    assert compute_quantiles([float("nan")]) == []


def test_compute_extremes_contrast() -> None:
    """Verifies quintile extremes contrast (Q1 vs Q5) and tipping point."""
    cd_ibge = list(range(3500001, 3500021))
    indicator_vals = [float(i) for i in range(20)]
    valid_votes = [1000] * 20
    # Votes cross 50% around middle index
    bloc_votes = [100 + i * 40 for i in range(20)]

    deciles = compute_decile_shares(
        cd_ibge=cd_ibge,
        indicator_values=indicator_vals,
        bloc_votes=bloc_votes,
        valid_votes=valid_votes,
    )
    contrast = compute_extremes_contrast(deciles)
    assert contrast is not None
    assert contrast.bottom_municipality_count == 4  # D1 (2) + D2 (2)
    assert contrast.top_municipality_count == 4  # D9 (2) + D10 (2)
    assert contrast.bottom_quintile_share < contrast.top_quintile_share
    assert contrast.diff_pp > 0.0
    assert contrast.tipping_point_decile is not None

    # Invalid length returns None
    assert compute_extremes_contrast([]) is None
    assert compute_extremes_contrast(deciles[:5]) is None
