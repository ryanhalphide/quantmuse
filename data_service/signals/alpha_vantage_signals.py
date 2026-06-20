"""Alpha Vantage signal provider.

Pulls real signal components from Alpha Vantage's REST API:
  - RSI (RSI endpoint)
  - MACD (MACD endpoint)
  - News & sentiment (NEWS_SENTIMENT endpoint)

and blends them into a composite directional score via SignalProvider.

Works for US equities and crypto (use ``market`` for crypto symbols).

Free tier reality: Alpha Vantage's free key is limited to ~25 requests/day and
~5/minute, and a full composite signal uses 3 requests per symbol. For more than
a handful of symbols you will need a paid key. Get a free key at
https://www.alphavantage.co/support/#api-key

API docs: https://www.alphavantage.co/documentation/

Signals are informational, not a profit guarantee.
"""

import logging
import os
from typing import Any, Dict, Optional

import requests

from ..utils.exceptions import DataFetchError
from .base import SignalProvider, clamp

ALPHA_VANTAGE_BASE = "https://www.alphavantage.co/query"


class AlphaVantageSignalProvider(SignalProvider):
    """Composite signals from Alpha Vantage technical indicators + news."""

    name = "alpha_vantage"

    def __init__(
        self,
        api_key: Optional[str] = None,
        interval: str = "daily",
        timeout: int = 15,
    ):
        """
        :param api_key: Alpha Vantage API key (falls back to ALPHAVANTAGE_API_KEY env)
        :param interval: Indicator interval (daily, weekly, 60min, ...)
        :param timeout: Per-request timeout in seconds
        """
        self.logger = logging.getLogger(__name__)
        self.api_key = api_key or os.environ.get("ALPHAVANTAGE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Alpha Vantage API key required (pass api_key or set "
                "ALPHAVANTAGE_API_KEY). Free key: "
                "https://www.alphavantage.co/support/#api-key"
            )
        self.interval = interval
        self.timeout = timeout
        self.session = requests.Session()

    def _get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        params = {**params, "apikey": self.api_key}
        try:
            resp = self.session.get(
                ALPHA_VANTAGE_BASE, params=params, timeout=self.timeout
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.RequestException as e:
            raise DataFetchError(f"Alpha Vantage request failed: {str(e)}")

        # Alpha Vantage signals rate-limit / errors via JSON keys, not HTTP codes.
        if "Note" in data or "Information" in data:
            msg = data.get("Note") or data.get("Information")
            raise DataFetchError(f"Alpha Vantage limit/notice: {msg}")
        if "Error Message" in data:
            raise DataFetchError(f"Alpha Vantage error: {data['Error Message']}")
        return data

    # ------------------------------------------------------------------
    # Components (each returns a score in [-1, 1])
    # ------------------------------------------------------------------
    def rsi_score(self, symbol: str) -> Optional[float]:
        """RSI: oversold (<30) is bullish (+), overbought (>70) is bearish (-)."""
        data = self._get(
            {
                "function": "RSI",
                "symbol": symbol,
                "interval": self.interval,
                "time_period": 14,
                "series_type": "close",
            }
        )
        series = data.get("Technical Analysis: RSI")
        if not series:
            return None
        latest = next(iter(series.values()))
        rsi = float(latest["RSI"])
        # Map RSI 0..100 to score: 30 -> +1, 50 -> 0, 70 -> -1 (linear, clamped).
        return clamp((50.0 - rsi) / 20.0)

    def macd_score(self, symbol: str) -> Optional[float]:
        """MACD: histogram (MACD - signal) sign and magnitude give direction."""
        data = self._get(
            {
                "function": "MACD",
                "symbol": symbol,
                "interval": self.interval,
                "series_type": "close",
            }
        )
        series = data.get("Technical Analysis: MACD")
        if not series:
            return None
        latest = next(iter(series.values()))
        macd = float(latest["MACD"])
        signal = float(latest["MACD_Signal"])
        hist = macd - signal
        # Normalize histogram by the MACD magnitude so the score is scale-free.
        denom = max(abs(macd), abs(signal), 1e-6)
        return clamp(hist / denom)

    def sentiment_score(self, symbol: str) -> Optional[float]:
        """News sentiment: average Alpha Vantage overall_sentiment_score.

        AV's score is already roughly in [-1, 1] (bearish..bullish).
        """
        data = self._get(
            {"function": "NEWS_SENTIMENT", "tickers": symbol, "limit": 50}
        )
        feed = data.get("feed")
        if not feed:
            return None
        scores = []
        for article in feed:
            # Prefer the ticker-specific score when present.
            ticker_score = None
            for ts in article.get("ticker_sentiment", []):
                if ts.get("ticker") == symbol:
                    ticker_score = float(ts.get("ticker_sentiment_score", 0))
                    break
            if ticker_score is None and "overall_sentiment_score" in article:
                ticker_score = float(article["overall_sentiment_score"])
            if ticker_score is not None:
                scores.append(ticker_score)
        if not scores:
            return None
        return clamp(sum(scores) / len(scores))
