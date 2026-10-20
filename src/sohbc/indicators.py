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

STANDARD_FIELDS = ["ref_date", "sex", "characteristic", "value", "uom", "standard"]

ALL_AGES = "Age at time of death, all ages"

#: Default dimension-label lookups, keyed by the tidy column they fill.
DEFAULT_DIMENSIONS: dict[str, str] = {
    "age_group": "Age at time of death",
    "sex": "Sex",
    "characteristic": "Characteristics",
}

INDICATORS: dict[str, dict[str, Any]] = {
    "mortality_rates_bc": {
        "title": "Mortality rates, British Columbia",
        "domain": "Mortality",
        "source_key": "statcan_wds",
        "source_table": "13-10-0710-01",
        "source_table_url": "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1310071001",
        "geo": "British Columbia, place of residence",
        "age_group": None,
        "sexes": ["Both sexes", "Males", "Females"],
        "all_ages": "Age at time of death, all ages",
        "output": PUBLISHED_DIR / "mortality_rates_bc.csv",
        "standard_population": REFERENCE_DIR / "who_standard_population.csv",
        "standard_name": "WHO World Standard Population (2000-2025)",
        "trajectory_characteristic": "Mortality rate per 1,000 population",
        "breakdown_label": "crude",
        "definition": (
            "Deaths and the crude mortality rate (deaths per 1,000 population), "
            "all ages, by sex (both sexes, males, females), resident in "
            "British Columbia, plus an age-standardised rate per sex using "
            "the WHO World Standard Population."
        ),
        "caveats": (
            "Crude rate: not adjusted to a standard population, so it reflects "
            "both real change and shifts in the age structure of the population. "
            "Sex categories are those of the source (both sexes, males, "
            "females). Recent years include the COVID-19 period."
        ),
    },
    "life_expectancy_bc": {
        "title": "Life expectancy at birth, British Columbia",
        "domain": "Mortality",
        "source_key": "statcan_life_tables",
        "source_table": "13-10-0837-01",
        "source_table_url": (
            "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1310083701"
        ),
        "dimensions": {
            "age_group": "Age group",
            "sex": "Sex",
            "characteristic": "Element",
        },
        "geo": "British Columbia",
        "age_group": "0 years",
        "sexes": ["Both sexes", "Males", "Females"],
        "output": PUBLISHED_DIR / "life_expectancy_bc.csv",
        "trajectory_characteristic": "Life expectancy (in years) at age x (ex)",
        "breakdown_label": "levels",
        "definition": (
            "Life expectancy at birth (age 0), in years, by sex (both sexes, "
            "males, females), resident in British Columbia. Derived from the "
            "complete life table of Statistics Canada table 13-10-0837-01."
        ),
        "caveats": (
            "Life expectancy is a period measure: it is the average length of "
            "life a synthetic cohort would experience if it lived its whole "
            "life under the age-specific death rates of the reference year. It "
            "reports nothing about the health of those alive. Single-year "
            "estimates are subject to revision, and the 2020-2022 period "
            "reflects the COVID-19 mortality shock."
        ),
    },
}

CCHS_DIMENSIONS: dict[str, str] = {
    "age_group": "Age group",
    "sex": "Sex",
    "characteristic": "Characteristics",
}

#: Reference period rows available for every CCHS indicator (table 13-10-0905-01).
CCHS_START, CCHS_END = 2015, 2024


def _cchs_indicator(
    key: str,
    title: str,
    domain: str,
    measure: str,
    definition: str,
    caveats: str,
) -> tuple[str, dict[str, Any]]:
    """Build a spec for one British Columbia series in table 13-10-0905-01.

    Every series is the survey "Percent" estimate for the population aged 18
    and over, both sexes, at provincial resolution.
    """
    return key, {
        "title": title,
        "domain": domain,
        "source_key": "statcan_health_indicators",
        "source_table": "13-10-0905-01",
        "source_table_url": (
            "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1310090501"
        ),
        "dimensions": CCHS_DIMENSIONS,
        "filters": {"Indicators": measure, "Characteristics": "Percent"},
        "measure": measure,
        "geo": "British Columbia",
        "age_group": "Total, 18 years and over",
        "sexes": ["Both sexes", "Males", "Females"],
        "all_ages": "Total, 18 years and over",
        "output": PUBLISHED_DIR / f"{key}.csv",
        "trajectory_characteristic": "Percent",
        "breakdown_label": "levels",
        "definition": definition,
        "caveats": caveats,
    }


