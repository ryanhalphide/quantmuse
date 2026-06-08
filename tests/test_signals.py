import unittest
from unittest.mock import Mock, patch

from data_service.signals.base import SignalProvider, SignalResult, score_to_label
from data_service.signals.alpha_vantage_signals import AlphaVantageSignalProvider


class TestScoreToLabel(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(score_to_label(0.5), "BULLISH")
        self.assertEqual(score_to_label(0.2), "SOMEWHAT_BULLISH")
        self.assertEqual(score_to_label(0.0), "NEUTRAL")
        self.assertEqual(score_to_label(-0.2), "SOMEWHAT_BEARISH")
        self.assertEqual(score_to_label(-0.5), "BEARISH")


class TestCompositeBlending(unittest.TestCase):
    def test_composite_skips_unavailable_components(self):
        class Partial(SignalProvider):
            name = "partial"

            def rsi_score(self, symbol):
                return 1.0

            def macd_score(self, symbol):
                return None  # unavailable

            def sentiment_score(self, symbol):
                raise RuntimeError("boom")  # errors -> None

        result = Partial().composite_signal("X")
        # Only RSI available -> composite equals RSI score.
        self.assertEqual(result.score, 1.0)
        self.assertEqual(result.label, "BULLISH")
        self.assertIsNone(result.components["macd"])
        self.assertIsNone(result.components["sentiment"])

    def test_weighted_average(self):
        class Two(SignalProvider):
            name = "two"
            weights = {"rsi": 0.5, "macd": 0.5, "sentiment": 0.0}

            def rsi_score(self, symbol):
                return 1.0

            def macd_score(self, symbol):
                return -1.0

            def sentiment_score(self, symbol):
                return None

        result = Two().composite_signal("X")
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.label, "NEUTRAL")


class TestAlphaVantageSignals(unittest.TestCase):
    def setUp(self):
        self.provider = AlphaVantageSignalProvider(api_key="TESTKEY")

    def test_requires_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError):
                AlphaVantageSignalProvider(api_key=None)

    def test_rsi_score_oversold_is_bullish(self):
        self.provider._get = Mock(
            return_value={
                "Technical Analysis: RSI": {"2026-06-08": {"RSI": "20.0"}}
            }
        )
        # RSI 20 -> (50-20)/20 = 1.5 -> clamped to 1.0
        self.assertEqual(self.provider.rsi_score("AAPL"), 1.0)

    def test_rsi_score_overbought_is_bearish(self):
        self.provider._get = Mock(
            return_value={
                "Technical Analysis: RSI": {"2026-06-08": {"RSI": "80.0"}}
            }
        )
        self.assertEqual(self.provider.rsi_score("AAPL"), -1.0)

    def test_macd_score_sign(self):
        self.provider._get = Mock(
            return_value={
                "Technical Analysis: MACD": {
                    "2026-06-08": {"MACD": "2.0", "MACD_Signal": "1.0", "MACD_Hist": "1.0"}
                }
            }
        )
        # hist=1, denom=2 -> 0.5 (bullish)
        self.assertEqual(self.provider.macd_score("AAPL"), 0.5)

    def test_sentiment_prefers_ticker_specific_score(self):
        self.provider._get = Mock(
            return_value={
                "feed": [
                    {
                        "overall_sentiment_score": 0.1,
                        "ticker_sentiment": [
                            {"ticker": "AAPL", "ticker_sentiment_score": "0.6"},
                            {"ticker": "MSFT", "ticker_sentiment_score": "-0.9"},
                        ],
                    }
                ]
            }
        )
        self.assertAlmostEqual(self.provider.sentiment_score("AAPL"), 0.6)

    def test_composite_combines_real_endpoints(self):
        def fake_get(params):
            fn = params["function"]
            if fn == "RSI":
                return {"Technical Analysis: RSI": {"d": {"RSI": "30.0"}}}
            if fn == "MACD":
                return {
                    "Technical Analysis: MACD": {
                        "d": {"MACD": "1.0", "MACD_Signal": "0.5", "MACD_Hist": "0.5"}
                    }
                }
            if fn == "NEWS_SENTIMENT":
                return {
                    "feed": [
                        {
                            "ticker_sentiment": [
                                {"ticker": "AAPL", "ticker_sentiment_score": "0.4"}
                            ]
                        }
                    ]
                }
            return {}

        self.provider._get = Mock(side_effect=fake_get)
        result = self.provider.composite_signal("AAPL")
        self.assertIsInstance(result, SignalResult)
        self.assertEqual(result.provider, "alpha_vantage")
        self.assertGreater(result.score, 0)  # all three components bullish
        self.assertEqual(result.components["rsi"], 1.0)

    def test_rate_limit_note_raises(self):
        from data_service.utils.exceptions import DataFetchError

        self.provider.session.get = Mock(
            return_value=Mock(
                status_code=200,
                raise_for_status=Mock(),
                json=Mock(return_value={"Note": "rate limit hit"}),
            )
        )
        with self.assertRaises(DataFetchError):
            self.provider._get({"function": "RSI"})


if __name__ == "__main__":
    unittest.main()
