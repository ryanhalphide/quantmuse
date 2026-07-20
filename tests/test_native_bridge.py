"""
Tests for the additive Portfolio/RiskManager methods (mark_to_market,
seed_equity_history, set_cash, get_last_rejection_reason) and the
data_service.execution advisory risk-check layer built on them.

Skipped entirely if the quantmuse_engine extension hasn't been built (see
USAGE.md Sec.17), matching tests/test_engine_integration.py's convention:

    cmake -B backend/build -DBUILD_PYTHON_MODULE=ON backend
    cmake --build backend/build --target quantmuse_engine
    export PYTHONPATH="$PWD/backend/build:$PYTHONPATH"
"""

import unittest

import pandas as pd

from data_service import engine

skip_reason = "quantmuse_engine C++ extension not built (see USAGE.md Sec.17)"


def _loose_limits():
    limits = engine.RiskLimits()
    limits.max_position_size = 1e9
    limits.max_drawdown = 1e9
    limits.max_leverage = 1e9
    limits.daily_loss_limit = 1e9
    limits.position_concentration = 1e9
    return limits


@unittest.skipUnless(engine.AVAILABLE, skip_reason)
class TestPortfolioMarkToMarket(unittest.TestCase):
    def test_well_sized_order_passes(self):
        limits = _loose_limits()
        limits.max_position_size = 0.10
        rm = engine.RiskManager(limits)
        p = engine.Portfolio()
        p.set_cash(10000.0)
        rm.update_current_prices({})
        p.mark_to_market({})

        order = engine.Order("AAPL", engine.OrderSide.BUY, engine.OrderType.MARKET, 10)
        order.set_price(50.0)  # $500 / $10,000 = 5%

        self.assertTrue(rm.check_order_risk(order, p))
        self.assertEqual(rm.get_last_rejection_reason(), "")

    def test_position_size_limit_blocks(self):
        limits = _loose_limits()
        limits.max_position_size = 0.10
        rm = engine.RiskManager(limits)
        p = engine.Portfolio()
        p.set_cash(10000.0)
        rm.update_current_prices({})
        p.mark_to_market({})

        order = engine.Order("AAPL", engine.OrderSide.BUY, engine.OrderType.MARKET, 30)
        order.set_price(50.0)  # $1,500 / $10,000 = 15%

        self.assertFalse(rm.check_order_risk(order, p))
        self.assertEqual(rm.get_last_rejection_reason(), "position_size_limit")

    def test_leverage_limit_blocks(self):
        limits = _loose_limits()
        limits.max_leverage = 1.2
        rm = engine.RiskManager(limits)
        p = engine.Portfolio()
        p.set_cash(-2000.0)  # margin debit
        p.update_position("SPY", 100, 100.0)
        prices = {"SPY": 100.0}
        rm.update_current_prices(prices)
        p.mark_to_market(prices)  # equity=8000, exposure=10000, leverage=1.25

        order = engine.Order("AAPL", engine.OrderSide.BUY, engine.OrderType.MARKET, 1)
        order.set_price(10.0)

        self.assertFalse(rm.check_order_risk(order, p))
        self.assertEqual(rm.get_last_rejection_reason(), "leverage_limit")

    def test_drawdown_limit_blocks(self):
        limits = _loose_limits()
        limits.max_drawdown = 0.05
        rm = engine.RiskManager(limits)
        p = engine.Portfolio()
        p.set_cash(10000.0)
        p.seed_equity_history(10000.0, 20000.0)
        rm.update_current_prices({})
        p.mark_to_market({})  # 50% drawdown vs. the seeded high-water-mark

        order = engine.Order("AAPL", engine.OrderSide.BUY, engine.OrderType.MARKET, 1)
        order.set_price(1.0)

        self.assertFalse(rm.check_order_risk(order, p))
        self.assertEqual(rm.get_last_rejection_reason(), "drawdown_limit")

    def test_daily_loss_limit_blocks(self):
        limits = _loose_limits()
        limits.daily_loss_limit = 100.0
        limits.max_drawdown = 0.99
        rm = engine.RiskManager(limits)
        p = engine.Portfolio()
        p.set_cash(5000.0)
        p.seed_equity_history(6000.0, 6000.0)
        rm.update_current_prices({})
        p.mark_to_market({})  # daily_pnl = 5000 - 6000 = -1000

        order = engine.Order("AAPL", engine.OrderSide.BUY, engine.OrderType.MARKET, 1)
        order.set_price(1.0)

        self.assertFalse(rm.check_order_risk(order, p))
        self.assertEqual(rm.get_last_rejection_reason(), "daily_loss_limit")

    def test_concentration_limit_blocks(self):
        limits = _loose_limits()
        limits.position_concentration = 0.20
        rm = engine.RiskManager(limits)
        p = engine.Portfolio()
        p.set_cash(10000.0)
        p.update_position("AAPL", 50, 100.0)
        prices = {"AAPL": 100.0}
        rm.update_current_prices(prices)
        p.mark_to_market(prices)  # equity = 15000

        order = engine.Order("AAPL", engine.OrderSide.BUY, engine.OrderType.MARKET, 20)
        order.set_price(100.0)  # (50+20)*100 / 15000 = 46.7%

        self.assertFalse(rm.check_order_risk(order, p))
        self.assertEqual(rm.get_last_rejection_reason(), "concentration_limit")


@unittest.skipUnless(engine.AVAILABLE, skip_reason)
class TestCheckRebalanceRisk(unittest.TestCase):
    def test_never_submits_orders_just_annotates(self):
        from data_service.execution import check_rebalance_risk

        weights = pd.Series({"SPY": 0.2, "QQQ": 0.1})
        trades = check_rebalance_risk(
            weights, equity=10_000.0, positions={}, prices={"SPY": 500.0, "QQQ": 400.0},
            ledger_path="/tmp/test_native_bridge_nonexistent_ledger.csv",
        )
        self.assertIn("risk_ok", trades.columns)
        self.assertIn("risk_reason", trades.columns)
        self.assertTrue((trades["risk_ok"] == True).all())  # noqa: E712 -- within default limits

    def test_oversized_trade_flagged_not_blocked(self):
        """Advisory only: a flagged trade still appears in the output for
        review, it is never silently dropped or auto-corrected."""
        from data_service.execution import check_rebalance_risk

        weights = pd.Series({"SPY": 0.9})  # over the 35% default max_position_size
        trades = check_rebalance_risk(
            weights, equity=10_000.0, positions={}, prices={"SPY": 500.0},
            ledger_path="/tmp/test_native_bridge_nonexistent_ledger.csv",
        )
        self.assertFalse(trades.loc["SPY", "risk_ok"])
        self.assertEqual(trades.loc["SPY", "risk_reason"], "position_size_limit")
        # Still present with its real trade size -- advisory, not filtered out.
        self.assertGreater(trades.loc["SPY", "trade_shares"], 0)


if __name__ == "__main__":
    unittest.main()
