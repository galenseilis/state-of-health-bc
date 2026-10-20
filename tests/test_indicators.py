"""Tests for indicator selection and tidying (no network access)."""

from __future__ import annotations

import csv
import io
import unittest
import zipfile

from sohbc.indicators import (
    DEFAULT_DIMENSIONS,
    INDICATORS,
    age_group_trends,
    age_label_to_standard,
    age_standardise,
    dispersion,
    ols_slope,
    region_level,
    select_rows,
    series_points,
    sex_breakdown,
    table_rows,
    tidy,
    tidy_regions,
    trajectory,
    wds_download_json,
)

LIFE_DIMENSIONS = INDICATORS["life_expectancy_bc"]["dimensions"]


def _life_row(
    geo: str, age: str, sex: str, element: str, value: str
) -> dict[str, str]:
    return {
        "REF_DATE": "2020",
        "GEO": geo,
        "Age group": age,
        "Sex": sex,
        "Element": element,
        "UOM": "Number",
        "VALUE": value,
        "STATUS": "",
    }


def _row(
    geo: str, age: str, sex: str, char: str, value: str, status: str = ""
) -> dict[str, str]:
    return {
        "REF_DATE": "2020",
        "GEO": geo,
        "Age at time of death": age,
        "Sex": sex,
        "Characteristics": char,
        "UOM": "Rates per 1,000 population",
        "VALUE": value,
        "STATUS": status,
    }


class SelectRowsTests(unittest.TestCase):
    def test_filters_by_geo_age_sex_and_empty_values(self) -> None:
        rows = [
            _row(
                "British Columbia, place of residence",
                "all ages",
                "Both sexes",
                "rate",
                "7.5",
            ),
            _row(
                "Alberta, place of residence", "all ages", "Both sexes", "rate", "7.0"
            ),
            _row(
                "British Columbia, place of residence",
                "0 to 4",
                "Both sexes",
                "rate",
                "1.0",
            ),
            _row(
                "British Columbia, place of residence",
                "all ages",
                "Males",
                "rate",
                "8.0",
            ),
            _row(
                "British Columbia, place of residence",
                "all ages",
                "Both sexes",
                "rate",
                "",
            ),
        ]
        out = select_rows(
            rows, "British Columbia, place of residence", "all ages", "Both sexes"
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["VALUE"], "7.5")

    def test_sex_none_keeps_every_sex(self) -> None:
        rows = [
            _row(
                "British Columbia, place of residence", "all ages", sex, "rate", value
            )
            for sex, value in [
                ("Both sexes", "7.5"),
                ("Males", "8.0"),
                ("Females", "7.0"),
            ]
        ]
        out = select_rows(
            rows, "British Columbia, place of residence", "all ages", None
        )
        self.assertEqual(len(out), 3)

    def test_custom_dimension_labels(self) -> None:
        rows = [
            _life_row(
                "British Columbia", "0 years", "Both sexes", "life expectancy", "82.5"
            ),
            _life_row(
                "British Columbia", "65 years", "Both sexes", "life expectancy", "20.0"
            ),
        ]
        out = select_rows(
            rows,
            "British Columbia",
            "0 years",
            None,
            dimensions=LIFE_DIMENSIONS,
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["Age group"], "0 years")


class TidyTests(unittest.TestCase):
    def test_converts_values_and_sorts(self) -> None:
        rows = [_row("British Columbia", "all ages", "Both sexes", "rate", "7.5")]
        rows.append({**rows[0], "REF_DATE": "1999", "VALUE": "8"})
        rows.append({**rows[0], "Sex": "Females", "VALUE": "7.0"})
        out = tidy(rows)
        self.assertEqual(
            [(r["ref_date"], r["sex"]) for r in out],
            [("1999", "Both sexes"), ("2020", "Both sexes"), ("2020", "Females")],
        )
        self.assertEqual(out[0]["value"], 8)
        self.assertIsInstance(out[0]["value"], int)
        self.assertEqual(out[1]["value"], 7.5)

    def test_custom_dimension_labels(self) -> None:
        rows = [
            _life_row(
                "British Columbia", "0 years", "Males", "life expectancy", "80.16"
            )
        ]
        out = tidy(rows, dimensions=LIFE_DIMENSIONS)
        self.assertEqual(out[0]["age_group"], "0 years")
        self.assertEqual(out[0]["sex"], "Males")
        self.assertEqual(out[0]["characteristic"], "life expectancy")
        self.assertEqual(out[0]["value"], 80.16)


