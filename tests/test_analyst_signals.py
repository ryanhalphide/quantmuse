import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

from data_service.signals.analyst_signals import (
    consensus_score,
    revision_signal,
    evaluate_orthogonality,
    evaluate_signal_orthogonality,
)
from data_service.fetchers.fmp_fetcher import FMPFetcher


def _grades(dates, sb, b, h, s, ss):
    return pd.DataFrame(
        {"strong_buy": sb, "buy": b, "hold": h, "sell": s, "strong_sell": ss},
        index=pd.to_datetime(dates),
    )


class TestConsensusScore(unittest.TestCase):
    def test_all_strong_buy_is_plus_one(self):
        g = _grades(["2026-01-01"], [10], [0], [0], [0], [0])
        self.assertEqual(consensus_score(g).iloc[0], 1.0)

    def test_all_strong_sell_is_minus_one(self):
        g = _grades(["2026-01-01"], [0], [0], [0], [0], [10])
        self.assertEqual(consensus_score(g).iloc[0], -1.0)

    def test_all_hold_is_zero(self):
        g = _grades(["2026-01-01"], [0], [0], [10], [0], [0])
        self.assertEqual(consensus_score(g).iloc[0], 0.0)

    def test_empty(self):
        self.assertTrue(consensus_score(pd.DataFrame()).empty)


class TestRevisionSignal(unittest.TestCase):
    def test_upgrade_is_positive(self):
        g = _grades(
            ["2026-01-01", "2026-02-01"],
            [0, 5], [10, 5], [0, 0], [0, 0], [0, 0],
        )
        rev = revision_signal(g)
        self.assertTrue(np.isnan(rev.iloc[0]))
        self.assertGreater(rev.iloc[1], 0)  # consensus rose -> positive revision


class TestOrthogonality(unittest.TestCase):
    def test_underpowered_returns_note(self):
        price = {"A": pd.DataFrame(
            {"close": list(100 + np.arange(40))},
            index=pd.date_range("2024-01-01", periods=40, freq="D"),
        )}
        grades = {"A": _grades(
            ["2024-01-01", "2024-02-01"], [5, 6], [5, 5], [1, 1], [0, 0], [0, 0]
        )}
        res = evaluate_orthogonality(price, grades, min_n=50)
        self.assertIn("note", res)
        self.assertLess(res["n"], 50)

    def test_pools_and_reports_metrics_when_sufficient(self):
        # Build many symbols with enough monthly history to exceed min_n.
        rng = np.random.RandomState(0)
        price_data, analyst_data = {}, {}
        months = pd.date_range("2018-01-01", periods=60, freq="MS")
        for i in range(20):
            daily = pd.date_range("2018-01-01", periods=60 * 22, freq="D")
            closes = 100 + np.cumsum(rng.randn(len(daily)))
            price_data[f"S{i}"] = pd.DataFrame({"close": closes}, index=daily)
            sb = rng.randint(0, 10, size=len(months))
            analyst_data[f"S{i}"] = pd.DataFrame(
                {"strong_buy": sb, "buy": rng.randint(0, 10, len(months)),
                 "hold": rng.randint(0, 5, len(months)),
                 "sell": rng.randint(0, 3, len(months)),
                 "strong_sell": rng.randint(0, 2, len(months))},
                index=months,
            )
        res = evaluate_orthogonality(price_data, analyst_data, min_n=50)
        self.assertGreaterEqual(res["n"], 50)
        self.assertIn("signal_correlation", res)
        self.assertIsNotNone(res["ic_technical"])


class TestGenericOrthogonality(unittest.TestCase):
    def test_recovers_known_signal_with_arbitrary_series(self):
        # A provider-agnostic signal that *is* next-month return should show a
        # strongly positive IC -- validates the generic pooling/alignment path.
        rng = np.random.RandomState(2)
        price_data, signal_data = {}, {}
        months = pd.date_range("2018-01-01", periods=60, freq="MS")
        for i in range(10):
            daily = pd.date_range("2018-01-01", periods=60 * 22, freq="D")
            closes = 100 + np.cumsum(rng.randn(len(daily)))
            df = pd.DataFrame({"close": closes}, index=daily)
            price_data[f"S{i}"] = df
            close_m = df["close"].resample("MS").first()
            fwd = close_m.shift(-1) / close_m - 1.0
            signal_data[f"S{i}"] = fwd.reindex(months).fillna(0.0)  # "leaks" fwd ret
        res = evaluate_signal_orthogonality(price_data, signal_data, min_n=50)
        self.assertGreaterEqual(res["n"], 50)
        self.assertIn("ic_signal", res)
        self.assertGreater(res["ic_signal"], 0.5)  # signal == fwd ret -> high IC


class TestFMPFetcher(unittest.TestCase):
    def test_requires_key(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError):
                FMPFetcher(api_key=None)

    def test_parses_grades_history(self):
        fetcher = FMPFetcher(api_key="K")
        fetcher._get = Mock(return_value=[
            {"symbol": "AAPL", "date": "2026-06-01", "analystRatingsStrongBuy": 7,
             "analystRatingsBuy": 23, "analystRatingsHold": 15,
             "analystRatingsSell": 1, "analystRatingsStrongSell": 2},
            {"symbol": "AAPL", "date": "2026-05-01", "analystRatingsStrongBuy": 7,
             "analystRatingsBuy": 25, "analystRatingsHold": 16,
             "analystRatingsSell": 1, "analystRatingsStrongSell": 2},
        ])
        df = fetcher.get_analyst_grades_history("AAPL")
        self.assertEqual(list(df.columns), ["strong_buy", "buy", "hold", "sell", "strong_sell"])
        self.assertEqual(len(df), 2)
        self.assertTrue(df.index.is_monotonic_increasing)  # sorted ascending

    def test_empty_grades(self):
        fetcher = FMPFetcher(api_key="K")
        fetcher._get = Mock(return_value=[])
        self.assertTrue(fetcher.get_analyst_grades_history("AAPL").empty)


if __name__ == "__main__":
    unittest.main()
