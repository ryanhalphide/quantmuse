"""Data sources for the carry sleeve (free, reachable from this environment).

Carry (Koijen et al. 2018) is the return an asset earns if its price stays
unchanged. It is a distinct, ~uncorrelated premium that complements trend. Free
proxies by asset class:

- Rates curve: Yahoo ^TNX (10y yield) and ^IRX (13-week T-bill) -- equivalent to
  FRED's T10Y3M, back to 2007, no API key, fully reproducible.
- Equity carry: trailing-12m dividend yield minus the cash (3m) rate (yfinance
  dividends). A proxy for true index-futures basis carry.
- Crypto carry: minus the perpetual funding rate (long a perp earns -funding).
  OKX funding-rate history is reachable here; Deribit is the fallback. (Binance
  futures are geo-blocked in this environment.)
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import requests

from .trend_following_data import _fetch_yahoo, _strip_tz

logger = logging.getLogger(__name__)

_OKX_URL = "https://www.okx.com/api/v5/public/funding-rate-history"
_DERIBIT_URL = "https://www.deribit.com/api/v2/public/get_funding_rate_history"
_MAX_PAGES = 80
# Display symbol -> (OKX swap, Deribit perpetual)
CRYPTO_PERP = {"BTC": ("BTC-USD-SWAP", "BTC-PERPETUAL"),
               "ETH": ("ETH-USD-SWAP", "ETH-PERPETUAL")}


def load_rates(start: datetime, end: datetime) -> pd.DataFrame:
    """10y and 3m Treasury yields (percent) from Yahoo, tz-naive daily index."""
    y10 = _fetch_yahoo("^TNX", start, end)
    m3 = _fetch_yahoo("^IRX", start, end)
    df = pd.DataFrame({
        "y10": y10["close"] if not y10.empty else pd.Series(dtype=float),
        "m3": m3["close"] if not m3.empty else pd.Series(dtype=float),
    }).sort_index()
    return df


def _okx_funding(swap: str, start: datetime, end: datetime) -> pd.DataFrame:
    """Page OKX 8h funding history backwards via the `after` cursor."""
    out, cursor = [], None
    start_ms = int(start.timestamp() * 1000)
    for _ in range(_MAX_PAGES):
        params = {"instId": swap, "limit": "100"}
        if cursor is not None:
            params["after"] = str(cursor)
        try:
            r = requests.get(_OKX_URL, params=params, timeout=15)
            rows = r.json().get("data", [])
        except Exception as e:
            logger.warning("OKX funding fetch failed for %s: %s", swap, e)
            break
        if not rows:
            break
        out.extend(rows)
        oldest = int(rows[-1]["fundingTime"])
        cursor = oldest
        if oldest <= start_ms:
            break
        time.sleep(0.1)
    if not out:
        return pd.DataFrame()
    df = pd.DataFrame(out)
    df["t"] = pd.to_datetime(df["fundingTime"].astype("int64"), unit="ms")
    df["rate"] = df["fundingRate"].astype(float)
    return df[["t", "rate"]].set_index("t").sort_index()


def _deribit_funding(perp: str, start: datetime, end: datetime) -> pd.DataFrame:
    """Deribit funding history (interest_8h), single ranged call (chunked)."""
    out, cur = [], start
    for _ in range(_MAX_PAGES):
        s_ms = int(cur.timestamp() * 1000)
        e_ms = int(min(cur + timedelta(days=300), end).timestamp() * 1000)
        try:
            r = requests.get(_DERIBIT_URL, params={
                "instrument_name": perp, "start_timestamp": s_ms, "end_timestamp": e_ms,
            }, timeout=15)
            rows = r.json().get("result", [])
        except Exception as e:
            logger.warning("Deribit funding fetch failed for %s: %s", perp, e)
            break
        for row in rows:
            out.append((row["timestamp"], row.get("interest_8h", 0.0)))
        if e_ms >= int(end.timestamp() * 1000):
            break
        cur = cur + timedelta(days=300)
    if not out:
        return pd.DataFrame()
    df = pd.DataFrame(out, columns=["ts", "rate"])
    df["t"] = pd.to_datetime(df["ts"].astype("int64"), unit="ms")
    return df[["t", "rate"]].set_index("t").sort_index()


def load_funding(display: str, start: datetime, end: datetime) -> pd.Series:
    """Daily annualized funding rate for a crypto perp (OKX, Deribit fallback).

    Funding is paid ~3x/day; daily funding = sum of the day's payments, annualized
    by x365. Returned as a tz-naive daily Series (NaN before the perp existed).
    """
    swap, perp = CRYPTO_PERP.get(display, (None, None))
    raw = pd.DataFrame()
    if swap:
        raw = _okx_funding(swap, start, end)
    if raw.empty and perp:
        raw = _deribit_funding(perp, start, end)
    if raw.empty:
        return pd.Series(dtype=float)
    daily = raw["rate"].groupby(raw.index.normalize()).sum() * 365.0
    daily.index = _strip_tz(daily.index)
    return daily.sort_index()


def load_dividend_yield(symbol: str, close: pd.Series) -> pd.Series:
    """Trailing-12-month dividend yield (fraction) aligned to `close`'s index."""
    try:
        import yfinance as yf
        divs = yf.Ticker(symbol).dividends
    except Exception as e:
        logger.warning("Dividend fetch failed for %s: %s", symbol, e)
        return pd.Series(dtype=float)
    if divs is None or len(divs) == 0:
        return pd.Series(dtype=float)
    divs.index = _strip_tz(divs.index)
    daily = divs.reindex(close.index).fillna(0.0)
    ttm = daily.rolling("365D").sum()
    return (ttm / close).replace([float("inf"), -float("inf")], float("nan"))
