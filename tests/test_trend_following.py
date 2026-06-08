import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

from data_service.strategies.trend_following import (
    TSMOMConfig,
    compute_forecast_series,
    realized_vol,
    build_weights,
    tsmom_backtest,
    run_both_directions,
    live_target_weights,
    _ewmac_forecast,
)
from data_service.strategies.trend_following_robustness import (
    walk_forward,
    parameter_sensitivity,
    per_asset_contribution,
    correlation_to_benchmark,
    core_plus_trend,
)


def _trending_df(n=600, drift=0.0008, noise=0.008, seed=0, start="2018-01-01"):
    """Geometric price series with a (possibly negative) drift + noise."""
    rng = np.random.RandomState(seed)
    rets = drift + noise * rng.randn(n)
    close = 100.0 * np.cumprod(1.0 + rets)
    idx = pd.date_range(start, periods=n, freq="B")
    return pd.DataFrame({"close": close}, index=idx)


def _panel(specs):
    """specs: dict sym -> kwargs for _trending_df."""
    return {sym: _trending_df(**kw) for sym, kw in specs.items()}


def _basket(n_up=6, n_days=600):
    return _panel({f"S{i}": dict(drift=0.0008, noise=0.01, seed=i, n=n_days)
                   for i in range(n_up)})


class TestForecast(unittest.TestCase):
    def test_forecast_within_cap(self):
        cfg = TSMOMConfig()
        fc = compute_forecast_series(_trending_df()["close"], cfg).dropna()
        self.assertTrue((fc.abs() <= cfg.forecast_cap + 1e-9).all())

    def test_uptrend_positive_downtrend_negative(self):
        up = _ewmac_forecast(_trending_df(drift=0.002, noise=0.004)["close"], 16, 64, 33).dropna()
        dn = _ewmac_forecast(_trending_df(drift=-0.002, noise=0.004)["close"], 16, 64, 33).dropna()
        self.assertGreater(up.iloc[-1], 0)
        self.assertLess(dn.iloc[-1], 0)

    def test_no_lookahead(self):
        # Forecast for the first k bars must not change when later data is appended.
        cfg = TSMOMConfig()
        close = _trending_df(n=500, seed=3)["close"]
        full = compute_forecast_series(close, cfg)
        k = 300
        partial = compute_forecast_series(close.iloc[:k], cfg)
        a = full.iloc[:k].reset_index(drop=True)
        b = partial.reset_index(drop=True)
        pd.testing.assert_series_equal(a, b, check_names=False)


class TestVolTargeting(unittest.TestCase):
    def test_realized_vol_recovers_known_vol(self):
        rng = np.random.RandomState(0)
        daily = 0.01  # 1% daily -> ~15.9% annualized
        close = pd.Series(100 * np.cumprod(1 + daily * rng.randn(4000)),
                          index=pd.date_range("2015-01-01", periods=4000, freq="B"))
        rv = realized_vol(close, lookback=33).dropna()
        self.assertAlmostEqual(rv.iloc[-1], daily * np.sqrt(252), delta=0.05)

    def test_strategy_vol_near_target(self):
        cfg = TSMOMConfig(portfolio_target_vol=0.15)
        res = tsmom_backtest(_basket(n_up=8, n_days=1500), cfg)
        realized = res["strat_returns"].std() * np.sqrt(252)
        # EWMA targeting is approximate; allow a wide-but-meaningful band.
        self.assertGreater(realized, 0.05)
        self.assertLess(realized, 0.35)


class TestDirection(unittest.TestCase):
    def test_long_flat_never_shorts(self):
        cfg = TSMOMConfig(direction="long_flat")
        res = tsmom_backtest(_basket(), cfg)
        self.assertTrue((res["weights"].values >= -1e-9).all())

    def test_long_short_can_short_downtrend(self):
        data = _panel({"DOWN": dict(drift=-0.002, noise=0.004, n=600),
                       "UP": dict(drift=0.002, noise=0.004, n=600, seed=1)})
        res = tsmom_backtest(data, TSMOMConfig(direction="long_short"))
        self.assertLess(res["weights"]["DOWN"].min(), 0)


class TestBacktestMechanics(unittest.TestCase):
    def test_uptrend_basket_is_profitable(self):
        # The key controlled test: a clearly trending-up basket MUST make money.
        res = tsmom_backtest(_basket(n_up=6, n_days=800), TSMOMConfig())
        self.assertGreater(res["strategy"]["ann_return"], 0.0)
        self.assertGreater(res["strategy"]["sharpe"], 0.0)

    def test_costs_reduce_returns(self):
        data = _basket()
        lo = tsmom_backtest(data, TSMOMConfig(cost_bps=1.0))["equity_curve"].iloc[-1]
        hi = tsmom_backtest(data, TSMOMConfig(cost_bps=50.0))["equity_curve"].iloc[-1]
        self.assertGreater(lo, hi)

    def test_equity_starts_at_one(self):
        res = tsmom_backtest(_basket(), TSMOMConfig())
        self.assertAlmostEqual(float(res["equity_curve"].iloc[0]), 1.0, places=6)

    def test_different_start_dates(self):
        data = _panel({"SPY": dict(n=600, seed=0, start="2018-01-01"),
                       "LATE": dict(n=300, seed=1, start="2019-06-03")})
        res = tsmom_backtest(data, TSMOMConfig())  # must not raise
        # LATE contributes 0 before it exists.
        early = res["held"]["LATE"].loc[:"2019-06-01"].abs().sum()
        self.assertEqual(early, 0.0)

    def test_benchmarks_present_when_spy_tlt(self):
        data = _panel({"SPY": dict(n=700, seed=0), "TLT": dict(n=700, seed=1, drift=0.0002)})
        res = tsmom_backtest(data, TSMOMConfig())
        self.assertIn("benchmark_spy", res)
        self.assertIn("benchmark_6040", res)
        self.assertIn("corr_to_spy", res)


