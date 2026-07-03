import matplotlib
matplotlib.use('Agg')  # headless backend for CI

import unittest
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from data_service.visualization import (
    MatplotlibChartGenerator, RealTimeChartManager, DashboardChartGenerator
)


def make_ohlcv(n=30):
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    close = 100 + np.cumsum(np.random.default_rng(0).normal(0, 1, n))
    return pd.DataFrame({
        "open": close, "high": close + 1, "low": close - 1,
        "close": close, "volume": np.random.default_rng(1).integers(100, 1000, n),
    }, index=idx)


class TestMatplotlibChartGenerator(unittest.TestCase):
    def setUp(self):
        self.gen = MatplotlibChartGenerator()
        self.data = make_ohlcv()

    def test_candlestick_chart(self):
        fig = self.gen.create_candlestick_chart(self.data, "AAPL")
        self.assertIsNotNone(fig)
        self.assertEqual(len(fig.axes), 2)  # price + volume

    def test_candlestick_no_volume(self):
        data = self.data.drop(columns=["volume"])
        fig = self.gen.create_candlestick_chart(data, "AAPL")
        self.assertEqual(len(fig.axes), 1)

    def test_technical_analysis_chart(self):
        data = self.data.copy()
        data["sma_20"] = data["close"].rolling(5).mean()
        data["rsi"] = 50.0
        fig = self.gen.create_technical_analysis_chart(data, "AAPL")
        self.assertEqual(len(fig.axes), 3)

    def test_factor_analysis_chart(self):
        factor_df = pd.DataFrame({
            "momentum": np.random.randn(20), "value": np.random.randn(20),
        }, index=pd.date_range("2024-01-01", periods=20))
        fig = self.gen.create_factor_analysis_chart(factor_df, ["momentum", "value"])
        self.assertIsNotNone(fig)

    def test_portfolio_performance_chart(self):
        equity = pd.Series(
            100000 + np.cumsum(np.random.default_rng(2).normal(0, 100, 50)),
            index=pd.date_range("2024-01-01", periods=50),
        )
        fig = self.gen.create_portfolio_performance_chart(equity)
        self.assertEqual(len(fig.axes), 2)

    def test_heatmap_chart(self):
        df = pd.DataFrame({
            "x": ["a", "a", "b", "b"], "y": ["m", "n", "m", "n"], "v": [1, 2, 3, 4],
        })
        fig = self.gen.create_heatmap_chart(df, "x", "y", "v")
        self.assertIsNotNone(fig)

    def test_3d_surface_chart(self):
        x, y = np.meshgrid(np.linspace(0, 1, 5), np.linspace(0, 1, 5))
        z = x ** 2 + y ** 2
        fig = self.gen.create_3d_surface_chart(x, y, z)
        self.assertIsNotNone(fig)

    def test_export_chart(self):
        import tempfile, os
        fig = self.gen.create_candlestick_chart(self.data, "AAPL")
        f = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        f.close()
        try:
            self.gen.export_chart(fig, f.name, format="png")
            self.assertGreater(os.path.getsize(f.name), 0)
        finally:
            os.unlink(f.name)


class FakeTick:
    def __init__(self, symbol, price, timestamp, volume=10.0):
        self.symbol = symbol
        self.price = price
        self.timestamp = timestamp
        self.volume = volume


class TestRealTimeChartManager(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mgr = RealTimeChartManager(max_points=5, chart_generator=MatplotlibChartGenerator())

    def test_add_tick_and_buffer_cap(self):
        base = datetime(2024, 1, 1)
        for i in range(10):
            self.mgr.add_tick("BTCUSD", 100 + i, base + timedelta(seconds=i))
        ohlcv = self.mgr.get_ohlcv("BTCUSD")
        self.assertEqual(len(ohlcv), 5)  # capped at max_points

    def test_get_chart(self):
        base = datetime(2024, 1, 1)
        for i in range(3):
            self.mgr.add_tick("ETHUSD", 2000 + i, base + timedelta(seconds=i))
        fig = self.mgr.get_chart("ETHUSD")
        self.assertIsNotNone(fig)

    async def test_on_tick_async_handler(self):
        tick = FakeTick("BTCUSD", 50000, datetime.now())
        await self.mgr.on_tick(tick)
        self.assertIn("BTCUSD", self.mgr.symbols())

    def test_clear(self):
        self.mgr.add_tick("BTCUSD", 100, datetime.now())
        self.mgr.clear("BTCUSD")
        self.assertNotIn("BTCUSD", self.mgr.symbols())


class TestDashboardChartGenerator(unittest.TestCase):
    def setUp(self):
        self.dash = DashboardChartGenerator(MatplotlibChartGenerator())
        self.data = make_ohlcv()

    def test_overview_layout(self):
        figs = self.dash.build_overview_layout(self.data, "AAPL")
        self.assertGreaterEqual(len(figs), 1)

    def test_strategy_layout(self):
        equity = pd.Series(
            100000 + np.cumsum(np.random.default_rng(3).normal(0, 100, 30)),
            index=pd.date_range("2024-01-01", periods=30),
        )
        result = {"equity_curve": equity}
        figs = self.dash.build_strategy_layout(result)
        self.assertEqual(len(figs), 1)

    def test_strategy_layout_empty_without_equity_curve(self):
        self.assertEqual(self.dash.build_strategy_layout({}), [])

    def test_factor_layout(self):
        factor_df = pd.DataFrame({"momentum": np.random.randn(10), "value": np.random.randn(10)})
        figs = self.dash.build_factor_layout(factor_df)
        self.assertEqual(len(figs), 1)


if __name__ == "__main__":
    unittest.main()
