"""Tests for association and temporal-stability analysis (milestone M4)."""

from __future__ import annotations

import random
import unittest

from sohbc.associations import (
    AssociationError,
    associate,
    stability,
    within_regime,
)


def _line(slope: float, intercept: float = 0.0, n: int = 12) -> list[tuple[float, float]]:
    return [(2000.0 + i, intercept + slope * i) for i in range(n)]


def _noisy(slope: float, seed: int = 0, noise: float = 1.0, n: int = 20):
    generator = random.Random(seed)
    x = [(2000.0 + i, float(i)) for i in range(n)]
    y = [
        (2000.0 + i, slope * i + generator.uniform(-noise, noise)) for i in range(n)
    ]
    return y, x


class AssociateTests(unittest.TestCase):
    def test_perfect_positive_relationship(self) -> None:
        result = associate(_line(2.0), _line(1.0, intercept=5.0))
        self.assertAlmostEqual(result["pearson"]["r"], 1.0)
        self.assertAlmostEqual(result["spearman"]["rho"], 1.0)
        self.assertAlmostEqual(result["ols"]["slope"], 2.0)
        self.assertTrue(result["ols"]["significant"])

    def test_perfect_negative_relationship(self) -> None:
        result = associate(_line(2.0), _line(-1.0))
        self.assertAlmostEqual(result["pearson"]["r"], -1.0)
        self.assertLess(result["ols"]["slope"], 0)

    def test_states_the_estimation_window(self) -> None:
        result = associate(_line(1.0), _line(1.0))
        self.assertEqual(result["window"]["start"], 2000)
        self.assertEqual(result["window"]["end"], 2011)
        self.assertEqual(result["window"]["n"], 12)

    def test_aligns_on_shared_periods_only(self) -> None:
        outcome = [
            (2000.0, 1.0), (2001.0, 2.0), (2002.0, 3.0), (2003.0, 4.0),
            (2004.0, 5.0), (2005.0, 6.0),
        ]
        determinant = [
            (2001.0, 5.0), (2002.0, 4.0), (2003.0, 3.0), (2004.0, 2.0),
            (2005.0, 1.0), (2006.0, 0.0),
        ]
        result = associate(outcome, determinant)
        self.assertEqual(result["window"]["start"], 2001)
        self.assertEqual(result["window"]["end"], 2005)
        self.assertEqual(result["window"]["n"], 5)

    def test_rejects_too_few_shared_periods(self) -> None:
        with self.assertRaises(AssociationError):
            associate(_line(1.0, n=3), _line(1.0, n=3))

    def test_rejects_a_constant_determinant(self) -> None:
        outcome = _line(1.0)
        determinant = [(2000.0 + i, 7.0) for i in range(12)]
        with self.assertRaises(AssociationError):
            associate(outcome, determinant)

    def test_noisy_relationship_is_detected(self) -> None:
        y, x = _noisy(slope=1.0, seed=3, noise=1.0)
        result = associate(y, x)
        self.assertTrue(result["ols"]["significant"])
        self.assertGreater(result["pearson"]["r"], 0.8)


class StabilityTests(unittest.TestCase):
    def test_constant_relationship_is_stable(self) -> None:
        y, x = _noisy(slope=2.0, seed=1, noise=1.0, n=24)
        result = stability(y, x, n_subperiods=3, window=8)
        self.assertTrue(result["stability"]["stable"])
        self.assertEqual(result["stability"]["verdict"], "stable")

    def test_sign_flip_across_subperiods_is_time_varying(self) -> None:
        x = [(2000.0 + i, float(i)) for i in range(24)]
        first = [(2000.0 + i, 2.0 * i) for i in range(12)]
        second = [(2012.0 + i, 2.0 * 11 - 2.0 * i) for i in range(12)]
        result = stability(first + second, x, n_subperiods=2, window=8)
        self.assertFalse(result["stability"]["stable"])
        self.assertEqual(result["stability"]["verdict"], "time-varying")
        self.assertIn(
            "subperiod estimates disagree in sign", result["stability"]["reasons"]
        )

    def test_magnitude_shift_is_time_varying(self) -> None:
        x = [(2000.0 + i, float(i)) for i in range(24)]
        slow = [(2000.0 + i, 0.1 * i) for i in range(12)]
        fast = [(2012.0 + i, 0.1 * 11 + 10.0 * i) for i in range(12)]
        result = stability(slow + fast, x, n_subperiods=2, window=8)
        self.assertFalse(result["stability"]["stable"])

    def test_short_series_is_undetermined_not_vacuously_stable(self) -> None:
        # 10 points cannot make two 5-point subperiods, so stability is
        # undetermined rather than trivially "stable".
        y, x = _noisy(slope=1.0, seed=6, noise=1.0, n=10)
        result = stability(y, x, n_subperiods=3, window=8)
        self.assertEqual(result["stability"]["verdict"], "undetermined")
        self.assertFalse(result["stability"]["stable"])

    def test_reports_subperiod_and_rolling_estimates(self) -> None:
        y, x = _noisy(slope=1.0, seed=2, noise=1.0, n=20)
        result = stability(y, x, n_subperiods=4, window=8)
        self.assertGreaterEqual(len(result["subperiods"]), 2)
        self.assertEqual(len(result["rolling"]), 20 - 8 + 1)
        for estimate in result["rolling"]:
            self.assertEqual(estimate["end"] - estimate["start"], 7)

    def test_pooled_estimate_is_always_reported(self) -> None:
        y, x = _noisy(slope=1.0, seed=4, noise=1.0, n=20)
        result = stability(y, x)
        self.assertIn("pooled", result)
        self.assertIn("window", result["pooled"])

    def test_rejects_short_series(self) -> None:
        with self.assertRaises(AssociationError):
            stability(_line(1.0, n=3), _line(1.0, n=3))


class WithinRegimeTests(unittest.TestCase):
    def test_splits_at_dated_regime(self) -> None:
        x = [(2000.0 + i, float(i)) for i in range(20)]
        first = [(2000.0 + i, 1.0 * i) for i in range(10)]
        second = [(2010.0 + i, 1.0 * 9 - 1.0 * i) for i in range(10)]
        result = within_regime(first + second, x, [2010])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["window"]["start"], 2000)
        self.assertEqual(result[1]["window"]["start"], 2010)
        self.assertGreater(result[0]["ols"]["slope"], 0)
        self.assertLess(result[1]["ols"]["slope"], 0)

    def test_skips_regimes_that_are_too_short(self) -> None:
        x = [(2000.0 + i, float(i)) for i in range(20)]
        y = [(2000.0 + i, 1.0 * i) for i in range(10)] + [
            (2010.0 + i, 9.0 - i) for i in range(10)
        ]
        result = within_regime(y, x, [2002, 2010])
        self.assertTrue(all(estimate["window"]["n"] >= 5 for estimate in result))

    def test_ignores_regimes_outside_the_window(self) -> None:
        y, x = _noisy(slope=1.0, seed=5, noise=1.0, n=20)
        result = within_regime(y, x, [1990, 2100])
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
