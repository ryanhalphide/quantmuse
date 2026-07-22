import unittest
from unittest.mock import Mock, patch

import pandas as pd

from data_service.fetchers.kalshi_fetcher import KalshiFetcher
from data_service.strategies.kalshi_arbitrage import (
    ArbConfig,
    KalshiArbitrageTrader,
)


class TestKalshiFetcher(unittest.TestCase):
    """Tests for KalshiFetcher market-data parsing."""

    def setUp(self):
        self.fetcher = KalshiFetcher()

    def test_normalize_market_converts_cents_to_dollars(self):
        raw = {
            "ticker": "KXBTC-T1",
            "event_ticker": "KXBTC",
            "title": "BTC above X",
            "status": "open",
            "close_time": "2026-06-08T12:15:00Z",
            "yes_bid": 40,
            "yes_ask": 45,
            "no_bid": 50,
            "no_ask": 52,
            "last_price": 44,
            "volume": 1000,
        }
        row = KalshiFetcher._normalize_market(raw, minutes_to_close=10.0)
        self.assertEqual(row["yes_ask"], 0.45)
        self.assertEqual(row["no_ask"], 0.52)
        self.assertEqual(row["yes_ask_cents"], 45)
        self.assertEqual(row["minutes_to_close"], 10.0)

    @patch.object(KalshiFetcher, "get_markets")
    def test_get_15min_markets_filters_by_close_time(self, mock_get_markets):
        from datetime import datetime, timedelta, timezone

        soon = (datetime.now(timezone.utc) + timedelta(minutes=8)).isoformat()
        later = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()
        mock_get_markets.return_value = [
            {"ticker": "A", "close_time": soon, "yes_ask": 45, "no_ask": 52},
            {"ticker": "B", "close_time": later, "yes_ask": 30, "no_ask": 30},
        ]
        df = self.fetcher.get_15min_markets()
        self.assertEqual(list(df["ticker"]), ["A"])


class TestKalshiArbitrage(unittest.TestCase):
    """Tests for arbitrage detection and dry-run execution."""

    def setUp(self):
        self.fetcher = KalshiFetcher()
        self.trader = KalshiArbitrageTrader(
            self.fetcher,
            ArbConfig(min_edge=0.01, max_contracts=10, max_total_spend=100.0),
        )

    def test_detects_locked_arbitrage(self):
        # yes_ask + no_ask = 0.95 -> 5c gross edge before fees.
        markets = pd.DataFrame(
            [
                {
                    "ticker": "ARB1",
                    "title": "t",
                    "yes_ask": 0.45,
                    "no_ask": 0.50,
                    "minutes_to_close": 5,
                }
            ]
        )
        opps = self.trader.find_opportunities(markets)
        self.assertEqual(len(opps), 1)
        self.assertEqual(opps[0].ticker, "ARB1")
        self.assertGreater(opps[0].net_edge_per_pair, 0)
        self.assertGreater(opps[0].total_profit, 0)

    def test_ignores_non_arbitrage(self):
        # Combined cost >= 1.00 -> no edge.
        markets = pd.DataFrame(
            [{"ticker": "NOPE", "title": "t", "yes_ask": 0.55, "no_ask": 0.50}]
        )
        self.assertEqual(self.trader.find_opportunities(markets), [])

    def test_min_edge_threshold_excludes_thin_edge(self):
        # 1c gross edge gets eaten by fees -> below default min_edge.
        markets = pd.DataFrame(
            [{"ticker": "THIN", "title": "t", "yes_ask": 0.49, "no_ask": 0.50}]
        )
        self.assertEqual(self.trader.find_opportunities(markets), [])

    def test_dry_run_does_not_place_orders(self):
        self.fetcher._request = Mock()
        markets = pd.DataFrame(
            [{"ticker": "ARB1", "title": "t", "yes_ask": 0.45, "no_ask": 0.50}]
        )
        opp = self.trader.find_opportunities(markets)[0]
        result = self.trader.execute(opp)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["status"], "simulated")
        self.fetcher._request.assert_not_called()

    def test_live_mode_places_two_orders(self):
        self.fetcher._request = Mock(return_value={"order": {"status": "executed"}})
        trader = KalshiArbitrageTrader(
            self.fetcher, ArbConfig(dry_run=False, min_edge=0.01)
        )
        markets = pd.DataFrame(
            [{"ticker": "ARB1", "title": "t", "yes_ask": 0.45, "no_ask": 0.50}]
        )
        opp = trader.find_opportunities(markets)[0]
        result = trader.execute(opp)
        self.assertFalse(result["dry_run"])
        self.assertEqual(self.fetcher._request.call_count, 2)

    def test_spend_budget_caps_contracts(self):
        trader = KalshiArbitrageTrader(
            self.fetcher,
            ArbConfig(max_contracts=1000, max_total_spend=10.0, min_edge=0.01),
        )
        markets = pd.DataFrame(
            [{"ticker": "ARB1", "title": "t", "yes_ask": 0.45, "no_ask": 0.50}]
        )
        opp = trader.find_opportunities(markets)[0]
        # At ~0.95/pair, $10 budget allows at most 10 pairs.
        self.assertLessEqual(opp.total_cost, 10.0)