class TestRobustness(unittest.TestCase):
    def test_walk_forward_structure(self):
        wf = walk_forward(_basket(n_days=1200), TSMOMConfig(), n_splits=4)
        self.assertEqual(len(wf["folds"]), 4)
        self.assertGreaterEqual(wf["frac_positive"], 0.0)
        self.assertLessEqual(wf["frac_positive"], 1.0)

    def test_parameter_sensitivity_covers_grid(self):
        ps = parameter_sensitivity(
            _basket(n_days=900), TSMOMConfig(),
            speed_grid=(((16, 64),), ((32, 128),)),
            vol_lookbacks=(33,), target_vols=(0.15,))
        self.assertEqual(ps["n"], 2)
        self.assertIn("mean_sharpe", ps)

    def test_per_asset_contribution_and_corr(self):
        data = _panel({"SPY": dict(n=700, seed=0), "X": dict(n=700, seed=2)})
        res = tsmom_backtest(data, TSMOMConfig())
        contrib = per_asset_contribution(res)
        self.assertEqual(set(contrib.index), {"SPY", "X"})
        corr = correlation_to_benchmark(res, "SPY")
        self.assertIn("corr", corr)

    def test_core_plus_trend_blend(self):
        data = _panel({"SPY": dict(n=700, seed=0), "X": dict(n=700, seed=2)})
        res = tsmom_backtest(data, TSMOMConfig())
        blend = core_plus_trend(res, core="SPY", trend_weights=(0.3, 0.5))
        self.assertEqual(len(blend), 3)  # core + two blends
        self.assertIn("sharpe", blend.columns)


class TestLiveSignal(unittest.TestCase):
    def test_live_matches_backtest_last_row(self):
        data = _basket()
        cfg = TSMOMConfig()
        live = live_target_weights(data, cfg)
        bt = tsmom_backtest(data, cfg)
        for sym in bt["weights"].columns:
            self.assertAlmostEqual(live.loc[sym, "target_weight"],
                                   bt["weights"].iloc[-1][sym], places=8)

    def test_both_directions(self):
        out = run_both_directions(_basket(), TSMOMConfig())
        self.assertIn("long_short", out)
        self.assertIn("long_flat", out)


class TestDataLoader(unittest.TestCase):
    def test_binance_pagination(self):
        from data_service.strategies import trend_following_data as tfd
        # Two full 1000-row chunks then a short one -> loader should stop after the short.
        idx1 = pd.date_range("2018-01-01", periods=1000, freq="D")
        idx2 = pd.date_range("2020-09-27", periods=1000, freq="D")
        idx3 = pd.date_range("2023-06-23", periods=50, freq="D")
        chunks = [pd.DataFrame({"close": np.arange(1000.0)}, index=idx1),
                  pd.DataFrame({"close": np.arange(1000.0)}, index=idx2),
                  pd.DataFrame({"close": np.arange(50.0)}, index=idx3)]
        fake = Mock()
        fake.fetch_historical_data = Mock(side_effect=chunks)
        from datetime import datetime
        with patch.object(tfd, "_make_binance_fetcher", return_value=fake):
            df = tfd._fetch_binance_paginated("BTCUSDT", datetime(2018, 1, 1), datetime(2024, 1, 1))
        self.assertGreater(len(df), 1000)
        self.assertFalse(df.index.duplicated().any())
        self.assertEqual(fake.fetch_historical_data.call_count, 3)

    def test_align_calendar_mixes_tz(self):
        from data_service.strategies.trend_following_data import align_calendar, _normalize
        spy = _normalize(pd.DataFrame(
            {"close": np.arange(10.0)},
            index=pd.date_range("2022-01-03", periods=10, freq="B", tz="UTC")))  # tz-aware
        btc = _normalize(pd.DataFrame(
            {"close": np.arange(14.0)},
            index=pd.date_range("2022-01-01", periods=14, freq="D")))            # tz-naive 7d/wk
        aligned = align_calendar({"SPY": spy, "BTC": btc}, anchor="SPY")
        self.assertTrue(aligned["SPY"].index.equals(aligned["BTC"].index))
        self.assertIsNone(aligned["BTC"].index.tz)


if __name__ == "__main__":
    unittest.main()
