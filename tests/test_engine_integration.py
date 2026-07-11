"""
Integration tests for the C++ quantmuse_engine <-> BacktestEngine wiring.

Skipped entirely if the quantmuse_engine extension hasn't been built (see
USAGE.md Sec.17):

    cmake -B backend/build -DBUILD_PYTHON_MODULE=ON backend
    cmake --build backend/build --target quantmuse_engine
    export PYTHONPATH="$PWD/backend/build:$PYTHONPATH"
"""

import unittest

import numpy as np
import pandas as pd

from data_service import engine
from data_service.backtest import BacktestEngine

skip_reason = "quantmuse_engine C++ extension not built (see USAGE.md Sec.17)"


def make_ohlcv(n=60, seed=0):
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    close = 100 + np.cumsum(np.random.default_rng(seed).normal(0, 1, n))
    return pd.DataFrame({
        "open": close, "high": close + 1, "low": close - 1,
        "close": close, "volume": 1000.0,
    }, index=idx)


def buy_then_sell_half(data, be):
    first, last = data.index[0], data.index[-1]
    qty = be.current_capital * 0.5 / data.loc[first, "close"]
    be.place_order("SYM", "buy", qty, data.loc[first, "close"], first)
    be.place_order("SYM", "sell", qty, data.loc[last, "close"], last)


def make_risk_limits(**overrides):
    limits = engine.RiskLimits()
    limits.max_position_size = overrides.get("max_position_size", 0.9)
    limits.max_leverage = overrides.get("max_leverage", 5.0)
    limits.max_drawdown = overrides.get("max_drawdown", 0.9)
    limits.daily_loss_limit = overrides.get("daily_loss_limit", 1e9)
    limits.position_concentration = overrides.get("position_concentration", 0.9)
    return limits


@unittest.skipUnless(engine.AVAILABLE, skip_reason)
class TestEngineAvailable(unittest.TestCase):
    def test_classes_exposed(self):
        for name in ("Order", "OrderSide", "OrderType", "OrderStatus", "MarketData",
                    "Position", "Portfolio", "RiskLimits", "RiskManager",
                    "OrderExecutor", "Strategy", "Signal", "MovingAverageStrategy"):
            self.assertIsNotNone(getattr(engine, name))


@unittest.skipUnless(engine.AVAILABLE, skip_reason)
class TestOrderPortfolioRoundTrip(unittest.TestCase):
    def test_order_lifecycle(self):
        order = engine.Order("AAPL", engine.OrderSide.BUY, engine.OrderType.MARKET, 10.0)
        self.assertEqual(order.get_status(), engine.OrderStatus.PENDING)
        order.set_price(150.0)
        self.assertEqual(order.get_price(), 150.0)

    def test_portfolio_valuation(self):
        portfolio = engine.Portfolio()
        portfolio.update_position("AAPL", 10, 150.0)
        total = portfolio.get_total_value({"AAPL": 155.0})
        self.assertAlmostEqual(total, portfolio.get_cash() + 10 * 155.0)


@unittest.skipUnless(engine.AVAILABLE, skip_reason)
class TestOrderExecutor(unittest.TestCase):
    def test_submit_and_fill(self):
        executor = engine.OrderExecutor()
        executor.start()
        try:
            order = engine.Order("AAPL", engine.OrderSide.BUY, engine.OrderType.MARKET, 5.0)
            executor.submit_order(order)
            import time
            for _ in range(200):
                if executor.get_order_status(order.get_order_id()) != engine.OrderStatus.PENDING:
                    break
                time.sleep(0.001)
            self.assertEqual(executor.get_order_status(order.get_order_id()),
                            engine.OrderStatus.FILLED)
        finally:
            executor.stop()

    def test_cancel(self):
        executor = engine.OrderExecutor()  # not started -- order stays queued
        order = engine.Order("AAPL", engine.OrderSide.SELL, engine.OrderType.MARKET, 5.0)
        executor.submit_order(order)
        executor.cancel_order(order.get_order_id())
        self.assertEqual(executor.get_order_status(order.get_order_id()),
                        engine.OrderStatus.CANCELLED)

    def test_unknown_order_id_raises(self):
        executor = engine.OrderExecutor()
        with self.assertRaises(RuntimeError):
            executor.get_order_status("nonexistent")


@unittest.skipUnless(engine.AVAILABLE, skip_reason)
class TestBacktestEngineCppRiskManager(unittest.TestCase):
    def test_no_attachment_behaves_as_before(self):
        be = BacktestEngine(100000)
        be.run_backtest(make_ohlcv(), buy_then_sell_half)
        self.assertEqual(len(be.trades), 2)

    def test_generous_limits_allow_trades(self):
        be = BacktestEngine(100000)
        be.attach_cpp_risk_manager(engine.RiskManager(make_risk_limits()))
        be.run_backtest(make_ohlcv(), buy_then_sell_half)
        self.assertEqual(len(be.trades), 2)

    def test_tight_limits_reject_trades(self):
        be = BacktestEngine(100000)
        tight = make_risk_limits(max_position_size=0.0001)
        be.attach_cpp_risk_manager(engine.RiskManager(tight))
        be.run_backtest(make_ohlcv(), buy_then_sell_half)
        self.assertEqual(len(be.trades), 0)

    def test_sell_of_existing_position_is_not_penalized_as_a_double(self):
        """Regression test for the concentration-check sign bug: a sell of an
        existing position must not be evaluated as if it doubled exposure.

        0.6 straddles the two outcomes: the initial buy's concentration is
        ~0.5 (passes either way); the closing sell's concentration is ~0 once
        fixed (signed BUY/SELL delta) but ~1.0 under the old bug (which added
        the sell quantity to the existing position instead of subtracting).
        """
        be = BacktestEngine(100000)
        limits = make_risk_limits(position_concentration=0.6)
        be.attach_cpp_risk_manager(engine.RiskManager(limits))
        be.run_backtest(make_ohlcv(), buy_then_sell_half)
        self.assertEqual(len(be.trades), 2)


@unittest.skipUnless(engine.AVAILABLE, skip_reason)
class TestBacktestEngineCppExecutor(unittest.TestCase):
    def test_executor_processes_every_trade(self):
        be = BacktestEngine(100000)
        executor = engine.OrderExecutor()
        be.attach_cpp_executor(executor)
        try:
            be.run_backtest(make_ohlcv(), buy_then_sell_half)
            self.assertEqual(len(be.trades), 2)
        finally:
            executor.stop()

    def test_both_attached_together(self):
        be = BacktestEngine(100000)
        be.attach_cpp_risk_manager(engine.RiskManager(make_risk_limits()))
        executor = engine.OrderExecutor()
        be.attach_cpp_executor(executor)
        try:
            be.run_backtest(make_ohlcv(), buy_then_sell_half)
            self.assertEqual(len(be.trades), 2)
        finally:
            executor.stop()


if __name__ == "__main__":
    unittest.main()
