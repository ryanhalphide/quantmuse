"""Financial Modeling Prep (FMP) fetcher for differentiated data.

Pulls data that is orthogonal to price -- starting with analyst rating
consensus history -- so it can be tested for predictive value *beyond* the
technical signals. Structured to extend to insider trades / congressional
trades / news once the account has a paid FMP plan (those endpoints are
gated on FMP's free tier).

Get a key: https://site.financialmodelingprep.com/developer/docs
Free-tier caveat: analyst grade history is limited to a short recent window
(~10 monthly snapshots), which is enough to *wire up* the pipeline but NOT
enough to rigorously validate predictive value. Deeper history needs a paid key.

API docs: https://site.financialmodelingprep.com/developer/docs/stable
"""

import logging
import os
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from ..utils.exceptions import DataFetchError

FMP_STABLE_BASE = "https://financialmodelingprep.com/stable"


class FMPFetcher:
    """Fetches differentiated (non-price) data from Financial Modeling Prep."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = FMP_STABLE_BASE,
        timeout: int = 15,
    ):
        """
        :param api_key: FMP API key (falls back to FMP_API_KEY env var)
        :param base_url: FMP API base
        :param timeout: Per-request timeout in seconds
        """
        self.logger = logging.getLogger(__name__)
        self.api_key = api_key or os.environ.get("FMP_API_KEY")
        if not self.api_key:
            raise ValueError(
                "FMP API key required (pass api_key or set FMP_API_KEY). "
                "Get one: https://site.financialmodelingprep.com/developer/docs"
            )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        params = {**(params or {}), "apikey": self.api_key}
        try:
            resp = self.session.get(
                f"{self.base_url}/{path}", params=params, timeout=self.timeout
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.RequestException as e:
            raise DataFetchError(f"FMP request failed ({path}): {str(e)}")
        if isinstance(data, dict) and ("Error Message" in data or "error" in data):
            raise DataFetchError(f"FMP error ({path}): {data}")
        return data

    def get_analyst_grades_history(
        self, symbol: str, limit: int = 10
    ) -> pd.DataFrame:
        """Monthly analyst rating-count snapshots for a symbol.

        Returns a DataFrame indexed by date (ascending) with columns:
        strong_buy, buy, hold, sell, strong_sell.
        """
        rows = self._get(
            "grades-historical", {"symbol": symbol, "limit": limit}
        )
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        rename = {
            "analystRatingsStrongBuy": "strong_buy",
            "analystRatingsBuy": "buy",
            "analystRatingsHold": "hold",
            "analystRatingsSell": "sell",
            "analystRatingsStrongSell": "strong_sell",
        }
        df = df.rename(columns=rename)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        keep = ["strong_buy", "buy", "hold", "sell", "strong_sell"]
        return df[[c for c in keep if c in df.columns]].astype(float)

    def get_price_target_consensus(self, symbol: str) -> Dict[str, Any]:
        """Current consensus price target (high/low/consensus/median)."""
        rows = self._get("price-target-consensus", {"symbol": symbol})
        return rows[0] if isinstance(rows, list) and rows else {}
