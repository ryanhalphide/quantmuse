"""Carry forecasts per asset class, assembled into a panel for the trend system.

Each raw carry signal is volatility-/scale-normalized with the same causal,
no-lookahead ``_scale_and_cap`` used for trend forecasts, so carry and trend
positions are directly comparable and can be blended at the book level.
"""

import logging
from datetime import datetime
from typing import Dict, Optional

import pandas as pd

from .trend_following import TSMOMConfig, _scale_and_cap, _aligned_closes
from . import carry_data

logger = logging.getLogger(__name__)

# Carry signals are defined for these assets; others get no carry (zero weight).
BOND_ASSETS = ("TLT", "IEF")
EQUITY_ASSETS = ("SPY", "QQQ", "EFA", "EEM", "IWM", "VNQ")
CRYPTO_ASSETS = ("BTC", "ETH")


def bond_carry(rates: pd.DataFrame, index: pd.Index, cap: float) -> pd.Series:
    """Term-structure carry: 10y minus 3m yield (steep curve => positive carry)."""
    spread = (rates["y10"] - rates["m3"]).reindex(index).ffill(limit=5)
    return _scale_and_cap(spread, 1.0, cap)


def equity_carry(div_yield: pd.Series, cash_rate_pct: pd.Series, index: pd.Index,
                 cap: float) -> pd.Series:
    """Equity carry proxy: trailing dividend yield minus the cash (3m) rate."""
    cash = (cash_rate_pct / 100.0).reindex(index).ffill(limit=5)
    raw = (div_yield.reindex(index) - cash)
    return _scale_and_cap(raw, 1.0, cap)


def crypto_carry(funding_annual: pd.Series, index: pd.Index, cap: float) -> pd.Series:
    """Crypto carry: minus the annualized funding rate (long a perp earns -funding)."""
    raw = (-funding_annual).reindex(index)
    return _scale_and_cap(raw, 1.0, cap)


def build_carry_panel(price_data: Dict[str, pd.DataFrame], start: datetime, end: datetime,
                      cfg: Optional[TSMOMConfig] = None, close_col: str = "close",
                      include_crypto: bool = True) -> pd.DataFrame:
    """Assemble per-asset carry forecasts aligned to the price calendar.

    Assets without a carry signal (and dates before a signal exists, e.g. crypto
    funding pre-2019) are left NaN -- the backtest maps NaN carry to zero weight.
    """
    cfg = cfg or TSMOMConfig()
    closes = _aligned_closes(price_data, close_col)
    idx = closes.index
    cap = cfg.forecast_cap
    panel = pd.DataFrame(index=idx)

    rates = carry_data.load_rates(start, end)
    if not rates.empty:
        bc = bond_carry(rates, idx, cap)
        for s in BOND_ASSETS:
            if s in closes:
                panel[s] = bc
        for s in EQUITY_ASSETS:
            if s in closes:
                dy = carry_data.load_dividend_yield(s, closes[s])
                if not dy.empty:
                    panel[s] = equity_carry(dy, rates["m3"], idx, cap)

    if include_crypto:
        for s in CRYPTO_ASSETS:
            if s in closes:
                f = carry_data.load_funding(s, start, end)
                if not f.empty:
                    panel[s] = crypto_carry(f, idx, cap)

    return panel.reindex(columns=closes.columns)
