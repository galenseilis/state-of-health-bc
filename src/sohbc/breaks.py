"""Formal change-point detection and trend testing for indicator series.

The descriptive trajectory summary in :mod:`sohbc.indicators` reports a
single best split by eye; this module supplies the formal tests milestone
M3 calls for, so every series can be labelled stationary or not and its
regimes dated with stated uncertainty.

Method
------
* **Segmentation.** The series is modelled as piecewise linear (a trend
  break changes the slope): the optimal segmentation for a given number
  of breaks is found with the dynamic-programming solver of ``ruptures``
  [@truong2020selective], using its ``linear`` cost — the residual sum of
  squares of a straight-line fit within each segment.
* **Number of breaks.** Chosen by BIC over 0..``max_breaks`` regimes,
  each extra break paying for two regression parameters plus the break
  location. This avoids an arbitrary penalty scale: the penalty is
  derived from the likelihood, not tuned.
* **Is there a break at all?** A permutation test against a single linear
  trend. The statistic is the reduction in residual sum of squares from
  the best split; the null distribution resamples the residuals of the
  global linear fit (preserving the trend, destroying any break). This
  tests "no break beyond a straight line", which is exactly the null the
  trajectory summary assumes away.
* **Trend/stationarity.** Kendall's tau on (year, value) gives a
  rank-based monotone-trend test; a series is labelled nonstationary when
  either test is significant, and the reasons are recorded.

All randomness is seeded, so published results reproduce exactly.
"""

from __future__ import annotations

import itertools
import random
from typing import Any

import numpy as np
import ruptures as rpt
from scipy import stats

#: Minimum points per segment; slopes over fewer points are unstable.
MIN_SEGMENT = 5

#: Default cap on the number of breaks considered.
MAX_BREAKS = 4

#: Default permutation count for the single-break test (odd, so the
#: p-value grid is symmetric around the observed statistic).
N_PERMUTATIONS = 1999

#: Default seed: published p-values must not move between rebuilds.
SEED = 20241018

SIGNIFICANCE = 0.05


class BreakError(ValueError):
    """Raised when a series cannot be tested for change points."""


def _arrays(points: list[tuple[float, float]]) -> tuple[np.ndarray, np.ndarray]:
    if len(points) < 2:
        raise BreakError("need at least two points to test for a break")
    ordered = sorted(points)
    x = np.array([float(px) for px, _ in ordered], dtype=float)
    y = np.array([float(py) for _, py in ordered], dtype=float)
    if np.all(x == x[0]):
        raise BreakError("cannot test a series with a single distinct year")
    return x, y


def _design(x: np.ndarray) -> np.ndarray:
    """Covariates for a straight-line fit: intercept and time index."""
    return np.column_stack([np.ones_like(x), x])


def _sse(y: np.ndarray, x: np.ndarray) -> float:
    """Residual sum of squares of a straight-line fit through ``(x, y)``."""
    residuals = y - _design(x) @ np.linalg.lstsq(_design(x), y, rcond=None)[0]
    return float(residuals @ residuals)


def _segment_sse(slices: list[np.ndarray], y: np.ndarray, x: np.ndarray) -> float:
    return sum(_sse(y[s], x[s]) for s in slices)


def _segmentation_arrays(
    x: np.ndarray, y: np.ndarray, n_breaks: int, min_segment: int
) -> list[int]:
    """End indices of the optimal piecewise-linear segmentation.

    The returned indices are segment ends (exclusive), the last always
    ``len(x)``; the regime that begins at index ``i`` therefore starts in
    year ``x[i]``.
    """
    signal = np.column_stack([y, _design(x)])
    breakpoints = rpt.Dynp(model="linear", min_size=min_segment, jump=1)
    breakpoints.fit(signal)
    return list(breakpoints.predict(n_bkps=n_breaks))


def _regime_years(x: np.ndarray, end_indices: list[int]) -> list[int]:
    """First year of each regime after the first, given segment ends."""
    return [int(x[end]) for end in end_indices[:-1]]


def _slices(end_indices: list[int]) -> list[np.ndarray]:
    bounds = [0, *end_indices]
    return [np.arange(start, end) for start, end in itertools.pairwise(bounds)]