class TestNormalizeMarketSchemas(unittest.TestCase):
    """Kalshi has shipped two market-quote schemas; both must parse.

    Regression test: the API migrated from integer-cent fields
    (yes_ask: 34) to decimal-dollar strings (yes_ask_dollars: "0.3400"),
    which the old parser silently turned into all-None quotes -- leaving
    the arbitrage scanner blind while appearing to work.
    """

    def test_new_dollars_schema_parses(self):
        from data_service.fetchers.kalshi_fetcher import KalshiFetcher

        row = KalshiFetcher._normalize_market(
            {
                "ticker": "KXBTC-TEST",
                "yes_bid_dollars": "0.3300",
                "yes_ask_dollars": "0.3400",
                "no_bid_dollars": "0.6500",
                "no_ask_dollars": "0.6600",
                "last_price_dollars": "0.3350",
                "volume_fp": "128.00",
                "open_interest_fp": "12.00",
                "liquidity_dollars": "455.0000",
            },
            minutes_to_close=7.5,
        )
        self.assertEqual(row["yes_ask"], 0.34)
        self.assertEqual(row["no_ask"], 0.66)
        self.assertEqual(row["yes_bid"], 0.33)
        self.assertEqual(row["last_price"], 0.335)
        self.assertEqual(row["volume"], 128.0)
        self.assertEqual(row["liquidity"], 455.0)
        # Cent values derived for the order layer.
        self.assertEqual(row["yes_ask_cents"], 34)
        self.assertEqual(row["no_ask_cents"], 66)

    def test_legacy_cents_schema_still_parses(self):
        from data_service.fetchers.kalshi_fetcher import KalshiFetcher

        row = KalshiFetcher._normalize_market(
            {
                "ticker": "KXBTC-TEST",
                "yes_bid": 33,
                "yes_ask": 34,
                "no_bid": 65,
                "no_ask": 66,
                "last_price": 33,
                "volume": 128,
            },
            minutes_to_close=7.5,
        )
        self.assertEqual(row["yes_ask"], 0.34)
        self.assertEqual(row["no_ask"], 0.66)
        self.assertEqual(row["yes_ask_cents"], 34)

    def test_unquoted_market_yields_none_not_crash(self):
        from data_service.fetchers.kalshi_fetcher import KalshiFetcher

        row = KalshiFetcher._normalize_market(
            {"ticker": "KXMVE-COMBO"}, minutes_to_close=3.0
        )
        self.assertIsNone(row["yes_ask"])
        self.assertIsNone(row["no_ask"])
        self.assertIsNone(row["yes_ask_cents"])


if __name__ == "__main__":
    unittest.main()