CCHS_CAVEAT = (
    "Survey estimate (Canadian Community Health Survey): carries sampling "
    "error and a coefficient-of-variation release policy, so some cells are "
    "suppressed or flagged. The collection frame changed over the series and "
    "2020-2021 collection was disrupted by the pandemic, so part of any "
    "apparent change is measurement change. Reported for the population aged "
    "18 and over, both sexes, at provincial resolution."
)

_CCHS_SPECS = [
    _cchs_indicator(
        "life_satisfaction_bc",
        "Life satisfaction, British Columbia",
        "Subjective wellbeing",
        "Life satisfaction, satisfied or very satisfied",
        "Percent of British Columbians aged 18 and over who report being "
        "satisfied or very satisfied with life, annual 2015-2024.",
        CCHS_CAVEAT,
    ),
    _cchs_indicator(
        "perceived_health_fair_poor_bc",
        "Perceived health, fair or poor, British Columbia",
        "Subjective wellbeing",
        "Perceived health, fair or poor",
        "Percent of British Columbians aged 18 and over who rate their own "
        "health as fair or poor, annual 2015-2024.",
        CCHS_CAVEAT,
    ),
    _cchs_indicator(
        "perceived_mental_health_fair_poor_bc",
        "Perceived mental health, fair or poor, British Columbia",
        "Mental health",
        "Perceived mental health, fair or poor",
        "Percent of British Columbians aged 18 and over who rate their own "
        "mental health as fair or poor, annual 2015-2024.",
        CCHS_CAVEAT,
    ),
    _cchs_indicator(
        "sense_of_belonging_bc",
        "Sense of belonging to local community, British Columbia",
        "Social wellbeing",
        "Sense of belonging to local community, somewhat strong or very strong",
        "Percent of British Columbians aged 18 and over who report a somewhat "
        "strong or very strong sense of belonging to their local community, "
        "annual 2015-2024.",
        CCHS_CAVEAT,
    ),
    _cchs_indicator(
        "anxiety_disorder_bc",
        "Anxiety disorder, British Columbia",
        "Mental health",
        "Anxiety disorder",
        "Percent of British Columbians aged 18 and over who report an anxiety "
        "disorder, annual 2015-2024.",
        CCHS_CAVEAT,
    ),
    _cchs_indicator(
        "mood_disorder_bc",
        "Mood disorder, British Columbia",
        "Mental health",
        "Mood disorder",
        "Percent of British Columbians aged 18 and over who report a mood "
        "disorder, annual 2015-2024.",
        CCHS_CAVEAT,
    ),
    _cchs_indicator(
        "diabetes_bc",
        "Diabetes, British Columbia",
        "Physical morbidity",
        "Diabetes",
        "Percent of British Columbians aged 18 and over who report diabetes, "
        "annual 2015-2024.",
        CCHS_CAVEAT,
    ),
    _cchs_indicator(
        "high_blood_pressure_bc",
        "High blood pressure, British Columbia",
        "Physical morbidity",
        "High blood pressure",
        "Percent of British Columbians aged 18 and over who report high blood "
        "pressure, annual 2015-2024.",
        CCHS_CAVEAT,
    ),
    _cchs_indicator(
        "has_regular_provider_bc",
        "Has a regular healthcare provider, British Columbia",
        "Functional status",
        "Has a regular healthcare provider",
        "Percent of British Columbians aged 18 and over who report having a "
        "regular healthcare provider, annual 2015-2024.",
        CCHS_CAVEAT,
    ),
    _cchs_indicator(
        "smoker_daily_bc",
        "Current daily smoker, British Columbia",
        "Physical morbidity",
        "Current smoker, daily",
        "Percent of British Columbians aged 18 and over who report smoking "
        "daily, annual 2015-2024.",
        CCHS_CAVEAT,
    ),
]

INDICATORS.update(dict(_CCHS_SPECS))

TIDY_FIELDS = [
    "ref_date",
    "geo",
    "age_group",
    "sex",
    "characteristic",
    "measure",
    "value",
    "uom",
    "status",
]


class IndicatorError(ValueError):
    """Raised when an indicator cannot be built."""


