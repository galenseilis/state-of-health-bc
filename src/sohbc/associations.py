"""Association and temporal-stability analysis for milestone M4.

M4 asks which candidate variables are statistically dependent with BC
health outcomes, with a hard constraint that milestone M3 made
non-negotiable: **stability before pooling**. A single pooled association
is only reported when the relationship is supported as stable over the
analysis window; otherwise the time-varying estimates *are* the result.

Method
------
* **Association.** For a paired outcome/determinant series the module
  reports Pearson and Spearman correlation and an ordinary-least-squares
  slope with its standard error and t p-value. Correlations are rank- and
  moment-based; the slope carries units and is the quantity that can be
  compared against a stated estimation window.
* **Stability.** The relationship is re-estimated on (a) contiguous
  subperiods and (b) rolling windows of a fixed width. A pooled estimate
  is deemed stable when subperiod estimates agree in sign and their
  dispersion is small relative to the pooled magnitude — an explicit,
  inspectable rule rather than a single significance flag.
* **Regime awareness.** If a series carries dated breaks (from
  :mod:`sohbc.breaks`), the association is re-estimated within each regime
  as well, so a pooled number is not reported across a known rule change.

All estimates state the window they were estimated on, per M4's
acceptance criteria.
"""

from __future__ import annotations

import csv
import itertools
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

#: Minimum paired points before any association is estimated.
MIN_POINTS = 5

#: Minimum points for a subperiod/rolling-window estimate to count.
MIN_WINDOW = 5

#: Default rolling-window width (in periods) for the stability sweep.
ROLLING_WINDOW = 8

#: A pooled estimate is stable only if subperiod slopes stay this close
#: to the pooled slope, expressed as a fraction of its magnitude.
STABILITY_TOLERANCE = 0.5

SIGNIFICANCE = 0.05


class AssociationError(ValueError):
    """Raised when a pair of series cannot be associated."""


def read_series(
    path: Path,
    characteristic: str | None = None,
    measure: str | None = None,
    sex: str = "Both sexes",
    age_group: str | None = None,
) -> list[tuple[float, float]]:
    """Read one ``(period, value)`` series from a published tidy CSV.

    Published indicator CSVs are tidy: one row per
    ``(ref_date, geo, age_group, sex, characteristic, measure)``. A single
    series is selected by characteristic, measure, sex, and (optionally)
    age group; rows with a missing value or an ``E`` flag are dropped,
    since Statistics Canada marks those "too unreliable to publish".

    Mortality and life-table files carry the metric in ``characteristic``;
    the survey family carries it in ``measure`` with ``characteristic``
    fixed at ``"Percent"``. Both are accepted.

    Args:
        path: Path to a published indicator CSV.
        characteristic: Characteristic to select, if the metric lives there.
        measure: Measure to select, if the metric lives there.
        sex: Sex category to select.
        age_group: Age group to select, if the file is age-resolved.

    Returns:
        list[tuple[float, float]]: ``(year, value)`` pairs, sorted by year.

    Raises:
        AssociationError: If the file is missing or selects no rows.
    """
    if not path.is_file():
        raise AssociationError(f"published series not found: {path}")
    pairs: dict[float, float] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("sex") != sex:
                continue
            if characteristic is not None and row.get("characteristic") != characteristic:
                continue
            if measure is not None and row.get("measure") != measure:
                continue
            if age_group is not None and row.get("age_group") != age_group:
                continue
            if not row.get("value") or row.get("status") == "E":
                continue
            pairs[float(row["ref_date"])] = float(row["value"])
    if not pairs:
        raise AssociationError(
            f"no rows selected in {path} for characteristic={characteristic!r} "
            f"measure={measure!r} sex={sex!r} age_group={age_group!r}"
        )
    return sorted(pairs.items())


