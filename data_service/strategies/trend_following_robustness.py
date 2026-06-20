"""Robustness suite for the trend-following system.

A single backtest equity curve is easy to fool yourself with. This module stress-tests
the strategy the way the rest of the repo does (mirroring signal_sweep.walk_forward_ic):
out-of-sample stability over time, parameter sensitivity (is the edge robust or one
lucky lookback?), per-asset attribution (is diversification doing the work?), and
correlation to SPY (the diversification/crisis-alpha claim).
"""

from dataclasses import replace
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .trend_following import TSMOMConfig, tsmom_backtest, _metrics


def walk_forward(price_data: Dict[str, pd.DataFrame], cfg: TSMOMConfig = None,
                 n_splits: int = 5, close_col: str = "close") -> Dict[str, Any]:
    """Slice the strategy's daily returns into contiguous folds and report per-fold
    Sharpe. TSMOM has no fitted parameters, so every fold is genuinely out-of-sample;
    stability (mostly-positive, low-dispersion Sharpe) is the thing we want to see."""
    cfg = cfg or TSMOMConfig()
    res = tsmom_backtest(price_data, cfg, close_col)
    r = res["strat_returns"]
    folds: List[Optional[float]] = []
    bounds = np.linspace(0, len(r), n_splits + 1).astype(int)
    for i in range(n_splits):
        seg = r.iloc[bounds[i]:bounds[i + 1]]
        if len(seg) > 20 and seg.std() > 0:
            folds.append(float(seg.mean() / seg.std() * np.sqrt(cfg.ann_factor)))
        else:
            folds.append(None)
    valid = [f for f in folds if f is not None]
    return {
        "folds": folds,
        "mean_sharpe": float(np.mean(valid)) if valid else None,
        "std_sharpe": float(np.std(valid)) if valid else None,
        "frac_positive": float(np.mean([f > 0 for f in valid])) if valid else None,
        "n_splits": n_splits,
    }


_DEFAULT_SPEED_GRID: Tuple[Tuple[Tuple[int, int], ...], ...] = (
    ((8, 32), (16, 64)),
    ((16, 64), (32, 128), (64, 256)),
    ((32, 128), (64, 256), (128, 512)),
)


def parameter_sensitivity(price_data: Dict[str, pd.DataFrame], cfg: TSMOMConfig = None,
                          speed_grid: Tuple = _DEFAULT_SPEED_GRID,
                          vol_lookbacks: Tuple[int, ...] = (20, 33, 63),
                          target_vols: Tuple[float, ...] = (0.10, 0.15, 0.20),
                          close_col: str = "close") -> Dict[str, Any]:
    """Sweep canonical parameter sets; report the Sharpe distribution. A robust edge
    is positive across most of the grid, not concentrated in one lucky setting."""
    cfg = cfg or TSMOMConfig()
    rows = []
    for speeds in speed_grid:
        for vl in vol_lookbacks:
            for tv in target_vols:
                c = replace(cfg, ewmac_pairs=speeds, vol_lookback=vl, portfolio_target_vol=tv)
                sharpe = tsmom_backtest(price_data, c, close_col)["strategy"]["sharpe"]
                rows.append({"speeds": str(speeds), "vol_lookback": vl,
                             "target_vol": tv, "sharpe": sharpe})
    table = pd.DataFrame(rows)
    s = table["sharpe"].dropna()
    return {
        "table": table,
        "mean_sharpe": float(s.mean()) if len(s) else None,
        "std_sharpe": float(s.std()) if len(s) else None,
        "min_sharpe": float(s.min()) if len(s) else None,
        "max_sharpe": float(s.max()) if len(s) else None,
        "frac_above_0_5": float((s > 0.5).mean()) if len(s) else None,
        "n": int(len(s)),
    }


def per_asset_contribution(result: Dict[str, Any]) -> pd.DataFrame:
    """Each asset's contribution to total return + standalone Sharpe of its sleeve."""
    held, R = result["held"], result["asset_returns"]
    cfg = result["config"]
    contrib = (held * R).fillna(0.0)
    sharpe = contrib.apply(
        lambda c: c.mean() / c.std() * np.sqrt(cfg.ann_factor) if c.std() > 0 else np.nan
    )
    return pd.DataFrame({
        "total_contribution": contrib.sum(),
        "sleeve_sharpe": sharpe,
        "avg_abs_weight": held.abs().mean(),
    }).sort_values("total_contribution", ascending=False)


def core_plus_trend(result: Dict[str, Any], core: str = "SPY",
                    trend_weights: Tuple[float, ...] = (0.3, 0.5)) -> pd.DataFrame:
    """The actual use case: blend a buy-and-hold core with the trend overlay.

    Trend following rarely beats a buy-and-hold equity core standalone in a bull
    market, but because it is ~uncorrelated it improves the *combined* portfolio's
    Sharpe and drawdown. Returns metrics for the core alone and for each
    (1-w)*core + w*trend blend, daily-rebalanced.
    """
    R, r = result["asset_returns"], result["strat_returns"]
    cfg = result["config"]
    if core not in R.columns:
        return pd.DataFrame()
    core_ret = R[core].reindex(r.index).fillna(0.0)
    rows = {"100% " + core: _metrics(core_ret, (1.0 + core_ret).cumprod(), cfg.ann_factor)}
    for w in trend_weights:
        blend = (1.0 - w) * core_ret + w * r
        label = f"{int((1-w)*100)}% {core} / {int(w*100)}% trend"
        rows[label] = _metrics(blend, (1.0 + blend).cumprod(), cfg.ann_factor)
    return pd.DataFrame(rows).T[["ann_return", "ann_vol", "sharpe", "max_drawdown"]]


def correlation_to_benchmark(result: Dict[str, Any], benchmark: str = "SPY") -> Dict[str, Any]:
    """Full-sample and down-market correlation to the benchmark (diversification/crisis
    alpha check). Low/near-zero correlation is the central value proposition."""
    R = result["asset_returns"]
    r = result["strat_returns"]
    if benchmark not in R.columns:
        return {"corr": None, "down_market_corr": None}
    b = R[benchmark].reindex(r.index).fillna(0.0)
    full = float(r.corr(b))
    down = b < 0
    dcorr = float(r[down].corr(b[down])) if down.sum() > 10 else None
    return {"corr": full, "down_market_corr": dcorr,
            "strat_mean_when_spy_down": float(r[down].mean()) if down.sum() else None}