def wds_download_json(source_key: str, table_id: str | None = None) -> Path:
    """Path to a WDS download manifest for a source (and optional table).

    Args:
        source_key: Catalogue key of the WDS source.
        table_id: Table id used to name the manifest file; when omitted,
            the single ``*-download.json`` manifest in the directory is
            used (the layout of a single-table source).
    """
    directory = RAW_DIR / source_key
    if table_id is None:
        return directory / "13100710-download.json"
    digits = table_id.split("-")
    stem = "".join(digits[:3]) if len(digits) >= 3 else re.sub(r"\D", "", table_id)
    return directory / f"{stem}-download.json"


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
    dimensions: dict[str, str] | None = None,
    filters: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    labels = dimensions or DEFAULT_DIMENSIONS
    age_field = labels.get("age_group")
    sex_field = labels.get("sex")
    required = filters or {}
    selected = []
    for row in rows:
        if row.get("GEO") != geo:
            continue
        if (
            age_group is not None
            and age_field is not None
            and row.get(age_field) != age_group
        ):
            continue
        if sex is not None and sex_field is not None and row.get(sex_field) != sex:
            continue
        if any(row.get(column) != value for column, value in required.items()):
            continue
        if not row.get("VALUE"):
            continue
        selected.append(row)
    return selected


def tidy(
    rows: list[dict[str, str]],
    dimensions: dict[str, str] | None = None,
    measure: str | None = None,
) -> list[dict[str, Any]]:
    labels = dimensions or DEFAULT_DIMENSIONS
    age_field = labels.get("age_group")
    sex_field = labels.get("sex")
    characteristic_field = labels.get("characteristic", "Characteristics")
    tidy_rows: list[dict[str, Any]] = []
    for row in rows:
        value = float(row["VALUE"])
        if value.is_integer():
            value = int(value)
        tidy_rows.append(
            {
                "ref_date": row.get("REF_DATE", ""),
                "geo": row.get("GEO", ""),
                "age_group": row.get(age_field, "") if age_field else "",
                "sex": row.get(sex_field, "") if sex_field else "",
                "characteristic": row.get(characteristic_field, ""),
                "measure": measure if measure is not None else "",
                "value": value,
                "uom": row.get("UOM", ""),
                "status": row.get("STATUS", ""),
            }
        )
    tidy_rows.sort(key=lambda r: (r["ref_date"], r["characteristic"], r["sex"]))
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
    sex: str | None = None,
) -> list[tuple[int, float]]:
    points = []
    for row in rows:
        if row["characteristic"] != characteristic:
            continue
        if age_group is not None and row["age_group"] != age_group:
            continue
        if sex is not None and row["sex"] != sex:
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
    sex: str | None = None,
) -> list[dict[str, Any]]:
    """Direct age-standardisation of age-specific rates to a standard population.

    Args:
        rows: Tidy rows as produced by :func:`tidy`.
        characteristic: The rate characteristic to standardise.
        weights: Standard-population weights by age-group id.
        sex: Restrict to one sex category; ``None`` keeps every sex,
            standardising each separately.
    """
    by_year: dict[tuple[str, str], dict[str, float]] = {}
    for row in rows:
        if row["characteristic"] != characteristic:
            continue
        row_sex = row.get("sex", "")
        if sex is not None and row_sex != sex:
            continue
        group = age_label_to_standard(row["age_group"])
        if group is None or group not in weights:
            continue
        by_year.setdefault((str(row["ref_date"]), row_sex), {})[group] = float(
            row["value"]
        )

    results: list[dict[str, Any]] = []
    for (ref_date, row_sex), groups in sorted(by_year.items()):
        total_weight = sum(weights[group] for group in groups)
        if total_weight == 0:
            continue
        rate = (
            sum(weights[group] * value for group, value in groups.items())
            / total_weight
        )
        results.append(
            {"ref_date": ref_date, "sex": row_sex, "value": round(rate, 4)}
        )
    return results


def sex_breakdown(
    rows: list[dict[str, Any]],
    characteristic: str,
    sexes: Sequence[str],
    age_group: str | None = None,
) -> dict[str, Any]:
    """Trajectory summary per sex category for one series.

    Args:
        rows: Tidy rows as produced by :func:`tidy`.
        characteristic: The characteristic to summarise.
        sexes: Sex categories to report, in display order.
        age_group: Restrict to one age group; ``None`` keeps all ages.

    Returns:
        dict: Sex category to :func:`trajectory` result, in the order
        requested; categories absent from the data are omitted.
    """
    breakdown: dict[str, Any] = {}
    for sex in sexes:
        points = series_points(rows, characteristic, age_group=age_group, sex=sex)
        if points:
            breakdown[sex] = trajectory(points)
    return breakdown


