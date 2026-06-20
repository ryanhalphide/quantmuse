import unittest
from unittest.mock import Mock, patch

import pandas as pd

from data_service.fetchers.eodhd_fetcher import EODHDFetcher


class TestEODHDFetcher(unittest.TestCase):
    def test_requires_key(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError):
                EODHDFetcher(api_key=None)

    def test_symbol_normalization(self):
        self.assertEqual(EODHDFetcher._norm_symbol("AAPL"), "AAPL.US")
        self.assertEqual(EODHDFetcher._norm_symbol("BTC-USD.CC"), "BTC-USD.CC")

    def test_parses_sentiment_dict_keyed_by_symbol(self):
        f = EODHDFetcher(api_key="K")
        f._get = Mock(return_value={"AAPL.US": [
            {"date": "2024-01-02", "count": 5, "normalized": 0.3},
            {"date": "2024-01-01", "count": 3, "normalized": -0.1},
        ]})
        df = f.get_sentiment("AAPL", "2024-01-01", "2024-02-01")
        self.assertEqual(list(df.columns), ["normalized", "count"])
        self.assertEqual(len(df), 2)
        self.assertTrue(df.index.is_monotonic_increasing)
        self.assertAlmostEqual(df["normalized"].iloc[0], -0.1)

    def test_monthly_signal_is_month_start_mean(self):
        f = EODHDFetcher(api_key="K")
        f._get = Mock(return_value={"AAPL.US": [
            {"date": "2024-01-05", "count": 1, "normalized": 0.2},
            {"date": "2024-01-20", "count": 1, "normalized": 0.4},
            {"date": "2024-02-10", "count": 1, "normalized": -0.6},
        ]})
        sig = f.monthly_sentiment_signal("AAPL", "2024-01-01", "2024-03-01")
        self.assertAlmostEqual(sig.loc[pd.Timestamp("2024-01-01")], 0.3)  # mean(0.2,0.4)
        self.assertAlmostEqual(sig.loc[pd.Timestamp("2024-02-01")], -0.6)

    def test_empty_sentiment(self):
        f = EODHDFetcher(api_key="K")
        f._get = Mock(return_value={})
        self.assertTrue(f.get_sentiment("AAPL", "2024-01-01", "2024-02-01").empty)
        self.assertTrue(f.monthly_sentiment_signal("AAPL", "2024-01-01", "2024-02-01").empty)


if __name__ == "__main__":
    unittest.main()
