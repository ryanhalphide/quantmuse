"""Kalshi market data fetcher.

Scrapes Kalshi markets (with first-class support for the short-duration
"15 minute" markets) via the public Trade API v2. Market data endpoints are
public and require no authentication; only order placement does.

API reference: https://trading-api.readme.io/reference
"""

import base64
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from ..utils.exceptions import DataFetchError

# Public production base URL for the Kalshi Trade API.
KALSHI_API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
# Demo / sandbox environment for paper testing.
KALSHI_DEMO_API_BASE = "https://demo-api.kalshi.co/trade-api/v2"


class KalshiFetcher:
    """Fetches market data from Kalshi.

    Market data calls (markets, events, orderbook) are public. An API key id +
    RSA private key can optionally be supplied to enable signed/authenticated
    requests used by the trading client.
    """

    def __init__(
        self,
        api_base: str = KALSHI_API_BASE,
        api_key_id: Optional[str] = None,
        private_key_pem: Optional[str] = None,
        timeout: int = 10,
        max_retries: int = 4,
        page_delay: float = 0.25,
    ):
        """
        :param api_base: Base URL (use KALSHI_DEMO_API_BASE for sandbox)
        :param api_key_id: Kalshi API key id (only needed for trading)
        :param private_key_pem: RSA private key PEM string (only for trading)
        :param timeout: Per-request timeout in seconds
        :param max_retries: Retries on rate limit (429) with exponential backoff
        :param page_delay: Delay between paged requests to respect rate limits
        """
        self.logger = logging.getLogger(__name__)
        self.api_base = api_base.rstrip("/")
        self.api_key_id = api_key_id
        self.timeout = timeout
        self.max_retries = max_retries
        self.page_delay = page_delay
        self._private_key = None
        self.session = requests.Session()

        if private_key_pem:
            self._load_private_key(private_key_pem)

    # ------------------------------------------------------------------
    # Authentication helpers (only needed for trading endpoints)
    # ------------------------------------------------------------------
    def _load_private_key(self, private_key_pem: str) -> None:
        try:
            from cryptography.hazmat.primitives.serialization import (
                load_pem_private_key,
            )

            self._private_key = load_pem_private_key(
                private_key_pem.encode(), password=None
            )
            self.logger.info("Kalshi private key loaded; signed requests enabled")
        except ImportError:
            self.logger.error(
                "cryptography package required for authenticated Kalshi requests. "
                "Install with: pip install cryptography"
            )
            raise
        except Exception as e:
            self.logger.error(f"Failed to load Kalshi private key: {str(e)}")
            raise

    def _signed_headers(self, method: str, path: str) -> Dict[str, str]:
        """Build the KALSHI-ACCESS-* signature headers for a request.

        Kalshi signs ``timestamp + method + path`` with RSA-PSS / SHA256.
        ``path`` must be the full request path including the ``/trade-api/v2``
        prefix and excluding the query string.
        """
        if not (self.api_key_id and self._private_key):
            raise DataFetchError(
                "API key id and private key required for authenticated requests"
            )

        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        timestamp_ms = str(int(time.time() * 1000))
        message = f"{timestamp_ms}{method.upper()}{path}".encode()
        signature = self._private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
            "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
        }

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        signed: bool = False,
    ) -> Dict[str, Any]:
        """Issue an HTTP request against the Kalshi API."""
        url = f"{self.api_base}{endpoint}"
        headers = {"Content-Type": "application/json"}
        if signed:
            # Path for signing includes the /trade-api/v2 prefix.
            path = self.api_base.split("kalshi.co", 1)[-1].split("kalshi.com", 1)[-1]
            path = path + endpoint
            headers.update(self._signed_headers(method, path))

        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.session.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=headers,
                    timeout=self.timeout,
                )
                # Back off and retry on rate limiting.
                if resp.status_code == 429 and attempt < self.max_retries:
                    wait = 2 ** attempt
                    self.logger.warning(
                        f"Rate limited by Kalshi ({endpoint}); retrying in {wait}s"
                    )
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json() if resp.content else {}
            except requests.exceptions.RequestException as e:
                last_exc = e
                # Retry transient network errors with backoff; fail fast on 4xx.
                status = getattr(e.response, "status_code", None)
                if attempt < self.max_retries and status not in (400, 401, 403, 404):
                    time.sleep(2 ** attempt)
                    continue
                break

        body = (
            getattr(last_exc.response, "text", "")
            if getattr(last_exc, "response", None) is not None
            else ""
        )
        self.logger.error(f"Kalshi request failed ({endpoint}): {str(last_exc)} {body}")
        raise DataFetchError(f"Kalshi request failed: {str(last_exc)}")

    # ------------------------------------------------------------------
    # Public market-data endpoints
    # ------------------------------------------------------------------
    def get_markets(
        self,
        series_ticker: Optional[str] = None,
        event_ticker: Optional[str] = None,
        status: str = "open",
        limit: int = 1000,
        max_pages: int = 20,
    ) -> List[Dict[str, Any]]:
        """Fetch markets, paging through the cursor automatically.

        :param series_ticker: Restrict to a series (e.g. a 15-min series)
        :param event_ticker: Restrict to a single event
        :param status: Market status filter ('open', 'closed', 'settled', ...)
        :param limit: Page size (max 1000)
        :param max_pages: Safety cap on number of pages fetched
        :return: List of market dicts
        """
        markets: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        for _ in range(max_pages):
            params: Dict[str, Any] = {"limit": min(limit, 1000), "status": status}
            if series_ticker:
                params["series_ticker"] = series_ticker
            if event_ticker:
                params["event_ticker"] = event_ticker
            if cursor:
                params["cursor"] = cursor

            data = self._request("GET", "/markets", params=params)
            page = data.get("markets", [])
            markets.extend(page)
            cursor = data.get("cursor")
            if not cursor or not page:
                break
            if self.page_delay:
                time.sleep(self.page_delay)

        self.logger.info(f"Fetched {len(markets)} Kalshi markets (status={status})")
        return markets

    def get_market(self, ticker: str) -> Dict[str, Any]:
        """Fetch a single market by ticker."""
        data = self._request("GET", f"/markets/{ticker}")
        return data.get("market", {})

    def get_orderbook(self, ticker: str, depth: int = 10) -> Dict[str, Any]:
        """Fetch the order book for a market.

        Returns price levels in cents. The ``yes`` and ``no`` arrays each
        contain ``[price_cents, quantity]`` resting bid levels.
        """
        data = self._request(
            "GET", f"/markets/{ticker}/orderbook", params={"depth": depth}
        )
        return data.get("orderbook", {})

    def get_events(
        self, series_ticker: Optional[str] = None, status: str = "open", limit: int = 200
    ) -> List[Dict[str, Any]]:
        """Fetch events, optionally restricted to a series."""
        params: Dict[str, Any] = {"limit": limit, "status": status}
        if series_ticker:
            params["series_ticker"] = series_ticker
        data = self._request("GET", "/events", params=params)
        return data.get("events", [])

    # ------------------------------------------------------------------
    # 15-minute markets
    # ------------------------------------------------------------------
    def get_15min_markets(
        self,
        series_tickers: Optional[List[str]] = None,
        max_minutes_to_close: int = 15,
    ) -> pd.DataFrame:
        """Fetch open short-duration ("15 minute") markets as a DataFrame.

        Kalshi exposes rapid-cycle markets (e.g. crypto price ranges) whose
        events resolve every ~15 minutes. We identify them by a short time to
        close. If ``series_tickers`` is provided we restrict to those series;
        otherwise we scan all open markets and keep the short-dated ones.

        :param series_tickers: Optional list of series tickers to restrict to
        :param max_minutes_to_close: Keep markets closing within this many minutes
        :return: DataFrame with one row per market, prices normalised to dollars
        """
        raw: List[Dict[str, Any]] = []
        if series_tickers:
            for st in series_tickers:
                raw.extend(self.get_markets(series_ticker=st, status="open"))
        else:
            raw = self.get_markets(status="open")

        now = datetime.now(timezone.utc)
        rows: List[Dict[str, Any]] = []
        for m in raw:
            close_ts = m.get("close_time")
            minutes_to_close = None
            if close_ts:
                try:
                    close_dt = datetime.fromisoformat(
                        close_ts.replace("Z", "+00:00")
                    )
                    minutes_to_close = (close_dt - now).total_seconds() / 60.0
                except (ValueError, AttributeError):
                    minutes_to_close = None

            if minutes_to_close is None or minutes_to_close > max_minutes_to_close:
                continue
            if minutes_to_close < 0:
                continue

            rows.append(self._normalize_market(m, minutes_to_close))

        df = pd.DataFrame(rows)
        self.logger.info(
            f"Found {len(df)} open 15-min markets closing within "
            f"{max_minutes_to_close} minutes"
        )
        return df

    @staticmethod
    def _normalize_market(m: Dict[str, Any], minutes_to_close: Optional[float]) -> Dict[str, Any]:
        """Convert a raw market dict to a normalised row (prices in dollars)."""
        def to_dollars(cents: Optional[Any]) -> Optional[float]:
            return round(cents / 100.0, 4) if cents is not None else None

        return {
            "ticker": m.get("ticker"),
            "event_ticker": m.get("event_ticker"),
            "title": m.get("title") or m.get("yes_sub_title"),
            "status": m.get("status"),
            "close_time": m.get("close_time"),
            "minutes_to_close": round(minutes_to_close, 2)
            if minutes_to_close is not None
            else None,
            # Best prices, in dollars (Kalshi quotes in cents 1..99).
            "yes_bid": to_dollars(m.get("yes_bid")),
            "yes_ask": to_dollars(m.get("yes_ask")),
            "no_bid": to_dollars(m.get("no_bid")),
            "no_ask": to_dollars(m.get("no_ask")),
            "last_price": to_dollars(m.get("last_price")),
            "volume": m.get("volume"),
            "open_interest": m.get("open_interest"),
            "liquidity": m.get("liquidity"),
            # Raw cent values retained for the order layer.
            "yes_ask_cents": m.get("yes_ask"),
            "no_ask_cents": m.get("no_ask"),
        }