class DownloadManifestTests(unittest.TestCase):
    def test_manifest_filename_uses_table_stem(self) -> None:
        path = wds_download_json("statcan_life_tables", table_id="13-10-0837-01")
        self.assertEqual(path.name, "13100837-download.json")
        self.assertEqual(path.parent.name, "statcan_life_tables")

    def test_manifest_default_is_legacy_layout(self) -> None:
        path = wds_download_json("statcan_wds")
        self.assertEqual(path.name, "13100710-download.json")


class TableRowsTests(unittest.TestCase):
    def test_reads_data_csv_from_zip(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            handle = io.StringIO()
            writer = csv.DictWriter(handle, fieldnames=["REF_DATE", "GEO", "VALUE"])
            writer.writeheader()
            writer.writerow(
                {"REF_DATE": "2020", "GEO": "British Columbia", "VALUE": "7.5"}
            )
            archive.writestr("13100710.csv", handle.getvalue())
            archive.writestr("13100710_MetaData.csv", "ignored")
        rows = table_rows(buffer.getvalue(), "13100710")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["GEO"], "British Columbia")


class SlopeTests(unittest.TestCase):
    def test_ols_slope_is_exact_on_a_line(self) -> None:
        slope, intercept, sse = ols_slope([(0, 1), (1, 3), (2, 5), (3, 7)])
        self.assertAlmostEqual(slope, 2.0)
        self.assertAlmostEqual(intercept, 1.0)
        self.assertAlmostEqual(sse, 0.0)


class TrajectoryTests(unittest.TestCase):
    def test_detects_change_point(self) -> None:
        points = [(y, 2.0 * y) for y in range(2000, 2011)]
        points += [(y, 100.0 - 2.0 * y) for y in range(2011, 2022)]
        result = trajectory(points, min_segment=5, n_permutations=199)
        self.assertEqual(result["change_point"], 2011)
        self.assertEqual(result["change_points"], [2011])
        self.assertEqual(len(result["segments"]), 2)
        self.assertLess(result["segments"][1]["slope_per_year"], 0)

    def test_reports_formal_break_and_trend_tests(self) -> None:
        points = [(y, 2.0 * y) for y in range(2000, 2011)]
        points += [(y, 100.0 - 2.0 * y) for y in range(2011, 2022)]
        result = trajectory(points, min_segment=5, n_permutations=199)
        self.assertTrue(result["break_test"]["significant"])
        self.assertTrue(result["break_test"]["method"])
        self.assertIn("p_value", result["trend_test"])
        self.assertEqual(result["stationarity"]["verdict"], "nonstationary")
        self.assertTrue(result["stationarity"]["reasons"])
        self.assertEqual(result["regime_selection"]["years"], [2011])

    def test_short_series_has_no_change_point(self) -> None:
        result = trajectory([(2000, 1.0), (2001, 1.1), (2002, 1.2)], min_segment=5)
        self.assertIsNone(result["change_point"])
        self.assertEqual(result["change_points"], [])
        self.assertEqual(result["stationarity"]["verdict"], "undetermined")

    def test_decomposes_change_into_within_and_between(self) -> None:
        # Two regimes with the same slope but a level step at the break:
        # the decomposition should put the whole change in "between".
        points = [(y, 2.0 * y) for y in range(2000, 2011)]
        points += [(y, 2.0 * y + 50.0) for y in range(2011, 2022)]
        result = trajectory(points, min_segment=5, n_permutations=199)
        self.assertIn("decomposition", result)
        self.assertEqual(len(result["jumps"]), 1)
        jump = result["jumps"][0]
        self.assertEqual(jump["year"], 2011)
        self.assertAlmostEqual(jump["jump"], 50.0, delta=1e-6)
        # Level step dominates; within-regime change is just the smooth slope.
        self.assertAlmostEqual(
            result["decomposition"]["between_regime_change"], 50.0, delta=1e-6
        )

    def test_reports_segment_levels_and_within_change(self) -> None:
        points = [(y, 2.0 * y) for y in range(2000, 2011)]
        points += [(y, 100.0 - 2.0 * y) for y in range(2011, 2022)]
        result = trajectory(points, min_segment=5, n_permutations=199)
        for segment in result["segments"]:
            self.assertIn("fitted_start", segment)
            self.assertIn("fitted_end", segment)
            self.assertIn("change_within", segment)


