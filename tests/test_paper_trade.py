import os
import tempfile
import unittest

import numpy as np
import pandas as pd

from data_service.strategies.paper_trade import (
    rebalance_report, record_targets, mark_ledger, save_snapshot, load_snapshot,
)


class TestRebalanceReport(unittest.TestCase):
    def test_buy_sell_hold_and_sizing(self):
        targets = pd.Series({"SPY": 0.5, "GLD": 0.25, "TLT": 0.0})
        prices = {"SPY": 100.0, "GLD": 50.0, "TLT": 20.0}
        positions = {"SPY": 10.0, "TLT": 5.0}      # SPY $1000 held, TLT $100 held
        rep = rebalance_report(targets, equity=10_000.0, positions=positions, prices=prices)
        # SPY target $5000, holds $1000 -> BUY $4000 -> 40 shares
        self.assertEqual(rep.loc["SPY", "action"], "BUY")
        self.assertAlmostEqual(rep.loc["SPY", "trade_shares"], 40.0)
        # GLD target $2500, holds 0 -> BUY 50 shares
        self.assertAlmostEqual(rep.loc["GLD", "trade_shares"], 50.0)
        # TLT target 0, holds $100 -> SELL
        self.assertEqual(rep.loc["TLT", "action"], "SELL")
        self.assertAlmostEqual(rep.loc["TLT", "trade_shares"], -5.0)

    def test_min_trade_threshold_holds(self):
        targets = pd.Series({"SPY": 0.10})
        prices = {"SPY": 100.0}
        positions = {"SPY": 10.0}                  # exactly on target ($1000 of $10k)
        rep = rebalance_report(targets, 10_000.0, positions, prices, min_trade=5.0)
        self.assertEqual(rep.loc["SPY", "action"], "HOLD")

    def test_short_target_is_negative(self):
        rep = rebalance_report(pd.Series({"USO": -0.2}), 10_000.0, {}, {"USO": 50.0})
        self.assertEqual(rep.loc["USO", "action"], "SELL")
        self.assertAlmostEqual(rep.loc["USO", "target_$"], -2000.0)


class TestLedger(unittest.TestCase):
    def test_record_and_mark(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = os.path.join(d, "ledger.csv")
            # Day 1: full long SPY at 100; Day 2: SPY rose to 110.
            record_targets(pd.Series({"SPY": 1.0}), {"SPY": 100.0}, 1000.0, ledger, as_of="2026-01-02")
            record_targets(pd.Series({"SPY": 1.0}), {"SPY": 110.0}, 1000.0, ledger, as_of="2026-01-03")
            marks = mark_ledger(ledger)
            self.assertEqual(marks["n_days"], 2)
            # Held 100% SPY through a +10% move -> ~+10% cum paper return.
            self.assertAlmostEqual(marks["cum_return"], 0.10, places=6)

    def test_record_is_idempotent_per_date(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = os.path.join(d, "ledger.csv")
            record_targets(pd.Series({"SPY": 1.0}), {"SPY": 100.0}, 1000.0, ledger, as_of="2026-01-02")
            record_targets(pd.Series({"SPY": 0.5}), {"SPY": 100.0}, 1000.0, ledger, as_of="2026-01-02")
            df = pd.read_csv(ledger)
            self.assertEqual(len(df[df["date"] == "2026-01-02"]), 1)
            self.assertAlmostEqual(df.iloc[0]["weight"], 0.5)  # overwritten

    def test_mark_needs_two_days(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = os.path.join(d, "ledger.csv")
            record_targets(pd.Series({"SPY": 1.0}), {"SPY": 100.0}, 1000.0, ledger, as_of="2026-01-02")
            self.assertEqual(mark_ledger(ledger)["n_days"], 1)


class TestSnapshot(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "snap.json")
            save_snapshot(path, 50_000.0, {"SPY": 1.0, "GLD": 2.0}, cash=100.0)
            snap = load_snapshot(path)
            self.assertEqual(snap["equity"], 50_000.0)
            self.assertEqual(snap["positions"]["GLD"], 2.0)
            self.assertEqual(snap["cash"], 100.0)


if __name__ == "__main__":
    unittest.main()
