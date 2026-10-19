"""Tests for indicator selection and tidying (no network access)."""

from __future__ import annotations

import csv
import io
import unittest
import zipfile

from sohbc.indicators import (
    age_label_to_standard,
    age_standardise,
    ols_slope,
    select_rows,
    table_rows,
    tidy,
    trajectory,
)


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


class TidyTests(unittest.TestCase):
    def test_converts_values_and_sorts(self) -> None:
        rows = [_row("British Columbia", "all ages", "Both sexes", "rate", "7.5")]
        rows.append({**rows[0], "REF_DATE": "1999", "VALUE": "8"})
        out = tidy(rows)
        self.assertEqual([r["ref_date"] for r in out], ["1999", "2020"])
        self.assertEqual(out[0]["value"], 8)
        self.assertIsInstance(out[0]["value"], int)
        self.assertEqual(out[1]["value"], 7.5)


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
        self.assertEqual(result["n"], 3)


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
                "age_group": "Age at time of death, 5 to 9 years",
                "characteristic": "Mortality rate per 1,000 population",
                "value": 10.0,
            },
            {
                "ref_date": "2020",
                "age_group": "Age at time of death, 65 to 69 years",
                "characteristic": "Mortality rate per 1,000 population",
                "value": 100.0,
            },
        ]
        weights = {"5-9": 1.0, "65-69": 3.0}
        result = age_standardise(rows, "Mortality rate per 1,000 population", weights)
        self.assertEqual(result, [{"ref_date": "2020", "value": 77.5}])


if __name__ == "__main__":
    unittest.main()
