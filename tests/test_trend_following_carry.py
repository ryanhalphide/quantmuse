import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from data_service.strategies.trend_following import TSMOMConfig, tsmom_backtest, build_weights
from data_service.strategies.carry import bond_carry, equity_carry, crypto_carry, build_carry_panel


def _trending_df(n=600, drift=0.0008, noise=0.008, seed=0, start="2018-01-01"):
    rng = np.random.RandomState(seed)
    rets = drift + noise * rng.randn(n)
    close = 100.0 * np.cumprod(1.0 + rets)
    return pd.DataFrame({"close": close}, index=pd.date_range(start, periods=n, freq="B"))


def _basket(n=600):
    return {f"S{i}": _trending_df(seed=i, n=n) for i in range(5)}


class TestCarryForecasts(unittest.TestCase):
    def test_bond_carry_sign(self):
        idx = pd.date_range("2015-01-01", periods=400, freq="B")
        steep = pd.DataFrame({"y10": np.full(400, 4.0), "m3": np.full(400, 1.0)}, index=idx)
        inverted = pd.DataFrame({"y10": np.full(400, 1.0), "m3": np.full(400, 4.0)}, index=idx)
        self.assertGreater(bond_carry(steep, idx, 2.0).dropna().iloc[-1], 0)
        self.assertLess(bond_carry(inverted, idx, 2.0).dropna().iloc[-1], 0)

    def test_crypto_carry_sign(self):
        idx = pd.date_range("2020-01-01", periods=400, freq="D")
        pos_funding = pd.Series(np.full(400, 0.10), index=idx)   # longs pay -> negative carry
        neg_funding = pd.Series(np.full(400, -0.10), index=idx)  # longs earn -> positive carry
        self.assertLess(crypto_carry(pos_funding, idx, 2.0).dropna().iloc[-1], 0)
        self.assertGreater(crypto_carry(neg_funding, idx, 2.0).dropna().iloc[-1], 0)

    def test_equity_carry_sign(self):
        idx = pd.date_range("2015-01-01", periods=400, freq="B")
        dy = pd.Series(np.full(400, 0.05), index=idx)            # 5% yield
        cash = pd.Series(np.full(400, 1.0), index=idx)           # 1% cash
        self.assertGreater(equity_carry(dy, cash, idx, 2.0).dropna().iloc[-1], 0)


class TestCarryIntegration(unittest.TestCase):
    def _carry_panel(self, data):
        idx = sorted(set().union(*[df.index for df in data.values()]))
        idx = pd.DatetimeIndex(idx)
        # Constant positive carry on two assets only.
        C = pd.DataFrame(index=idx)
        C["S0"] = 1.0
        C["S1"] = -1.0
        return C

    def test_carry_weight_zero_is_noop(self):
        data = _basket()
        C = self._carry_panel(data)
        base = build_weights(data, TSMOMConfig(carry_weight=0.0))[0]
        with_panel = build_weights(data, TSMOMConfig(carry_weight=0.0), carry_panel=C)[0]
        pd.testing.assert_frame_equal(base, with_panel)

    def test_carry_weight_changes_weights(self):
        data = _basket()
        C = self._carry_panel(data)
        base = build_weights(data, TSMOMConfig(carry_weight=0.0), carry_panel=C)[0]
        blended = build_weights(data, TSMOMConfig(carry_weight=0.5), carry_panel=C)[0]
        self.assertFalse(np.allclose(base.values, blended.values))

    def test_carry_no_lookahead(self):
        # Carry weights for the first k bars unchanged when later data is appended.
        data = _basket(n=500)
        C = self._carry_panel(data)
        cfg = TSMOMConfig(carry_weight=0.5)
        full = build_weights(data, cfg, carry_panel=C)[0]
        k = 300
        trunc = {s: df.iloc[:k] for s, df in data.items()}
        part = build_weights(trunc, cfg, carry_panel=C.iloc[:k])[0]
        a = full.iloc[:k].reset_index(drop=True)
        b = part.reset_index(drop=True)
        # Allow tiny float drift; assert max abs difference negligible.
        self.assertLess(float((a - b).abs().to_numpy().max()), 1e-9)

    def test_backtest_runs_with_carry(self):
        data = _basket()
        C = self._carry_panel(data)
        res = tsmom_backtest(data, TSMOMConfig(carry_weight=0.3), carry_panel=C)
        self.assertIn("sharpe", res["strategy"])
        self.assertEqual(len(res["equity_curve"]), len(next(iter(data.values()))))


class TestCarryData(unittest.TestCase):
    def test_okx_funding_pagination(self):
        from data_service.strategies import carry_data
        from datetime import datetime

        class Resp:
            def __init__(self, rows):
                self._rows = rows
            def json(self):
                return {"code": "0", "data": self._rows}

        # Two pages then empty; timestamps walk backwards.
        def mk(rows, base_ms):
            return [{"fundingTime": str(base_ms - i * 28800000), "fundingRate": "0.0001"}
                    for i in range(rows)]
        pages = [Resp(mk(100, 1_700_000_000_000)),
                 Resp(mk(100, 1_700_000_000_000 - 100 * 28800000)),
                 Resp([])]
        with patch.object(carry_data.requests, "get", side_effect=pages):
            df = carry_data._okx_funding("BTC-USD-SWAP", datetime(2020, 1, 1), datetime(2024, 1, 1))
        self.assertEqual(len(df), 200)
        self.assertFalse(df.index.duplicated().any())


if __name__ == "__main__":
    unittest.main()