def _paired(
    outcome: list[tuple[float, float]],
    determinant: list[tuple[float, float]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Align two (period, value) series on their shared periods."""
    first = {float(period): float(value) for period, value in outcome}
    second = {float(period): float(value) for period, value in determinant}
    shared = sorted(set(first) & set(second))
    if len(shared) < MIN_POINTS:
        raise AssociationError(
            f"need at least {MIN_POINTS} shared periods to associate, found {len(shared)}"
        )
    periods = np.array(shared, dtype=float)
    y = np.array([first[period] for period in shared], dtype=float)
    x = np.array([second[period] for period in shared], dtype=float)
    return periods, y, x


def _ols(x: np.ndarray, y: np.ndarray) -> dict[str, float]:
    """Ordinary least squares of ``y`` on ``x`` with a t-test on the slope."""
    n = len(x)
    mean_x = float(x.mean())
    mean_y = float(y.mean())
    sxx = float(((x - mean_x) ** 2).sum())
    if sxx == 0:
        raise AssociationError("determinant has no variation over the window")
    slope = float(((x - mean_x) * (y - mean_y)).sum() / sxx)
    intercept = mean_y - slope * mean_x
    residual = y - (intercept + slope * x)
    dof = n - 2
    if dof <= 0:
        return {
            "slope": slope,
            "intercept": intercept,
            "std_error": float("nan"),
            "t_statistic": float("nan"),
            "p_value": float("nan"),
        }
    sse = float((residual**2).sum())
    variance = sse / dof
    std_error = float(np.sqrt(variance / sxx)) if variance > 0 else 0.0
    if std_error == 0:
        t_statistic = float("inf") if slope != 0 else 0.0
        p_value = 0.0 if slope != 0 else 1.0
    else:
        t_statistic = slope / std_error
        p_value = float(2 * stats.t.sf(abs(t_statistic), dof))
    return {
        "slope": slope,
        "intercept": intercept,
        "std_error": std_error,
        "t_statistic": float(t_statistic),
        "p_value": p_value,
    }


def associate(
    outcome: list[tuple[float, float]],
    determinant: list[tuple[float, float]],
) -> dict[str, Any]:
    """Pooled association between a health outcome and a determinant.

    Args:
        outcome: The health series as ``(period, value)`` pairs.
        determinant: The candidate variable as ``(period, value)`` pairs.

    Returns:
        dict: Pearson and Spearman correlation with p-values, the OLS
        slope with its standard error and p-value, and the estimation
        window (first and last shared period, and the count).
    """
    periods, y, x = _paired(outcome, determinant)
    pearson = stats.pearsonr(x, y)
    spearman = stats.spearmanr(x, y)
    fit = _ols(x, y)
    return {
        "window": {
            "start": int(periods[0]),
            "end": int(periods[-1]),
            "n": len(periods),
        },
        "pearson": {
            "r": round(float(pearson.statistic), 4),
            "p_value": round(float(pearson.pvalue), 6),
        },
        "spearman": {
            "rho": round(float(spearman.statistic), 4),
            "p_value": round(float(spearman.pvalue), 6),
        },
        "ols": {
            "slope": round(fit["slope"], 6),
            "intercept": round(fit["intercept"], 6),
            "std_error": round(fit["std_error"], 6),
            "t_statistic": round(fit["t_statistic"], 4),
            "p_value": round(fit["p_value"], 6),
            "significant": bool(fit["p_value"] < SIGNIFICANCE),
        },
    }


def _subperiods(
    periods: np.ndarray, n: int
) -> list[tuple[int, int]]:
    """Split ``range(len(periods))`` into ``n`` contiguous index runs."""
    bounds = np.linspace(0, len(periods), n + 1).round().astype(int)
    runs: list[tuple[int, int]] = []
    for start, end in itertools.pairwise(bounds):
        if end - start >= MIN_WINDOW:
            runs.append((int(start), int(end)))
    return runs


def stability(
    outcome: list[tuple[float, float]],
    determinant: list[tuple[float, float]],
    n_subperiods: int = 3,
    window: int = ROLLING_WINDOW,
) -> dict[str, Any]:
    """Estimate the association across subperiods and rolling windows.

    A pooled estimate is only reported as stable when every subperiod
    estimate agrees in sign with the pooled slope and stays within
    ``STABILITY_TOLERANCE`` of it. Otherwise the time-varying estimates
    are the result and the reason is recorded.

    Args:
        outcome: The health series as ``(period, value)`` pairs.
        determinant: The candidate variable as ``(period, value)`` pairs.
        n_subperiods: Number of contiguous subperiods to split into.
        window: Width, in periods, of each rolling estimate.

    Returns:
        dict: The pooled association, the subperiod and rolling estimates,
        a stability verdict, and the reasons behind it.
    """
    periods, y, x = _paired(outcome, determinant)
    pooled = associate(outcome, determinant)
    pooled_slope = pooled["ols"]["slope"]

    subperiod_estimates: list[dict[str, Any]] = []
    for start, end in _subperiods(periods, n_subperiods):
        fit = _ols(x[start:end], y[start:end])
        subperiod_estimates.append(
            {
                "start": int(periods[start]),
                "end": int(periods[end - 1]),
                "n": end - start,
                "slope": round(fit["slope"], 6),
                "p_value": round(fit["p_value"], 6),
            }
        )

    rolling_estimates: list[dict[str, Any]] = []
    for start in range(len(periods) - window + 1):
        end = start + window
        fit = _ols(x[start:end], y[start:end])
        rolling_estimates.append(
            {
                "start": int(periods[start]),
                "end": int(periods[end - 1]),
                "n": window,
                "slope": round(fit["slope"], 6),
                "p_value": round(fit["p_value"], 6),
            }
        )

    reasons: list[str] = []
    if len(subperiod_estimates) < 2:
        reasons.append(
            "series too short to split into two testable subperiods"
        )
    signs = {np.sign(est["slope"]) for est in subperiod_estimates if est["slope"] != 0}
    if len(signs) > 1:
        reasons.append("subperiod estimates disagree in sign")
    if pooled_slope != 0 and len(subperiod_estimates) > 1:
        spread = max(abs(est["slope"] - pooled_slope) for est in subperiod_estimates)
        spread_ratio = spread / abs(pooled_slope)
        if spread_ratio > STABILITY_TOLERANCE:
            reasons.append(
                f"subperiod slopes stray up to {spread_ratio:.2f} of the pooled slope"
            )
    stable = not reasons
    verdict = "stable" if stable else "time-varying"
    if reasons and reasons[0].startswith("series too short"):
        verdict = "undetermined"
    return {
        "pooled": pooled,
        "subperiods": subperiod_estimates,
        "rolling": rolling_estimates,
        "rolling_window": window,
        "stability": {
            "stable": bool(stable),
            "tolerance": STABILITY_TOLERANCE,
            "verdict": verdict,
            "reasons": reasons,
            "interpretation": (
                "stable = one pooled estimate is defensible over the window; "
                "time-varying = report the subperiod/rolling estimates instead; "
                "undetermined = too few points to test stability"
            ),
        },
    }


def within_regime(
    outcome: list[tuple[float, float]],
    determinant: list[tuple[float, float]],
    regime_years: list[int],
) -> list[dict[str, Any]]:
    """Re-estimate the association inside each dated regime.

    A pooled association that spans a known rule change is not reported
    naively; this splits the shared window at ``regime_years`` and
    estimates the relationship separately in each regime.

    Args:
        outcome: The health series as ``(period, value)`` pairs.
        determinant: The candidate variable as ``(period, value)`` pairs.
        regime_years: First year of each regime after the first.

    Returns:
        list[dict]: One association per regime, each stating its window.
    """
    periods, y, x = _paired(outcome, determinant)
    bounds = [0]
    for year in sorted(regime_years):
        if periods[0] < year <= periods[-1]:
            bounds.append(int(np.searchsorted(periods, year, side="left")))
    bounds.append(len(periods))

    estimates: list[dict[str, Any]] = []
    for index, (start, end) in enumerate(itertools.pairwise(bounds)):
        if end - start < MIN_POINTS:
            continue
        subset_outcome = [
            (float(periods[i]), float(y[i])) for i in range(start, end)
        ]
        subset_determinant = [
            (float(periods[i]), float(x[i])) for i in range(start, end)
        ]
        estimate = associate(subset_outcome, subset_determinant)
        estimate["regime"] = index + 1
        estimates.append(estimate)
    return estimates


#: Candidate outcome/determinant pairs drawn from the published indicator
#: family. Each names the published CSV and the row filter that selects one
#: series. These are the associations M4 characterises first; determinants
#: outside the fetched family join as their catalogue sources are built.
CANDIDATE_PAIRS: dict[str, dict[str, Any]] = {
    "life_expectancy_by_daily_smoking": {
        "domain": "behavioural",
        "title": "Life expectancy at birth vs daily smoking prevalence",
        "outcome": {
            "file": "life_expectancy_bc.csv",
            "characteristic": "Life expectancy (in years) at age x (ex)",
            "age_group": "0 years",
        },
        "determinant": {
            "file": "smoker_daily_bc.csv",
            "measure": "Current smoker, daily",
        },
        "caveat": "Ecological, annual, province-level; not individual-level.",
    },
    "life_expectancy_by_mood_disorder": {
        "domain": "mental_health",
        "title": "Life expectancy at birth vs mood-disorder prevalence",
        "outcome": {
            "file": "life_expectancy_bc.csv",
            "characteristic": "Life expectancy (in years) at age x (ex)",
            "age_group": "0 years",
        },
        "determinant": {
            "file": "mood_disorder_bc.csv",
            "measure": "Mood disorder",
        },
        "caveat": "Ecological, annual, province-level; not individual-level.",
    },
    "diabetes_by_daily_smoking": {
        "domain": "behavioural",
        "title": "Diabetes prevalence vs daily smoking prevalence",
        "outcome": {
            "file": "diabetes_bc.csv",
            "measure": "Diabetes",
        },
        "determinant": {
            "file": "smoker_daily_bc.csv",
            "measure": "Current smoker, daily",
        },
        "caveat": "Ecological, annual, province-level; not individual-level.",
    },
    "life_satisfaction_by_sense_of_belonging": {
        "domain": "social",
        "title": "Life satisfaction vs sense of community belonging",
        "outcome": {
            "file": "life_satisfaction_bc.csv",
            "measure": "Life satisfaction, satisfied or very satisfied",
        },
        "determinant": {
            "file": "sense_of_belonging_bc.csv",
            "measure": "Sense of belonging to local community, somewhat strong or very strong",
        },
        "caveat": "Ecological, annual, province-level; not individual-level.",
    },
}


def build_association(key: str) -> dict[str, Any]:
    """Estimate and publish the association named by ``key``.

    Loads the paired series from the published tidy CSVs, runs the pooled
    association and the stability analysis, and writes a JSON record that
    states each estimate's window and stability verdict.

    Args:
        key: A key of :data:`CANDIDATE_PAIRS`.

    Returns:
        dict: The written path and the analysis payload.

    Raises:
        AssociationError: If the key is unknown.
    """
    import json

    from .indicators import PUBLISHED_DIR

    if key not in CANDIDATE_PAIRS:
        raise AssociationError(f"unknown association: {key}")
    spec = CANDIDATE_PAIRS[key]
    outcome_spec = spec["outcome"]
    determinant_spec = spec["determinant"]
    outcome = read_series(
        PUBLISHED_DIR / outcome_spec["file"],
        outcome_spec.get("characteristic"),
        measure=outcome_spec.get("measure"),
        sex=outcome_spec.get("sex", "Both sexes"),
        age_group=outcome_spec.get("age_group"),
    )
    determinant = read_series(
        PUBLISHED_DIR / determinant_spec["file"],
        determinant_spec.get("characteristic"),
        measure=determinant_spec.get("measure"),
        sex=determinant_spec.get("sex", "Both sexes"),
        age_group=determinant_spec.get("age_group"),
    )
    result = stability(outcome, determinant)
    result["key"] = key
    result["domain"] = spec["domain"]
    result["title"] = spec["title"]
    result["caveat"] = spec.get("caveat", "")
    result["outcome"] = outcome_spec
    result["determinant"] = determinant_spec
    output = PUBLISHED_DIR / f"association_{key}.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return {"key": key, "output": output, "result": result}
