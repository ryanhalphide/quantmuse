"""Multi-symbol and walk-forward evaluation of signal predictive value.

A single-symbol IC can be luck. To trust a signal you want it to predict
returns (a) across many symbols and (b) stably across time, not just in one
regime. This module provides:

  - ic_sweep:        IC per symbol across multiple forward horizons + aggregate
  - walk_forward_ic: IC across contiguous time folds (stability over time)

Both build on compute_technical_signal_series, so they evaluate the same
composite signal the live provider produces. No API key needed (technical
components are computed locally from price history).
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .signal_backtest import compute_technical_signal_series

logger = logging.getLogger(__name__)

DEFAULT_HORIZONS = [1, 5, 10, 20]


def _ic(score: pd.Series, fwd_ret: pd.Series) -> Optional[float]:
    """Spearman IC = Pearson correlation of ranks (no scipy dependency)."""
    df = pd.DataFrame({"s": score, "r": fwd_ret}).dropna()
    if len(df) < 30:
        return None
    ic = df["s"].rank().corr(df["r"].rank())
    return float(ic) if pd.notna(ic) else None


def _forward_return(close: pd.Series, horizon: int) -> pd.Series:
    return close.shift(-horizon) / close - 1.0


def ic_sweep(
    price_data: Dict[str, pd.DataFrame],
    horizons: Optional[List[int]] = None,
    close_col: str = "close",
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Compute IC for each symbol across forward horizons, plus an aggregate.

    :param price_data: {symbol: price DataFrame with a close column}
    :param horizons: forward-return horizons in bars
    :return: dict with 'per_symbol' DataFrame (rows=symbol, cols=horizon IC) and
             'aggregate' (mean IC and fraction-positive per horizon).
    """
    horizons = horizons or DEFAULT_HORIZONS
    rows: Dict[str, Dict[int, Optional[float]]] = {}
    for symbol, df in price_data.items():
        if df is None or df.empty or close_col not in df:
            continue
        signals = compute_technical_signal_series(
            df, close_col=close_col, weights=weights
        )
        close = df[close_col].astype(float)
        rows[symbol] = {
            h: _ic(signals["score"], _forward_return(close, h)) for h in horizons
        }

    per_symbol = pd.DataFrame.from_dict(rows, orient="index")
    per_symbol = per_symbol.reindex(columns=horizons)

    aggregate = {}
    for h in horizons:
        col = per_symbol[h].dropna() if h in per_symbol else pd.Series(dtype=float)
        aggregate[h] = {
            "mean_ic": float(col.mean()) if len(col) else None,
            "median_ic": float(col.median()) if len(col) else None,
            "frac_positive": float((col > 0).mean()) if len(col) else None,
            "n_symbols": int(len(col)),
        }

    return {"per_symbol": per_symbol, "aggregate": aggregate, "horizons": horizons}


def walk_forward_ic(
    price_df: pd.DataFrame,
    horizon: int = 5,
    n_splits: int = 5,
    close_col: str = "close",
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Compute IC in contiguous time folds to test stability over time.

    A signal whose IC flips sign across folds is regime-dependent, not a robust
    edge. Returns per-fold ICs plus mean/std and the fraction of folds positive.
    """
    signals = compute_technical_signal_series(price_df, close_col=close_col, weights=weights)
    close = price_df[close_col].astype(float)
    fwd = _forward_return(close, horizon)

    df = pd.DataFrame({"score": signals["score"], "fwd": fwd}).dropna()
    if len(df) < n_splits * 30:
        return {"folds": [], "mean_ic": None, "std_ic": None,
                "frac_positive": None, "note": "insufficient data"}

    fold_size = len(df) // n_splits
    folds: List[Optional[float]] = []
    for i in range(n_splits):
        start = i * fold_size
        end = (i + 1) * fold_size if i < n_splits - 1 else len(df)
        chunk = df.iloc[start:end]
        folds.append(_ic(chunk["score"], chunk["fwd"]))

    valid = [f for f in folds if f is not None]
    return {
        "folds": folds,
        "mean_ic": float(np.mean(valid)) if valid else None,
        "std_ic": float(np.std(valid)) if valid else None,
        "frac_positive": float(np.mean([f > 0 for f in valid])) if valid else None,
        "horizon": horizon,
        "n_splits": n_splits,
    }


def cross_sectional_ls(
    price_data: Dict[str, pd.DataFrame],
    horizon: int = 1,
    quantile: float = 0.3,
    close_col: str = "close",
    weights: Optional[Dict[str, float]] = None,
    ann_factor: int = 252,
) -> Dict[str, Any]:
    """Market-neutral long/short backtest driven by the cross-sectional signal.

    Each bar: rank the universe by composite signal, go long the top
    ``quantile`` and short the bottom ``quantile`` (equal weight), and earn the
    spread of their forward returns. This monetizes a cross-sectional signal
    without taking on market drift -- so a signal that ranks well shows up as a
    positive long/short Sharpe even when a single-asset long/flat strategy would
    underperform buy-and-hold.

    Uses ``horizon=1`` by default so forward returns don't overlap. Returns the
    daily L/S series plus annualized return, Sharpe, and hit rate, and the
    equal-weight universe buy-and-hold benchmark over the same period.
    """
    scores: Dict[str, pd.Series] = {}
    rets: Dict[str, pd.Series] = {}
    for sym, df in price_data.items():
        if df is None or df.empty or close_col not in df:
            continue
        sig = compute_technical_signal_series(df, close_col=close_col, weights=weights)
        scores[sym] = sig["score"]
        rets[sym] = _forward_return(df[close_col].astype(float), horizon)

    if len(scores) < 4:
        return {"n_days": 0, "sharpe": None, "note": "need >= 4 symbols to rank"}

    score_panel = pd.DataFrame(scores)
    ret_panel = pd.DataFrame(rets)
    common = score_panel.index.intersection(ret_panel.index)
    score_panel = score_panel.loc[common]
    ret_panel = ret_panel.loc[common]

    ls_returns: Dict[Any, float] = {}
    bh_returns: Dict[Any, float] = {}
    for date in score_panel.index:
        s = score_panel.loc[date].dropna()
        r = ret_panel.loc[date]
        valid = s.index.intersection(r.dropna().index)
        if len(valid) < 4:
            continue
        s = s.loc[valid]
        r = r.loc[valid]
        k = max(1, int(len(s) * quantile))
        ranked = s.sort_values()
        shorts = ranked.index[:k]
        longs = ranked.index[-k:]
        ls_returns[date] = float(r.loc[longs].mean() - r.loc[shorts].mean())
        bh_returns[date] = float(r.mean())  # equal-weight universe

    if not ls_returns:
        return {"n_days": 0, "sharpe": None, "note": "insufficient overlapping data"}

    ls = pd.Series(ls_returns).sort_index()
    bh = pd.Series(bh_returns).sort_index()
    scale = ann_factor / horizon

    def sharpe(x: pd.Series) -> Optional[float]:
        return float(x.mean() / x.std() * np.sqrt(scale)) if x.std() > 0 else None

    return {
        "n_days": int(len(ls)),
        "horizon": horizon,
        "quantile": quantile,
        "ls_ann_return": float(ls.mean() * scale),
        "ls_sharpe": sharpe(ls),
        "ls_hit_rate": float((ls > 0).mean()),
        "benchmark_ann_return": float(bh.mean() * scale),
        "benchmark_sharpe": sharpe(bh),
        "ls_series": ls,
    }