def select_breaks(
    points: list[tuple[float, float]],
    min_segment: int = MIN_SEGMENT,
    max_breaks: int = MAX_BREAKS,
) -> dict[str, Any]:
    """Date the regimes of a series by BIC-selected piecewise-linear fit.

    Args:
        points: ``(x, y)`` pairs, typically ``(year, value)``.
        min_segment: Minimum points per regime.
        max_breaks: Largest number of breaks to consider.

    Returns:
        dict: The break years of the best segmentation, its residual sum
        of squares, the number of segments, and the BIC comparison table
        for every candidate number of breaks.
    """
    x, y = _arrays(points)
    n = len(x)
    feasible = max(0, n // min_segment - 1)
    limit = min(max_breaks, feasible)
    zero_breaks_sse = _sse(y, x)
    candidates = []
    best: tuple[float, int, list[int], float] = (
        float("inf"),
        0,
        [],
        zero_breaks_sse,
    )
    for n_breaks in range(limit + 1):
        if n_breaks == 0:
            sse = zero_breaks_sse
            ends: list[int] = []
        else:
            ends = _segmentation_arrays(x, y, n_breaks, min_segment)
            sse = _segment_sse(_slices(ends), y, x)
        # Two regression parameters per segment, plus one per break location.
        parameters = 2 * (n_breaks + 1) + n_breaks
        bic = n * np.log(max(sse, 1e-12) / n) + parameters * np.log(n)
        candidates.append(
            {
                "n_breaks": n_breaks,
                "years": _regime_years(x, ends),
                "sse": round(sse, 6),
                "bic": round(float(bic), 4),
            }
        )
        if bic < best[0]:
            best = (float(bic), n_breaks, ends, sse)
    _, n_breaks, ends, sse = best
    return {
        "method": "piecewise-linear segmentation (ruptures Dynp), BIC over K",
        "min_segment": min_segment,
        "max_breaks_considered": limit,
        "n_breaks": n_breaks,
        "years": _regime_years(x, ends),
        "sse": round(sse, 6),
        "bic": round(float(best[0]), 4),
        "candidates": candidates,
    }


def _best_split_reduction(x: np.ndarray, y: np.ndarray, min_segment: int) -> float:
    """Largest drop in residual sum of squares from splitting the series."""
    baseline = _sse(y, x)
    best = 0.0
    for split in range(min_segment, len(y) - min_segment + 1):
        sse = _sse(y[:split], x[:split]) + _sse(y[split:], x[split:])
        best = max(best, baseline - sse)
    return best


def single_break_test(
    points: list[tuple[float, float]],
    min_segment: int = MIN_SEGMENT,
    n_permutations: int = N_PERMUTATIONS,
    seed: int = SEED,
) -> dict[str, Any]:
    """Permutation test of "a straight line, no break" against one break.

    The null model is the global straight-line fit. Its residuals are
    resampled (without replacement) onto the fitted trend, so each
    replicate keeps the trend and loses any break; the p-value is the
    share of replicates whose best split reduces the residual sum of
    squares by at least as much as the observed series.

    Args:
        points: ``(x, y)`` pairs, typically ``(year, value)``.
        min_segment: Minimum points per side of the split.
        n_permutations: Number of residual resamples.
        seed: Seed for the resampling, so results are reproducible.

    Returns:
        dict: The observed statistic, the p-value, and the year of the
        best split.
    """
    x, y = _arrays(points)
    if n_permutations < 1:
        raise BreakError("need at least one permutation")
    coefficients = np.linalg.lstsq(_design(x), y, rcond=None)[0]
    trend = _design(x) @ coefficients
    residuals = y - trend
    observed = _best_split_reduction(x, y, min_segment)
    observed_year = None
    best = float("inf")
    for split in range(min_segment, len(y) - min_segment + 1):
        sse = _sse(y[:split], x[:split]) + _sse(y[split:], x[split:])
        if sse < best:
            best = sse
            observed_year = int(x[split])

    generator = random.Random(seed)  # nosec B311
    exceedances = 0
    pool = [float(residual) for residual in residuals]
    for _ in range(n_permutations):
        generator.shuffle(pool)
        replicate = trend + np.array(pool, dtype=float)
        if _best_split_reduction(x, replicate, min_segment) >= observed:
            exceedances += 1
    p_value = (1 + exceedances) / (1 + n_permutations)
    return {
        "method": "residual-permutation test (H0: one straight line)",
        "statistic_sse_reduction": round(observed, 6),
        "n_permutations": n_permutations,
        "seed": seed,
        "p_value": round(p_value, 4),
        "significant": bool(p_value < SIGNIFICANCE),
        "change_point": observed_year,
    }


def slope_change_test(
    points: list[tuple[float, float]],
    change_point: float,
) -> dict[str, Any]:
    """Chow-style F-test of equal slopes either side of a change point.

    The unrestricted model fits a separate straight line to each side of
    ``change_point``; the restricted model fits one straight line to the
    whole series. The F statistic compares the residual sums of squares:
    ``F = ((SSE_r - SSE_u) / 1) / (SSE_u / (n - 4))``, with 1 and ``n - 4``
    degrees of freedom — one slope difference, four estimated parameters
    (two intercepts, two slopes).

    This turns the descriptive within-versus-across decomposition into a
    test: the within-regime *rates* differ when this F is significant, so
    the break changed the pace of movement rather than the level.

    Args:
        points: ``(x, y)`` pairs, typically ``(year, value)``.
        change_point: The year separating the two regimes; the first
            regime is ``x < change_point``, the second ``x >= change_point``.

    Returns:
        dict: The F statistic, its p-value, degrees of freedom, both
        residual sums of squares, and whether the slope change is
        significant.
    """
    x, y = _arrays(points)
    if np.all(x < change_point) or np.all(x >= change_point):
        raise BreakError("change point leaves one regime empty")
    first = x < change_point
    second = ~first
    if first.sum() < 2 or second.sum() < 2:
        raise BreakError("need at least two points on each side of the break")
    sse_restricted = _sse(y, x)
    sse_unrestricted = _sse(y[first], x[first]) + _sse(y[second], x[second])
    n = len(x)
    df_residual = n - 4
    if df_residual <= 0:
        raise BreakError("need at least five points to test a slope change")
    numerator = (sse_restricted - sse_unrestricted) / 1
    denominator = sse_unrestricted / df_residual
    if denominator == 0:
        f_statistic = float("inf") if numerator > 0 else 0.0
        p_value = 0.0 if numerator > 0 else 1.0
    else:
        f_statistic = float(numerator / denominator)
        p_value = float(stats.f.sf(f_statistic, 1, df_residual))
    return {
        "method": "Chow-style F-test for a slope change at a known break",
        "change_point": int(change_point),
        "f_statistic": round(f_statistic, 4),
        "df": [1, df_residual],
        "sse_restricted": round(sse_restricted, 6),
        "sse_unrestricted": round(sse_unrestricted, 6),
        "p_value": round(p_value, 6),
        "significant": bool(p_value < SIGNIFICANCE),
    }


def trend_test(points: list[tuple[float, float]]) -> dict[str, Any]:
    """Kendall's tau test for a monotone trend in the series.

    Args:
        points: ``(x, y)`` pairs, typically ``(year, value)``.

    Returns:
        dict: Tau, its p-value, and whether the trend is significant.
    """
    x, y = _arrays(points)
    result = stats.kendalltau(x, y)
    tau = float(result.statistic)
    p_value = float(result.pvalue)
    return {
        "method": "Kendall tau (rank-based monotone trend)",
        "tau": round(tau, 4),
        "p_value": round(p_value, 6),
        "significant": bool(p_value < SIGNIFICANCE),
    }


def summarise(
    points: list[tuple[float, float]],
    min_segment: int = MIN_SEGMENT,
    max_breaks: int = MAX_BREAKS,
    n_permutations: int = N_PERMUTATIONS,
    seed: int = SEED,
) -> dict[str, Any]:
    """Test a series for breaks and trend, and state its stationarity.

    Args:
        points: ``(x, y)`` pairs, typically ``(year, value)``.
        min_segment: Minimum points per regime.
        max_breaks: Largest number of breaks to consider.
        n_permutations: Number of residual resamples in the break test.
        seed: Seed for the resampling, so results are reproducible.

    Returns:
        dict: ``breaks``, ``break_test``, ``trend_test``, and a
        ``stationarity`` verdict with its reasons.
    """
    _, y = _arrays(points)
    if len(y) < 2 * min_segment:
        return {
            "breaks": None,
            "break_test": None,
            "trend_test": trend_test(points),
            "stationarity": {
                "verdict": "undetermined",
                "reasons": [
                    (
                        f"series has {len(y)} points; at least "
                        f"{2 * min_segment} are needed for two regimes"
                    )
                ],
            },
        }
    breaks = select_breaks(points, min_segment=min_segment, max_breaks=max_breaks)
    break_test = single_break_test(
        points, min_segment=min_segment, n_permutations=n_permutations, seed=seed
    )
    trend = trend_test(points)
    reasons = []
    if trend["significant"]:
        reasons.append(
            f"monotone trend (Kendall tau={trend['tau']}, p={trend['p_value']})"
        )
    if break_test["significant"]:
        reasons.append(
            f"break beyond a straight line (permutation test, "
            f"p={break_test['p_value']})"
        )
    verdict = "nonstationary" if reasons else "stationary"
    if not reasons:
        reasons.append("no significant trend or break over the observed window")
    return {
        "breaks": breaks,
        "break_test": break_test,
        "trend_test": trend,
        "stationarity": {"verdict": verdict, "reasons": reasons},
    }
