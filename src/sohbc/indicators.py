"""Indicator definitions and the build step that turns raw tables into
published, tidy datasets under data/published/."""

from __future__ import annotations

import csv
import io
import itertools
import json
import re
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import requests

from . import breaks
from .catalogue import ROOT
from .fetch import RAW_DIR, TIMEOUT, USER_AGENT

PUBLISHED_DIR = ROOT / "data" / "published"
REFERENCE_DIR = ROOT / "data" / "reference"

STANDARD_FIELDS = ["ref_date", "characteristic", "value", "uom", "standard"]
REFERENCE_DIR = ROOT / "data" / "reference"

ALL_AGES = "Age at time of death, all ages"

INDICATORS: dict[str, dict[str, Any]] = {
    "mortality_rates_bc": {
        "title": "Mortality rates, British Columbia",
        "domain": "Mortality",
        "source_key": "statcan_wds",
        "source_table": "13-10-0710-01",
        "source_table_url": "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1310071001",
        "geo": "British Columbia, place of residence",
        "age_group": None,
        "sex": "Both sexes",
        "all_ages": "Age at time of death, all ages",
        "output": PUBLISHED_DIR / "mortality_rates_bc.csv",
        "standard_population": REFERENCE_DIR / "who_standard_population.csv",
        "standard_name": "WHO World Standard Population (2000-2025)",
        "trajectory_characteristic": "Mortality rate per 1,000 population",
        "definition": (
            "Deaths and the crude mortality rate (deaths per 1,000 population), "
            "all ages, both sexes, resident in British Columbia, plus an "
            "age-standardised rate using the WHO World Standard Population."
        ),
        "caveats": (
            "Crude rate: not adjusted to a standard population, so it reflects "
            "both real change and shifts in the age structure of the population. "
            "Recent years include the COVID-19 period."
        ),
    },
}

TIDY_FIELDS = [
    "ref_date",
    "geo",
    "age_group",
    "sex",
    "characteristic",
    "value",
    "uom",
    "status",
]


class IndicatorError(ValueError):
    """Raised when an indicator cannot be built."""


def wds_download_json(source_key: str) -> Path:
    return RAW_DIR / source_key / "13100710-download.json"


def wds_zip_url(manifest_path: Path) -> str:
    """Read a WDS download JSON and return the full-table zip URL."""
    if not manifest_path.exists():
        raise IndicatorError(
            f"missing WDS download JSON: {manifest_path}. Run "
            f"'python -m sohbc fetch <source>' first."
        )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    url = payload.get("object")
    if not url:
        raise IndicatorError(f"no download URL in {manifest_path}: {payload!r}")
    return url


def fetch_wds_zip(url: str) -> bytes:
    response = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.content


