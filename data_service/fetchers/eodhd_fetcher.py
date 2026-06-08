"""EODHD (eodhd.com) fetcher for differentiated, history-bearing data.

EODHD's free tier exposes a daily **news-sentiment** time series -- a normalized
sentiment score per symbol per day -- which is differentiated from price and has
real history, exactly what's needed to test for orthogonal predictive value.

Setup: create a free key at https://eodhd.com and set EODHD_API_KEY.
Docs: https://eodhd.com/financial-apis/stock-market-financial-news-sentiment-data-api

Symbols use EODHD's ``TICKER.EXCHANGE`` form; bare US tickers get ``.US`` appended.
"""

import logging
import os
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from ..utils.exceptions import DataFetchError

EODHD_BASE = "https://eodhd.com/api"


class EODHDFetcher:
    """Fetches sentiment (and EOD prices) from EODHD."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = EODHD_BASE,
        timeout: int = 20,
    ):
        self.logger = logging.getLogger(__name__)
        self.api_key = api_key or os.environ.get("EODHD_API_KEY")
        if not self.api_key:
            raise ValueError(
                "EODHD API key required (pass api_key or set EODHD_API_KEY). "
                "Get a free key: https://eodhd.com"
            )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    @staticmethod
    def _norm_symbol(symbol: str) -> str:
        return symbol if "." in symbol else f"{symbol}.US"

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        params = {**(params or {}), "api_token": self.api_key, "fmt": "json"}
        try:
            resp = self.session.get(
                f"{self.base_url}/{path}", params=params, timeout=self.timeout
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            raise DataFetchError(f"EODHD request failed ({path}): {str(e)}")

    def get_sentiment(
        self, symbol: str, from_date: str, to_date: str
    ) -> pd.DataFrame:
        """Daily news-sentiment for a symbol.

        :param from_date / to_date: 'YYYY-MM-DD'
        :returns: DataFrame indexed by date (ascending) with columns
                  ``normalized`` (sentiment in ~[-1, 1]) and ``count`` (articles).
        """
        sym = self._norm_symbol(symbol)
        data = self._get("sentiments", {"s": sym, "from": from_date, "to": to_date})
        # API returns {symbol: [{date, count, normalized}, ...]}.
        rows: List[Dict[str, Any]] = []
        if isinstance(data, dict):
            for key in (sym, symbol):
                if key in data:
                    rows = data[key]
                    break
        elif isinstance(data, list):
            rows = data
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        keep = [c for c in ("normalized", "count") if c in df.columns]
        return df[keep].astype(float)

    def monthly_sentiment_signal(
        self, symbol: str, from_date: str, to_date: str
    ) -> pd.Series:
        """Month-start mean of daily normalized sentiment, ready for the
        orthogonality harness (``evaluate_signal_orthogonality``)."""
        df = self.get_sentiment(symbol, from_date, to_date)
        if df.empty:
            return pd.Series(dtype=float)
        return df["normalized"].resample("MS").mean()
