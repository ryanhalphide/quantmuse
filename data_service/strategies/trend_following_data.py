"""Multi-asset data loader for the trend-following system.

Pulls a diversified universe from free sources: ETFs/indices via Yahoo and crypto
via Binance (with Yahoo fallback). Normalizes every index to a tz-naive, normalized
DatetimeIndex (Yahoo is tz-aware, Binance tz-naive) and aligns everything onto one
common calendar so the vectorized backtest can join cleanly.
"""

import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# On-disk price cache: makes loads resilient to transient Yahoo rate limits and
# fast on reruns. Gitignored (under data/). Falls back to cache when a live fetch
# returns empty; refreshes the cache whenever a live fetch succeeds.
CACHE_DIR = os.environ.get("TREND_CACHE_DIR", os.path.join("data", "cache"))


def _cache_get(symbol: str, interval: str) -> Optional[pd.DataFrame]:
    path = os.path.join(CACHE_DIR, f"{symbol}_{interval}.pkl")
    if os.path.exists(path):
        try:
            return pd.read_pickle(path)
        except Exception:
            return None
    return None


def _cache_put(symbol: str, interval: str, df: pd.DataFrame) -> None:
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        df.to_pickle(os.path.join(CACHE_DIR, f"{symbol}_{interval}.pkl"))
    except Exception as e:
        logger.warning("cache write failed for %s: %s", symbol, e)

# Diversified, liquid, free-to-fetch universe.
ETF_UNIVERSE: List[str] = [
    "SPY", "QQQ", "EFA", "EEM", "IWM",   # equity (US large/Nasdaq/intl/EM/small)
    "TLT", "IEF",                         # bonds (long / intermediate Treasuries)
    "DBC", "USO",                         # commodities (broad / oil)
    "GLD",                                # gold
    "VNQ",                                # REITs
]
# Display symbol -> Binance pair (Yahoo fallback uses "<BASE>-USD").
CRYPTO_UNIVERSE: Dict[str, str] = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}

_MAX_BINANCE_PAGES = 30  # guard against infinite pagination loops


def _strip_tz(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """tz-aware or tz-naive -> tz-naive, normalized to midnight (mirrors analyst_signals)."""
    idx = pd.to_datetime(idx)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return idx.normalize()


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.index = _strip_tz(df.index)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def _fetch_yahoo(symbol: str, start: datetime, end: datetime, retries: int = 4) -> pd.DataFrame:
    from ..fetchers.yahoo_fetcher import YahooFetcher
    fetcher = YahooFetcher()
    for attempt in range(retries):
        try:
            df = fetcher.fetch_historical_data(symbol, start_time=start, end_time=end, interval="1d")
            if df is not None and not df.empty:
                return _normalize(df)
        except Exception as e:
            logger.warning("Yahoo fetch error for %s (attempt %d): %s", symbol, attempt + 1, e)
        if attempt < retries - 1:
            time.sleep(2 ** attempt)  # 1s, 2s, 4s backoff for transient rate limits
    return pd.DataFrame()


def _make_binance_fetcher():
    """Factory isolated for patchability (python-binance is an optional dependency)."""
    from ..fetchers.binance_fetcher import BinanceFetcher
    return BinanceFetcher()


def _fetch_binance_paginated(pair: str, start: datetime, end: datetime,
                             interval: str = "1d") -> pd.DataFrame:
    """Fetch deep Binance history despite the 1000-candle-per-call cap."""
    fetcher = _make_binance_fetcher()
    frames, cursor = [], start
    for _ in range(_MAX_BINANCE_PAGES):
        chunk = fetcher.fetch_historical_data(symbol=pair, interval=interval,
                                              start_time=cursor, end_time=end, limit=1000)
        if chunk is None or chunk.empty:
            break
        frames.append(chunk)
        last = pd.to_datetime(chunk.index[-1])
        if last >= pd.to_datetime(end) or len(chunk) < 1000:
            break
        cursor = last.to_pydatetime() + timedelta(days=1)
    if not frames:
        return pd.DataFrame()
    return _normalize(pd.concat(frames))


def _fetch_crypto(display: str, pair: str, start: datetime, end: datetime,
                  prefer_binance: bool = True) -> pd.DataFrame:
    if prefer_binance:
        try:
            df = _fetch_binance_paginated(pair, start, end)
            if not df.empty:
                return df
            logger.warning("Binance returned no data for %s; falling back to Yahoo", pair)
        except Exception as e:  # network/auth/library issues -> fall back
            logger.warning("Binance fetch failed for %s (%s); falling back to Yahoo", pair, e)
    return _fetch_yahoo(f"{display}-USD", start, end)


def load_universe(etfs: Optional[List[str]] = None,
                  crypto: Optional[Dict[str, str]] = None,
                  start: Optional[datetime] = None,
                  end: Optional[datetime] = None,
                  prefer_binance: bool = True) -> Dict[str, pd.DataFrame]:
    """Load the full universe. Symbols that fail to load are skipped (logged)."""
    etfs = ETF_UNIVERSE if etfs is None else etfs
    crypto = CRYPTO_UNIVERSE if crypto is None else crypto
    end = end or datetime.now()
    start = start or (end - timedelta(days=365 * 12))

    data: Dict[str, pd.DataFrame] = {}
    for sym in etfs:
        try:
            df = _fetch_yahoo(sym, start, end)
            if df.empty:                       # transient rate limit -> fall back to cache
                cached = _cache_get(sym, "1d")
                if cached is not None and not cached.empty:
                    logger.warning("Using cached data for ETF %s", sym)
                    df = cached
            if not df.empty:
                _cache_put(sym, "1d", df)
                data[sym] = df
            else:
                logger.warning("No data for ETF %s", sym)
        except Exception as e:
            logger.warning("Failed to load ETF %s: %s", sym, e)
    for display, pair in crypto.items():
        try:
            df = _fetch_crypto(display, pair, start, end, prefer_binance)
            if df.empty:
                cached = _cache_get(display, "1d")
                if cached is not None and not cached.empty:
                    logger.warning("Using cached data for crypto %s", display)
                    df = cached
            if not df.empty:
                _cache_put(display, "1d", df)
                data[display] = df
            else:
                logger.warning("No data for crypto %s", display)
        except Exception as e:
            logger.warning("Failed to load crypto %s: %s", display, e)
    return data


def align_calendar(price_data: Dict[str, pd.DataFrame],
                   anchor: str = "SPY", ffill_limit: int = 3) -> Dict[str, pd.DataFrame]:
    """Reindex all assets onto one shared calendar.

    Crypto trades 7 days/week while ETFs trade ~5; we anchor on a tradable ETF's
    calendar (default SPY) so weekend-only crypto bars don't inject phantom return
    days for ETFs. Crypto is forward-filled onto the anchor calendar. If the anchor
    is absent, the union of all indices is used.
    """
    if not price_data:
        return price_data
    if anchor in price_data:
        calendar = price_data[anchor].index
    else:
        calendar = None
        for df in price_data.values():
            calendar = df.index if calendar is None else calendar.union(df.index)
    out: Dict[str, pd.DataFrame] = {}
    for sym, df in price_data.items():
        out[sym] = df.reindex(calendar).ffill(limit=ffill_limit)
    return out
