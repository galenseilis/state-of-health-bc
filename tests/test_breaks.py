"""Tests for formal change-point detection and trend testing."""

from __future__ import annotations

import random
import unittest

from sohbc.breaks import (
    BreakError,
    select_breaks,
    single_break_test,
    summarise,
    trend_test,
)


def _piecewise_linear(knot_year: int = 2011) -> list[tuple[float, float]]:
    rising = [(y, 2.0 * y) for y in range(2000, knot_year)]
    falling = [(y, 100.0 - 2.0 * y) for y in range(knot_year, 2022)]
    return [(float(y), value) for y, value in rising + falling]


def _noisy_line(seed: int = 0, n: int = 30) -> list[tuple[float, float]]:
    generator = random.Random(seed)
    return [
        (2000.0 + i, 3.0 + 0.5 * i + generator.uniform(-0.5, 0.5)) for i in range(n)
    ]


class SelectBreaksTests(unittest.TestCase):
    def test_dates_the_knot_of_a_piecewise_linear_series(self) -> None:
        result = select_breaks(_piecewise_linear())
        self.assertEqual(result["n_breaks"], 1)
        self.assertEqual(result["years"], [2011])

    def test_perfectly_linear_series_has_no_breaks(self) -> None:
        line = [(float(2000 + i), 3.0 + 0.5 * i) for i in range(30)]
        result = select_breaks(line)
        self.assertEqual(result["n_breaks"], 0)
        self.assertEqual(result["years"], [])

    def test_bic_table_covers_every_candidate(self) -> None:
        result = select_breaks(_piecewise_linear())
        considered = [row["n_breaks"] for row in result["candidates"]]
        self.assertEqual(considered, list(range(result["max_breaks_considered"] + 1)))
        best = min(result["candidates"], key=lambda row: row["bic"])
        self.assertEqual(best["n_breaks"], result["n_breaks"])
        self.assertEqual(best["bic"], result["bic"])


class SingleBreakTestTests(unittest.TestCase):
    def test_flags_a_break_beyond_a_straight_line(self) -> None:
        result = single_break_test(_piecewise_linear(), n_permutations=199)
        self.assertTrue(result["significant"])
        self.assertLess(result["p_value"], 0.05)
        self.assertEqual(result["change_point"], 2011)

    def test_does_not_flag_a_noisy_straight_line(self) -> None:
        result = single_break_test(_noisy_line(), n_permutations=199, seed=7)
        self.assertFalse(result["significant"])
        self.assertGreater(result["p_value"], 0.05)

    def test_is_reproducible_for_a_given_seed(self) -> None:
        first = single_break_test(_piecewise_linear(), n_permutations=99, seed=3)
        second = single_break_test(_piecewise_linear(), n_permutations=99, seed=3)
        self.assertEqual(first["p_value"], second["p_value"])

    def test_rejects_a_non_positive_permutation_count(self) -> None:
        with self.assertRaises(BreakError):
            single_break_test(_piecewise_linear(), n_permutations=0)


class TrendTestTests(unittest.TestCase):
    def test_detects_a_monotone_trend(self) -> None:
        rising = [(float(2000 + i), 2.0 + i) for i in range(20)]
        result = trend_test(rising)
        self.assertAlmostEqual(result["tau"], 1.0)
        self.assertTrue(result["significant"])

    def test_rejects_too_few_points(self) -> None:
        with self.assertRaises(BreakError):
            trend_test([(2000.0, 1.0)])


class SummariseTests(unittest.TestCase):
    def test_labels_a_broken_series_nonstationary(self) -> None:
        result = summarise(_piecewise_linear(), n_permutations=199)
        self.assertEqual(result["stationarity"]["verdict"], "nonstationary")
        self.assertGreaterEqual(len(result["stationarity"]["reasons"]), 1)
        self.assertEqual(result["breaks"]["years"], [2011])

    def test_short_series_is_undetermined(self) -> None:
        result = summarise([(2000.0, 1.0), (2001.0, 1.1), (2002.0, 1.2)])
        self.assertEqual(result["stationarity"]["verdict"], "undetermined")
        self.assertIsNone(result["breaks"])
        self.assertIsNone(result["break_test"])


if __name__ == "__main__":
    unittest.main()
