import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from data_service.signals import signal_sweep
from data_service.signals.signal_sweep import (
    ic_sweep,
    walk_forward_ic,
    cross_sectional_ls,
)


def _price_df(closes):
    idx = pd.date_range("2022-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({"close": closes}, index=idx)


def _basket(n_symbols=6, n_days=400, seed=0):
    rng = np.random.RandomState(seed)
    return {
        f"S{i}": _price_df(list(100 + np.cumsum(rng.randn(n_days))))
        for i in range(n_symbols)
    }


class TestICSweep(unittest.TestCase):
    def test_shape_and_aggregate(self):
        data = _basket()
        res = ic_sweep(data, horizons=[1, 5, 10])
        self.assertEqual(list(res["per_symbol"].columns), [1, 5, 10])
        self.assertEqual(len(res["per_symbol"]), 6)
        for h in [1, 5, 10]:
            agg = res["aggregate"][h]
            self.assertIn("mean_ic", agg)
            self.assertIn("frac_positive", agg)
            self.assertEqual(agg["n_symbols"], 6)

    def test_skips_empty(self):
        data = _basket(n_symbols=2)
        data["EMPTY"] = pd.DataFrame()
        res = ic_sweep(data, horizons=[1])
        self.assertEqual(len(res["per_symbol"]), 2)


class TestWalkForward(unittest.TestCase):
    def test_folds_count(self):
        df = _price_df(list(100 + np.cumsum(np.random.RandomState(1).randn(600))))
        wf = walk_forward_ic(df, horizon=5, n_splits=5)
        self.assertEqual(len(wf["folds"]), 5)
        self.assertIsNotNone(wf["mean_ic"])
        self.assertIsNotNone(wf["frac_positive"])

    def test_insufficient_data(self):
        wf = walk_forward_ic(_price_df([100, 101, 102]), n_splits=5)
        self.assertEqual(wf["folds"], [])
        self.assertIsNone(wf["mean_ic"])


class TestCrossSectionalLS(unittest.TestCase):
    def test_needs_enough_symbols(self):
        res = cross_sectional_ls(_basket(n_symbols=3))
        self.assertEqual(res["n_days"], 0)
        self.assertIn("note", res)

    def test_known_predictive_signal_is_profitable(self):
        # 4 symbols with deterministic, distinct daily drifts:
        # WIN rises fastest, LOSE falls. We patch the signal so WIN gets the
        # highest score and LOSE the lowest -> long WIN / short LOSE -> positive.
        n = 80
        drifts = {"WIN": 1.0, "MID1": 0.2, "MID2": -0.2, "LOSE": -1.0}
        data = {}
        for sym, d in drifts.items():
            closes = [100.0]
            for _ in range(n):
                closes.append(closes[-1] * (1 + d / 100.0))
            data[sym] = _price_df(closes)

        # Constant per-symbol score equal to its drift => stable cross-sectional rank.
        def fake_signal(df, close_col="close", weights=None):
            # Identify which symbol by matching first close path is fragile;
            # instead infer drift from the series itself.
            ret = df[close_col].pct_change().mean()
            score = np.clip(ret * 100, -1, 1)
            return pd.DataFrame({"score": [score] * len(df)}, index=df.index)

        with patch.object(signal_sweep, "compute_technical_signal_series", fake_signal):
            res = cross_sectional_ls(data, horizon=1, quantile=0.25)

        self.assertGreater(res["n_days"], 10)
        self.assertGreater(res["ls_ann_return"], 0)
        self.assertGreater(res["ls_sharpe"], 0)

    def test_reports_benchmark(self):
        res = cross_sectional_ls(_basket(n_symbols=8), horizon=1)
        self.assertIn("benchmark_ann_return", res)
        self.assertIn("benchmark_sharpe", res)
        self.assertIsInstance(res["ls_series"], pd.Series)


if __name__ == "__main__":
    unittest.main()