def build(key: str) -> dict[str, Any]:
    if key not in INDICATORS:
        raise IndicatorError(f"unknown indicator: {key}")
    spec = INDICATORS[key]
    sexes: list[str] = list(spec.get("sexes") or [spec.get("sex")])
    dimensions = spec.get("dimensions")
    table_id = spec["source_table"]
    zip_url = wds_zip_url(
        wds_download_json(spec["source_key"], table_id=table_id)
    )
    rows = table_rows(fetch_wds_zip(zip_url), table_id)
    chosen = select_rows(
        rows,
        spec["geo"],
        spec.get("age_group"),
        sex=None,
        dimensions=dimensions,
        filters=spec.get("filters"),
    )
    tidy_rows = tidy(chosen, dimensions=dimensions, measure=spec.get("measure"))
    if not tidy_rows:
        raise IndicatorError(f"indicator {key} selected no rows")
    output = write_published(tidy_rows, spec["output"])

    standardised: list[dict[str, Any]] = []
    standardised_path = None
    if spec.get("standard_population"):
        weights = load_standard_population(spec["standard_population"])
        characteristic = spec["trajectory_characteristic"]
        for sex in sexes:
            standardised.extend(
                age_standardise(tidy_rows, characteristic, weights, sex=sex)
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
                        "sex": record["sex"],
                        "characteristic": (
                            f"Age-standardised {spec['trajectory_characteristic'].lower()}"
                        ),
                        "value": record["value"],
                        "uom": "per 1,000 population",
                        "standard": spec["standard_name"],
                    }
                )

    standardised_trend_path = None
    by_sex_trend_path = None
    trend_path = None
    headline_sex = sexes[0]
    if spec.get("trajectory_characteristic"):
        characteristic = spec["trajectory_characteristic"]

        headline_asr = [r for r in standardised if r["sex"] == headline_sex]
        if headline_asr:
            standardised_points = [
                (int(str(record["ref_date"])[:4]), float(record["value"]))
                for record in headline_asr
            ]
            standardised_trend = trajectory(standardised_points)
            standardised_trend["series"] = (
                f"Age-standardised {characteristic.lower()}"
            )
            standardised_trend["sex"] = headline_sex
            standardised_trend_path = standardised_path.with_name(
                standardised_path.stem + "_trend.json"
            )
            standardised_trend_path.write_text(
                json.dumps(standardised_trend, indent=2) + "\n", encoding="utf-8"
            )

        points = series_points(
            tidy_rows,
            characteristic,
            age_group=spec.get("all_ages"),
            sex=headline_sex,
        )
        if points:
            trend = trajectory(points)
            trend["series"] = characteristic
            trend["sex"] = headline_sex
            trend_path = spec["output"].with_name(spec["output"].stem + "_trend.json")
            trend_path.write_text(
                json.dumps(trend, indent=2) + "\n", encoding="utf-8"
            )

        breakdown: dict[str, Any] = {
            spec.get("breakdown_label", "levels"): sex_breakdown(
                tidy_rows,
                characteristic,
                sexes,
                age_group=spec.get("all_ages"),
            ),
        }
        if standardised:
            standardised_breakdown: dict[str, Any] = {}
            for sex in sexes:
                sex_points = [
                    (int(str(record["ref_date"])[:4]), float(record["value"]))
                    for record in standardised
                    if record["sex"] == sex
                ]
                if sex_points:
                    standardised_breakdown[sex] = trajectory(sex_points)
            breakdown["age_standardised"] = standardised_breakdown
        by_sex_trend_path = spec["output"].with_name(
            spec["output"].stem + "_by_sex_trend.json"
        )
        by_sex_trend_path.write_text(
            json.dumps(breakdown, indent=2) + "\n", encoding="utf-8"
        )

    return {
        "indicator": key,
        "rows": len(tidy_rows),
        "output": output,
        "standardised": standardised_path,
        "standardised_trend": standardised_trend_path,
        "trend": trend_path,
        "by_sex_trend": by_sex_trend_path,
    }
