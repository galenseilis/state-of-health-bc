"""Indicator definitions and the build step that turns raw tables into
published, tidy datasets under data/published/."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import requests

from .catalogue import ROOT
from .fetch import RAW_DIR, TIMEOUT, USER_AGENT

PUBLISHED_DIR = ROOT / "data" / "published"

INDICATORS: dict[str, dict[str, Any]] = {
    "mortality_rates_bc": {
        "title": "Mortality rates, British Columbia",
        "domain": "Mortality",
        "source_key": "statcan_wds",
        "source_table": "13-10-0710-01",
        "source_table_url": "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1310071001",
        "geo": "British Columbia, place of residence",
        "age_group": "Age at time of death, all ages",
        "sex": "Both sexes",
        "output": PUBLISHED_DIR / "mortality_rates_bc.csv",
        "trajectory_characteristic": "Mortality rate per 1,000 population",
        "definition": (
            "Deaths and the crude mortality rate (deaths per 1,000 population), "
            "all ages, both sexes, resident in British Columbia."
        ),
        "caveats": (
            "Crude rate: not adjusted to a standard population, so it reflects "
            "both real change and shifts in the age structure of the population. "
            "Recent years include the COVID-19 period."
        ),
    },
}

TIDY_FIELDS = ["ref_date", "geo", "age_group", "sex", "characteristic", "value", "uom", "status"]


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


def ols_slope(points: list[tuple[float, float]]) -> tuple[float, float, float]:
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


def trajectory(points: list[tuple[int, float]], min_segment: int = 5) -> dict[str, Any]:
    """Summarise a series: overall slope and a single best change point."""
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
        "segments": [],
    }
    if len(points) < 2 * min_segment:
        return result

    best_year: int | None = None
    best_sse = float("inf")
    for i in range(min_segment, len(points) - min_segment + 1):
        left = points[:i]
        right = points[i:]
        try:
            _, _, sse_left = ols_slope(left)
            _, _, sse_right = ols_slope(right)
        except IndicatorError:
            continue
        total = sse_left + sse_right
        if total < best_sse:
            best_sse = total
            best_year = points[i][0]
    if best_year is None:
        return result

    left = [(x, y) for x, y in points if x < best_year]
    right = [(x, y) for x, y in points if x >= best_year]
    result["change_point"] = best_year
    for label, segment in (("before", left), ("after", right)):
        s, _, _ = ols_slope(segment)
        result["segments"].append(
            {
                "label": label,
                "start": segment[0][0],
                "end": segment[-1][0],
                "slope_per_year": round(s, 4),
                "slope_per_decade": round(s * 10, 4),
            }
        )
    return result


def series_points(
    rows: list[dict[str, Any]], characteristic: str
) -> list[tuple[int, float]]:
    points = []
    for row in rows:
        if row["characteristic"] != characteristic:
            continue
        points.append((int(str(row["ref_date"])[:4]), float(row["value"])))
    return points


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

    trend_path = None
    if spec.get("trajectory_characteristic"):
        points = series_points(tidy_rows, spec["trajectory_characteristic"])
        trend = trajectory(points)
        trend["series"] = spec["trajectory_characteristic"]
        trend_path = spec["output"].with_name(spec["output"].stem + "_trend.json")
        trend_path.write_text(json.dumps(trend, indent=2) + "\n", encoding="utf-8")
    return {"indicator": key, "rows": len(tidy_rows), "output": output, "trend": trend_path}

