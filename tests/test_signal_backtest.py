import unittest

import numpy as np
import pandas as pd

from data_service.backtest.backtest_engine import BacktestEngine
from data_service.signals.signal_backtest import (
    compute_technical_signal_series,
    evaluate_predictive_value,
    make_signal_strategy,
    long_flat_backtest,
    _rsi,
)


def _price_df(closes):
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({"close": closes, "symbol": "TEST"}, index=idx)


class TestIndicators(unittest.TestCase):
    def test_rsi_bounds_and_uptrend(self):
        closes = pd.Series(np.linspace(100, 200, 100))
        rsi = _rsi(closes).dropna()
        self.assertTrue((rsi >= 0).all() and (rsi <= 100).all())
        # Pure uptrend -> RSI should be very high.
        self.assertGreater(rsi.iloc[-1], 90)


class TestSignalSeries(unittest.TestCase):
    def test_columns_and_range(self):
        closes = list(100 + np.cumsum(np.random.RandomState(0).randn(200)))
        sig = compute_technical_signal_series(_price_df(closes))
        for col in ("rsi_score", "macd_score", "score", "label"):
            self.assertIn(col, sig.columns)
        valid = sig["score"].dropna()
        self.assertTrue((valid >= -1).all() and (valid <= 1).all())

    def test_uptrend_is_not_bullish_on_rsi(self):
        # Strong uptrend -> high RSI -> RSI score should be negative (overbought).
        closes = list(np.linspace(100, 300, 120))
        sig = compute_technical_signal_series(_price_df(closes))
        self.assertLess(sig["rsi_score"].dropna().iloc[-1], 0)


class TestPredictiveValue(unittest.TestCase):
    def test_insufficient_data(self):
        ev = evaluate_predictive_value(_price_df([100, 101, 102, 103]))
        self.assertIsNone(ev["ic"])
        self.assertEqual(ev["n"], None) if ev.get("n") is None else self.assertLess(ev["n"], 30)

    def test_returns_ic_on_sufficient_data(self):
        rng = np.random.RandomState(42)
        closes = list(100 + np.cumsum(rng.randn(400)))
        ev = evaluate_predictive_value(_price_df(closes), horizon=5)
        self.assertIsInstance(ev["n"], int)
        self.assertGreater(ev["n"], 100)
        self.assertIsNotNone(ev["ic"])
        self.assertGreaterEqual(ev["ic"], -1.0)
        self.assertLessEqual(ev["ic"], 1.0)
        self.assertIsNotNone(ev["hit_rate"])
        self.assertEqual(len(ev["bucket_returns"]), 5)

    def test_rsi_component_sign_on_mean_reverting_series(self):
        # On a mean-reverting series, oversold (low RSI -> positive rsi_score)
        # precedes rises, so the RSI component should rank-correlate positively
        # with forward returns. This validates the RSI mapping sign + that the
        # evaluation machinery detects a known relationship.
        rng = np.random.RandomState(1)
        x = [100.0]
        for _ in range(600):
            x.append(x[-1] + (100 - x[-1]) * 0.1 + rng.randn() * 2)
        df = _price_df(x)
        sig = compute_technical_signal_series(df)
        fwd = df["close"].shift(-5) / df["close"] - 1.0
        joined = pd.DataFrame(
            {"rsi": sig["rsi_score"], "fwd": fwd}
        ).dropna()
        ic_rsi = joined["rsi"].rank().corr(joined["fwd"].rank())
        self.assertGreater(ic_rsi, 0.0)


class TestSignalStrategyBacktest(unittest.TestCase):
    def test_runs_through_engine(self):
        rng = np.random.RandomState(7)
        closes = list(100 + np.cumsum(rng.randn(300)))
        df = _price_df(closes)
        engine = BacktestEngine(initial_capital=100_000, commission_rate=0.001)
        strat = make_signal_strategy()
        results = engine.run_backtest(df, strat)
        # Should produce a results dict and not crash; trades may be >0.
        self.assertIn("total_return", results)
        self.assertIsInstance(results["total_trades"], int)

    def test_no_lookahead(self):
        # A signal at bar t must not depend on future bars: computing on a
        # truncated history must reproduce the earlier values exactly.
        rng = np.random.RandomState(3)
        closes = list(100 + np.cumsum(rng.randn(250)))
        full = compute_technical_signal_series(_price_df(closes))
        k = 150
        partial = compute_technical_signal_series(_price_df(closes[:k]))
        a = full["score"].iloc[:k].reset_index(drop=True)
        b = partial["score"].reset_index(drop=True)
        pd.testing.assert_series_equal(a, b, check_names=False)


if __name__ == "__main__":
    unittest.main()


class TestLongFlatBacktest(unittest.TestCase):
    def test_structure_and_bounds(self):
        rng = np.random.RandomState(5)
        df = _price_df(list(100 + np.cumsum(rng.randn(400))))
        r = long_flat_backtest(df, entry=0.3, exit=0.0)
        for key in ("ann_return", "ann_vol", "sharpe", "max_drawdown"):
            self.assertIn(key, r["strategy"])
            self.assertIn(key, r["benchmark"])
        self.assertGreaterEqual(r["time_in_market"], 0.0)
        self.assertLessEqual(r["time_in_market"], 1.0)
        self.assertGreaterEqual(r["n_trades"], 0)
        self.assertLessEqual(r["strategy"]["max_drawdown"], 0.0)

    def test_no_lookahead_positions(self):
        # Flat at the start until the first signal can possibly act (shifted).
        rng = np.random.RandomState(6)
        df = _price_df(list(100 + np.cumsum(rng.randn(300))))
        r = long_flat_backtest(df)
        # Equity starts at ~1.0 (first bar return neutralized by shift).
        self.assertAlmostEqual(float(r["equity_curve"].iloc[0]), 1.0, places=6)

    def test_position_mechanics_with_controlled_signal(self):
        # Deterministic test of the entry/exit + next-bar execution logic:
        # patch the signal so it is bullish for the first half, then flat.
        from unittest.mock import patch
        from data_service.signals import signal_backtest as sb

        n = 20
        closes = [100.0 * (1.01 ** i) for i in range(n)]  # +1%/day
        df = _price_df(closes)
        score = pd.Series([1.0] * (n // 2) + [-1.0] * (n // 2), index=df.index)

        def fake(_df, close_col="close", weights=None):
            return pd.DataFrame({"score": score})

        with patch.object(sb, "compute_technical_signal_series", fake):
            r = long_flat_backtest(df, entry=0.3, exit=0.0, cost_bps=0.0)

        # Entered early and exited mid-way -> held roughly the first half.
        self.assertGreater(r["time_in_market"], 0.3)
        self.assertLess(r["time_in_market"], 0.7)
        # Held during a steady rise -> strictly positive strategy return.
        self.assertGreater(r["strategy"]["ann_return"], 0.0)
        self.assertEqual(r["n_trades"], 2)  # one entry, one exit