class AgeStandardisationTests(unittest.TestCase):
    def test_maps_labels_to_standard_groups(self) -> None:
        self.assertEqual(
            age_label_to_standard("Age at time of death, under 1 year"), "0-4"
        )
        self.assertEqual(
            age_label_to_standard("Age at time of death, 1 to 4 years"), "0-4"
        )
        self.assertEqual(
            age_label_to_standard("Age at time of death, 65 to 69 years"), "65-69"
        )
        self.assertEqual(
            age_label_to_standard("Age at time of death, 90 years and over"), "90+"
        )
        self.assertIsNone(age_label_to_standard("Age at time of death, all ages"))

    def test_standardised_rate_weights_by_population(self) -> None:
        rows = [
            {
                "ref_date": "2020",
                "sex": "Both sexes",
                "age_group": "Age at time of death, 5 to 9 years",
                "characteristic": "Mortality rate per 1,000 population",
                "value": 10.0,
            },
            {
                "ref_date": "2020",
                "sex": "Both sexes",
                "age_group": "Age at time of death, 65 to 69 years",
                "characteristic": "Mortality rate per 1,000 population",
                "value": 100.0,
            },
        ]
        weights = {"5-9": 1.0, "65-69": 3.0}
        result = age_standardise(rows, "Mortality rate per 1,000 population", weights)
        self.assertEqual(
            result, [{"ref_date": "2020", "sex": "Both sexes", "value": 77.5}]
        )

    def test_sex_filter_keeps_one_category(self) -> None:
        rows = [
            {
                "ref_date": "2020",
                "sex": sex,
                "age_group": "Age at time of death, 5 to 9 years",
                "characteristic": "Mortality rate per 1,000 population",
                "value": value,
            }
            for sex, value in [("Males", 2.0), ("Females", 1.0)]
        ]
        weights = {"5-9": 1.0}
        result = age_standardise(
            rows, "Mortality rate per 1,000 population", weights, sex="Females"
        )
        self.assertEqual(result, [{"ref_date": "2020", "sex": "Females", "value": 1.0}])


class SeriesPointsTests(unittest.TestCase):
    def test_filters_by_sex(self) -> None:
        rows = [
            {
                "ref_date": "2020",
                "sex": sex,
                "age_group": "Age at time of death, all ages",
                "characteristic": "rate",
                "value": value,
            }
            for sex, value in [("Both sexes", 7.5), ("Males", 8.0), ("Females", 7.0)]
        ]
        self.assertEqual(series_points(rows, "rate", sex="Males"), [(2020, 8.0)])
        self.assertEqual(len(series_points(rows, "rate")), 3)


class SexBreakdownTests(unittest.TestCase):
    def test_summarises_each_sex_separately(self) -> None:
        rows = []
        for sex, base in [("Males", 8.0), ("Females", 7.0)]:
            for year in range(2000, 2011):
                rows.append(
                    {
                        "ref_date": str(year),
                        "sex": sex,
                        "age_group": "Age at time of death, all ages",
                        "characteristic": "rate",
                        "value": base + 0.1 * (year - 2000),
                    }
                )
        result = sex_breakdown(
            rows, "rate", ["Both sexes", "Males", "Females"], age_group=None
        )
        self.assertEqual(list(result), ["Males", "Females"])
        self.assertGreater(result["Males"]["overall"]["slope_per_year"], 0)
        self.assertAlmostEqual(
            result["Males"]["overall"]["slope_per_year"],
            result["Females"]["overall"]["slope_per_year"],
            places=6,
        )


class RegionLevelTests(unittest.TestCase):
    def test_classifies_authority_area_and_province(self) -> None:
        self.assertEqual(
            region_level("Fraser Health Authority, British Columbia"),
            "health_authority",
        )
        self.assertEqual(
            region_level(
                "Richmond Health Service Delivery Area, British Columbia"
            ),
            "health_service_delivery_area",
        )
        self.assertEqual(region_level("British Columbia"), "province")