def table_rows(zip_bytes: bytes, table_id: str) -> list[dict[str, str]]:
    """Return rows from the data CSV inside a WDS full-table zip."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        member = next(
            (
                name
                for name in archive.namelist()
                if name.endswith(".csv") and "_MetaData" not in name
            ),
            None,
        )
        if member is None:
            raise IndicatorError(f"no data CSV in WDS archive for table {table_id}")
        raw = archive.read(member).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(raw)))


def select_rows(
    rows: list[dict[str, str]],
    geo: str,
    age_group: str | None,
    sex: str | None,
) -> list[dict[str, str]]:
    selected = []
    for row in rows:
        if row.get("GEO") != geo:
            continue
        if age_group is not None and row.get("Age at time of death") != age_group:
            continue
        if sex is not None and row.get("Sex") != sex:
            continue
        if not row.get("VALUE"):
            continue
        selected.append(row)
    return selected


def tidy(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    tidy_rows: list[dict[str, Any]] = []
    for row in rows:
        value = float(row["VALUE"])
        if value.is_integer():
            value = int(value)
        tidy_rows.append(
            {
                "ref_date": row.get("REF_DATE", ""),
                "geo": row.get("GEO", ""),
                "age_group": row.get("Age at time of death", ""),
                "sex": row.get("Sex", ""),
                "characteristic": row.get("Characteristics", ""),
                "value": value,
                "uom": row.get("UOM", ""),
                "status": row.get("STATUS", ""),
            }
        )
    tidy_rows.sort(key=lambda r: (r["ref_date"], r["characteristic"]))
    return tidy_rows


def write_published(rows: list[dict[str, Any]], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TIDY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return output


def ols_slope(points: Sequence[tuple[float, float]]) -> tuple[float, float, float]:
    """Ordinary least squares for y = a + b x; return (slope, intercept, sse)."""
    n = len(points)
    if n < 2:
        raise IndicatorError("need at least two points to fit a slope")
    mean_x = sum(x for x, _ in points) / n
    mean_y = sum(y for _, y in points) / n
    sxx = sum((x - mean_x) ** 2 for x, _ in points)
    if sxx == 0:
        raise IndicatorError("cannot fit a slope through identical x values")
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in points)
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    sse = sum((y - (intercept + slope * x)) ** 2 for x, y in points)
    return slope, intercept, sse


def trajectory(
    points: list[tuple[int, float]],
    min_segment: int = 5,
    n_permutations: int = breaks.N_PERMUTATIONS,
    seed: int = breaks.SEED,
) -> dict[str, Any]:
    """Summarise a series: overall slope, formally tested regimes, trend.

    The regime dating and the tests behind it come from
    :mod:`sohbc.breaks`; this function only selects the headline break and
    the segment slopes for reporting.
    """
    points = sorted(points)
    years = [x for x, _ in points]
    slope, _, _ = ols_slope(points)
    result: dict[str, Any] = {
        "start": years[0],
        "end": years[-1],
        "n": len(points),
        "overall": {
            "slope_per_year": round(slope, 4),
            "slope_per_decade": round(slope * 10, 4),
        },
        "change_point": None,
        "change_points": [],
        "segments": [],
    }
    tested = breaks.summarise(
        [(float(x), float(y)) for x, y in points],
        min_segment=min_segment,
        n_permutations=n_permutations,
        seed=seed,
    )
    result["break_test"] = tested["break_test"]
    result["trend_test"] = tested["trend_test"]
    result["stationarity"] = tested["stationarity"]
    result["regime_selection"] = tested["breaks"]
    if len(points) < 2 * min_segment or tested["breaks"] is None:
        return result

    break_years = tested["breaks"]["years"]
    result["change_points"] = break_years
    starts = [0]
    for year in break_years:
        starts.append(next(i for i, (x, _) in enumerate(points) if x >= year))
    starts.append(len(points))
    if len(break_years) == 1:
        labels = ["before", "after"]
    else:
        labels = [f"regime {i + 1}" for i in range(len(starts) - 1)]
    slopes: list[float] = []
    for label, (start, end) in zip(labels, itertools.pairwise(starts)):
        segment = points[start:end]
        segment_slope, _, _ = ols_slope(segment)
        slopes.append(segment_slope)
        result["segments"].append(
            {
                "label": label,
                "start": segment[0][0],
                "end": segment[-1][0],
                "slope_per_year": round(segment_slope, 4),
                "slope_per_decade": round(segment_slope * 10, 4),
            }
        )
    if len(slopes) > 1:
        changes = [abs(slopes[i] - slopes[i - 1]) for i in range(1, len(slopes))]
        result["change_point"] = break_years[changes.index(max(changes))]
    return result


def series_points(
    rows: list[dict[str, Any]],
    characteristic: str,
    age_group: str | None = None,
) -> list[tuple[int, float]]:
    points = []
    for row in rows:
        if row["characteristic"] != characteristic:
            continue
        if age_group is not None and row["age_group"] != age_group:
            continue
        points.append((int(str(row["ref_date"])[:4]), float(row["value"])))
    return points


AGE_PREFIX = "Age at time of death, "


def age_label_to_standard(label: str) -> str | None:
    """Map a StatCan age label to a WHO standard-population age-group id."""
    if not label.startswith(AGE_PREFIX):
        return None
    rest = label[len(AGE_PREFIX) :].strip()
    if rest == "under 1 year":
        return "0-4"
    if rest.endswith("years and over"):
        low = rest.split(" ", 1)[0]
        return f"{low}+"
    match = re.match(r"^(\d+)\s+to\s+(\d+)\s+years$", rest)
    if match:
        low, high = match.group(1), match.group(2)
        if int(low) <= 4 and int(high) <= 4:
            return "0-4"
        return f"{low}-{high}"
    return None


def load_standard_population(path: Path) -> dict[str, float]:
    weights: dict[str, float] = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            weights[row["age_group"]] = float(row["proportion"])
    if not weights:
        raise IndicatorError(f"empty standard population file: {path}")
    return weights


def age_standardise(
    rows: list[dict[str, Any]],
    characteristic: str,
    weights: dict[str, float],
) -> list[dict[str, Any]]:
    """Direct age-standardisation of age-specific rates to a standard population."""
    by_year: dict[str, dict[str, float]] = {}
    for row in rows:
        if row["characteristic"] != characteristic:
            continue
        group = age_label_to_standard(row["age_group"])
        if group is None or group not in weights:
            continue
        by_year.setdefault(str(row["ref_date"]), {})[group] = float(row["value"])

    results: list[dict[str, Any]] = []
    for ref_date, groups in sorted(by_year.items()):
        total_weight = sum(weights[group] for group in groups)
        if total_weight == 0:
            continue
        rate = (
            sum(weights[group] * value for group, value in groups.items())
            / total_weight
        )
        results.append({"ref_date": ref_date, "value": round(rate, 4)})
    return results


def build(key: str) -> dict[str, Any]:
    if key not in INDICATORS:
        raise IndicatorError(f"unknown indicator: {key}")
    spec = INDICATORS[key]
    zip_url = wds_zip_url(wds_download_json(spec["source_key"]))
    rows = table_rows(fetch_wds_zip(zip_url), spec["source_table"])
    chosen = select_rows(rows, spec["geo"], spec.get("age_group"), spec.get("sex"))
    tidy_rows = tidy(chosen)
    if not tidy_rows:
        raise IndicatorError(f"indicator {key} selected no rows")
    output = write_published(tidy_rows, spec["output"])

    standardised_path = None
    standardised: list[dict[str, Any]] = []
    if spec.get("standard_population"):
        weights = load_standard_population(spec["standard_population"])
        standardised = age_standardise(
            tidy_rows, spec["trajectory_characteristic"], weights
        )
        standardised_path = spec["output"].with_name(
            spec["output"].stem + "_age_standardised.csv"
        )
        with standardised_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=STANDARD_FIELDS)
            writer.writeheader()
            for record in standardised:
                writer.writerow(
                    {
                        "ref_date": record["ref_date"],
                        "characteristic": (
                            f"Age-standardised {spec['trajectory_characteristic'].lower()}"
                        ),
                        "value": record["value"],
                        "uom": "per 1,000 population",
                        "standard": spec["standard_name"],
                    }
                )

    standardised_trend_path = None
    if standardised_path is not None:
        standardised_points = [
            (int(str(record["ref_date"])[:4]), float(record["value"]))
            for record in standardised
        ]
        standardised_trend = trajectory(standardised_points)
        standardised_trend["series"] = (
            f"Age-standardised {spec['trajectory_characteristic'].lower()}"
        )
        standardised_trend_path = standardised_path.with_name(
            standardised_path.stem + "_trend.json"
        )
        standardised_trend_path.write_text(
            json.dumps(standardised_trend, indent=2) + "\n", encoding="utf-8"
        )

    trend_path = None
    if spec.get("trajectory_characteristic"):
        points = series_points(
            tidy_rows,
            spec["trajectory_characteristic"],
            age_group=spec.get("all_ages"),
        )
        trend = trajectory(points)
        trend["series"] = spec["trajectory_characteristic"]
        trend_path = spec["output"].with_name(spec["output"].stem + "_trend.json")
        trend_path.write_text(json.dumps(trend, indent=2) + "\n", encoding="utf-8")
    return {
        "indicator": key,
        "rows": len(tidy_rows),
        "output": output,
        "standardised": standardised_path,
        "standardised_trend": standardised_trend_path,
        "trend": trend_path,
    }