class TidyRegionsTests(unittest.TestCase):
    def _region_row(
        self, geo: str, sex: str, value: str, indicator: str = "Mortality"
    ) -> dict[str, str]:
        return {
            "REF_DATE": "2021/2023",
            "GEO": geo,
            "Sex": sex,
            "Indicators": indicator,
            "Selected causes of death": "Premature mortality",
            "Characteristics": "Age-standardized rate",
            "UOM": "Age-standardized rate per 100,000 population",
            "VALUE": value,
            "STATUS": "",
        }

    def test_drops_province_and_keeps_regions(self) -> None:
        rows = [
            self._region_row("British Columbia", "Both sexes", "342.3"),
            self._region_row(
                "Richmond Health Service Delivery Area, British Columbia",
                "Both sexes",
                "183.5",
            ),
        ]
        result = tidy_regions(rows, "British Columbia", ["Both sexes"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["region"], "Richmond Health Service Delivery Area")
        self.assertEqual(result[0]["region_level"], "health_service_delivery_area")

    def test_filters_by_indicator(self) -> None:
        rows = [
            self._region_row(
                "Richmond Health Service Delivery Area, British Columbia",
                "Both sexes",
                "183.5",
                indicator="Mortality",
            ),
            self._region_row(
                "Richmond Health Service Delivery Area, British Columbia",
                "Both sexes",
                "9939.5",
                indicator="Potential years of life lost",
            ),
        ]
        result = tidy_regions(
            rows, "British Columbia", ["Both sexes"], indicators=["Mortality"]
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["value"], 183.5)

    def test_filters_by_sex_and_skips_empty_values(self) -> None:
        rows = [
            self._region_row(
                "Richmond Health Service Delivery Area, British Columbia",
                "Males",
                "200",
            ),
            self._region_row(
                "Richmond Health Service Delivery Area, British Columbia",
                "Females",
                "",
            ),
        ]
        result = tidy_regions(rows, "British Columbia", ["Males"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["sex"], "Males")


class DispersionTests(unittest.TestCase):
    def _tidy(self, region: str, level: str, value: float) -> dict:
        return {
            "ref_date": "2021/2023",
            "region": region,
            "region_level": level,
            "sex": "Both sexes",
            "indicator": "Mortality",
            "cause": "Premature mortality",
            "characteristic": "Age-standardized rate",
            "value": value,
        }

    def test_reports_lowest_highest_ratio_and_range(self) -> None:
        rows = [
            self._tidy("Richmond", "health_service_delivery_area", 183.5),
            self._tidy("Northwest", "health_service_delivery_area", 551.3),
            self._tidy("Fraser", "health_service_delivery_area", 300.0),
        ]
        result = dispersion(
            rows, "Premature mortality", "Age-standardized rate", "Both sexes"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["n_regions"], 3)
        self.assertEqual(result["lowest"]["region"], "Richmond")
        self.assertEqual(result["highest"]["region"], "Northwest")
        self.assertAlmostEqual(result["ratio"], round(551.3 / 183.5, 3))
        self.assertAlmostEqual(result["range"], round(551.3 - 183.5, 3))

    def test_excludes_other_levels(self) -> None:
        rows = [
            self._tidy("Richmond", "health_service_delivery_area", 183.5),
            self._tidy("Northern", "health_authority", 999.0),
        ]
        result = dispersion(
            rows, "Premature mortality", "Age-standardized rate", "Both sexes"
        )
        self.assertEqual(result["n_regions"], 1)
        self.assertEqual(result["highest"]["region"], "Richmond")

    def test_returns_none_when_no_match(self) -> None:
        result = dispersion([], "Premature mortality", "Age-standardized rate", "Males")
        self.assertIsNone(result)


class AgeGroupTrendsTests(unittest.TestCase):
    def test_summarises_each_age_group_for_one_sex(self) -> None:
        rows = []
        for group, base in [("young", 1.0), ("old", 20.0)]:
            for year in range(2000, 2011):
                rows.append(
                    {
                        "ref_date": str(year),
                        "sex": "Both sexes",
                        "age_group": group,
                        "characteristic": "rate",
                        "value": base + 0.5 * (year - 2000),
                    }
                )
        result = age_group_trends(
            rows, "rate", ["young", "old"], "Both sexes", n_permutations=99
        )
        self.assertEqual(list(result), ["young", "old"])
        self.assertAlmostEqual(result["young"]["overall"]["slope_per_year"], 0.5, places=6)
        self.assertAlmostEqual(result["old"]["overall"]["slope_per_year"], 0.5, places=6)

    def test_omits_absent_age_groups(self) -> None:
        rows = [
            {
                "ref_date": str(year),
                "sex": "Both sexes",
                "age_group": "young",
                "characteristic": "rate",
                "value": float(year),
            }
            for year in range(2000, 2011)
        ]
        result = age_group_trends(
            rows, "rate", ["young", "missing"], "Both sexes", n_permutations=99
        )
        self.assertEqual(list(result), ["young"])


if __name__ == "__main__":
    unittest.main()
