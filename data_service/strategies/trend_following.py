"""Diversified multi-asset time-series momentum (trend following) with vol targeting.

This is the synthesis of the strongest, most robust, free-data-implementable edge
documented in the quant literature: *diversified time-series momentum* (a.k.a.
trend following / managed futures). Key facts that shaped this design:

- Diversified TSMOM has historically earned a Sharpe of ~1.0-1.2 -- but the edge
  comes from DIVERSIFICATION across many low-correlation markets plus VOLATILITY
  TARGETING, not from any single clever signal (Moskowitz/Ooi/Pedersen 2012; AQR
  "Demystifying Managed Futures").
- It is counter-cyclical: it tends to profit in sustained crises (2008, 2022),
  which is why its low/negative correlation to equities matters as much as its
  standalone return.
- We use TIME-SERIES (per-asset) momentum, NOT cross-sectional: the cross-sectional
  short leg is now broken in equities (catastrophic momentum crashes in 2009/2020).
- Signals: an ensemble of EWMAC (EWMA crossover) rules at multiple speeds, optionally
  a 12-month trend sign with a 200-day moving-average filter. Canonical, not tuned.

Honest caveat: trend following is regime-dependent (weak 2013-2019, soft 2023-2024)
and whipsaws in choppy markets. Its value is diversification + crisis alpha.

Everything here is vectorized pandas and lookahead-free: every transform is causal
(ewm/rolling/expanding/shift/pct_change), and positions are executed with a single
central ``shift(1)`` in the backtest. The mark-to-market accounting mirrors
``data_service/signals/signal_backtest.py:long_flat_backtest`` generalized to a
multi-asset panel (the repo's BacktestEngine marks at average cost and is unfit for
an equity curve).
"""

from dataclasses import dataclass, field, replace
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

ANN = 252


@dataclass
class TSMOMConfig:
    """All knobs for the trend-following system (canonical defaults, not tuned)."""

    ewmac_pairs: Tuple[Tuple[int, int], ...] = ((16, 64), (32, 128), (64, 256))
    use_ts_sign: bool = False          # alt rule: 12m sign + 200d MA filter
    ts_lookback: int = 252             # 12 months
    ma_filter: int = 200               # 200-day trend filter for the ts-sign rule
    vol_lookback: int = 33             # EWMA span for realized vol (~32 trading days)
    fdm: float = 1.1                   # forecast diversification multiplier
    forecast_cap: float = 2.0          # cap on combined forecast (avg |forecast| ~ 1)
    target_abs_forecast: float = 1.0   # expanding-scaled average |forecast| target
    target_vol_per_asset: float = 0.10 # annual vol budget per asset (pre portfolio scale)
    portfolio_target_vol: float = 0.15 # annual portfolio vol target
    portfolio_vol_lookback: int = 63   # window for portfolio vol estimate (~quarter)
    max_asset_leverage: float = 2.0    # cap on |weight| per asset
    max_gross_leverage: float = 4.0    # cap on sum |weight|
    buffer_fraction: float = 0.15      # no-trade band (fraction of target) to cut turnover
    direction: str = "long_short"      # or "long_flat"
    cost_bps: float = 5.0              # transaction cost per unit turnover, bps
    initial_capital: float = 100_000.0
    ann_factor: int = ANN


# --------------------------------------------------------------------------- #
# Forecasts (per-asset trend signal)                                          #
# --------------------------------------------------------------------------- #
def _ewmac_forecast(close: pd.Series, fast: int, slow: int, vol_lookback: int) -> pd.Series:
    """Volatility-normalized EWMA crossover (Carver-style), unscaled."""
    ema_fast = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
    raw = ema_fast - ema_slow
    daily_ret = close.pct_change()
    # Price-unit daily volatility, so the crossover is expressed in "risk units".
    price_vol = daily_ret.ewm(span=vol_lookback, adjust=False).std() * close
    return raw / price_vol.replace(0.0, np.nan)


def _scale_and_cap(forecast: pd.Series, target_abs: float, cap: float) -> pd.Series:
    """Scale so the average absolute forecast ~= target_abs, then cap. No lookahead:
    the scalar uses an expanding (past-only) mean."""
    avg_abs = forecast.abs().expanding(min_periods=50).mean()
    scalar = target_abs / avg_abs.replace(0.0, np.nan)
    return (forecast * scalar).clip(-cap, cap)


def _ts_sign_forecast(close: pd.Series, cfg: TSMOMConfig) -> pd.Series:
    """12-month trend sign gated by a 200-day moving-average filter; in {-1, 0, +1}."""
    past_ret = close / close.shift(cfg.ts_lookback) - 1.0
    ma = close.rolling(cfg.ma_filter, min_periods=cfg.ma_filter).mean()
    sign = np.sign(past_ret)
    long_ok = (close > ma).astype(float)
    short_ok = (close < ma).astype(float)
    fc = np.where(sign > 0, long_ok, np.where(sign < 0, -short_ok, 0.0))
    out = pd.Series(fc, index=close.index)
    # NaN out the warmup region where we can't compute the rule.
    out[past_ret.isna() | ma.isna()] = np.nan
    return out


def compute_forecast_series(close: pd.Series, cfg: TSMOMConfig) -> pd.Series:
    """Combined, bounded per-asset trend forecast (avg |forecast| ~ 1, capped)."""
    close = close.astype(float)
    if cfg.use_ts_sign:
        return _ts_sign_forecast(close, cfg)
    rules = []
    for fast, slow in cfg.ewmac_pairs:
        f = _ewmac_forecast(close, fast, slow, cfg.vol_lookback)
        rules.append(_scale_and_cap(f, cfg.target_abs_forecast, cfg.forecast_cap))
    combined = pd.concat(rules, axis=1).mean(axis=1)
    return (combined * cfg.fdm).clip(-cfg.forecast_cap, cfg.forecast_cap)


def realized_vol(close: pd.Series, lookback: int, ann_factor: int = ANN) -> pd.Series:
    """Annualized EWMA volatility of daily returns."""
    return close.astype(float).pct_change().ewm(span=lookback, adjust=False).std() * np.sqrt(ann_factor)


# --------------------------------------------------------------------------- #
# Position sizing (volatility targeting)                                       #
# --------------------------------------------------------------------------- #
def _position_from_forecast(forecast: pd.Series, vol: pd.Series, cfg: TSMOMConfig) -> pd.Series:
    """Per-asset weight = forecast * (per-asset vol target / realized vol).

    A full forecast (~1) targets ``target_vol_per_asset`` annualized risk in that
    asset. long_flat clips shorts to zero so the long side is identical to long_short.
    """
    w = forecast * (cfg.target_vol_per_asset / vol.replace(0.0, np.nan))
    if cfg.direction == "long_flat":
        w = w.clip(lower=0.0)
    return w.clip(-cfg.max_asset_leverage, cfg.max_asset_leverage)


def _apply_portfolio_vol_target(W: pd.DataFrame, R: pd.DataFrame, cfg: TSMOMConfig) -> pd.DataFrame:
    """Scale the whole book to a target annual vol using ONLY past information."""
    gross_ret = (W.shift(1) * R).sum(axis=1)
    port_vol = gross_ret.ewm(span=cfg.portfolio_vol_lookback, adjust=False).std() * np.sqrt(cfg.ann_factor)
    scale = (cfg.portfolio_target_vol / port_vol.replace(0.0, np.nan)).shift(1)
    scale = scale.clip(upper=cfg.max_gross_leverage).fillna(0.0)
    W_scaled = W.mul(scale, axis=0)
    # Enforce gross leverage cap row-wise.
    gross = W_scaled.abs().sum(axis=1)
    excess = (gross / cfg.max_gross_leverage).clip(lower=1.0)
    return W_scaled.div(excess, axis=0).fillna(0.0)


# --------------------------------------------------------------------------- #
# Weight panel + backtest                                                      #
# --------------------------------------------------------------------------- #
def _apply_buffer(W: pd.DataFrame, buffer_fraction: float) -> pd.DataFrame:
    """No-trade band: hold the current position until the target moves more than
    ``buffer_fraction * |target|`` away, then jump to the new target. Causal and
    path-dependent only on the past, so no lookahead. Cuts turnover/cost materially
    (Carver-style buffering) at the price of slightly staler positions."""
    if buffer_fraction <= 0:
        return W
    vals = W.values
    out = np.empty_like(vals)
    prev = np.zeros(vals.shape[1])
    for t in range(vals.shape[0]):
        target = vals[t]
        band = buffer_fraction * np.abs(target)
        newpos = np.where(np.abs(target - prev) > band, target, prev)
        out[t] = newpos
        prev = newpos
    return pd.DataFrame(out, index=W.index, columns=W.columns)


def _aligned_closes(price_data: Dict[str, pd.DataFrame], close_col: str) -> pd.DataFrame:
    closes = pd.DataFrame({sym: df[close_col].astype(float) for sym, df in price_data.items()})
    return closes.sort_index()


def build_weights(price_data: Dict[str, pd.DataFrame], cfg: TSMOMConfig,
                  close_col: str = "close") -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (weights, forecasts, asset_returns) panels aligned on a common index."""
    closes = _aligned_closes(price_data, close_col)
    R = closes.pct_change()
    F = pd.DataFrame({sym: compute_forecast_series(closes[sym].dropna(), cfg) for sym in closes})
    F = F.reindex(closes.index)
    V = pd.DataFrame({sym: realized_vol(closes[sym], cfg.vol_lookback, cfg.ann_factor) for sym in closes})
    W = pd.DataFrame({sym: _position_from_forecast(F[sym], V[sym], cfg) for sym in closes})
    # Mask assets that don't yet have a valid forecast/vol (different start dates).
    W = W.where(F.notna() & V.notna(), 0.0).fillna(0.0)
    W = _apply_portfolio_vol_target(W, R.fillna(0.0), cfg)
    W = _apply_buffer(W, cfg.buffer_fraction)
    return W, F, R


def _metrics(r: pd.Series, eq: pd.Series, ann: int = ANN) -> Dict[str, float]:
    """Risk metrics (identical formula to long_flat_backtest for consistency)."""
    n = len(r)
    ann_return = float(eq.iloc[-1] ** (ann / n) - 1.0) if n > 0 and eq.iloc[-1] > 0 else float("nan")
    vol = float(r.std() * np.sqrt(ann))
    sharpe = float(r.mean() / r.std() * np.sqrt(ann)) if r.std() > 0 else float("nan")
    peak = eq.cummax()
    max_dd = float((eq / peak - 1.0).min())
    return {"ann_return": ann_return, "ann_vol": vol, "sharpe": sharpe, "max_drawdown": max_dd}


def tsmom_backtest(price_data: Dict[str, pd.DataFrame], cfg: TSMOMConfig = None,
                   close_col: str = "close") -> Dict[str, Any]:
    """Vectorized, mark-to-market, lookahead-free multi-asset trend-following backtest.

    Returns strategy metrics, buy-hold SPY and 60/40 benchmarks (when available),
    the equity curve, per-asset weight/return panels, turnover and correlation to SPY.
    """
    cfg = cfg or TSMOMConfig()
    W, F, R = build_weights(price_data, cfg, close_col)

    held = W.shift(1).fillna(0.0)                       # act next bar (no lookahead)
    gross_ret = (held * R).sum(axis=1)
    turnover = (held - held.shift(1)).abs().sum(axis=1).fillna(held.abs().sum(axis=1))
    cost = turnover * (cfg.cost_bps / 1e4)
    strat_ret = (gross_ret - cost).fillna(0.0)
    equity = (1.0 + strat_ret).cumprod()

    out: Dict[str, Any] = {
        "strategy": _metrics(strat_ret, equity, cfg.ann_factor),
        "equity_curve": equity,
        "strat_returns": strat_ret,
        "weights": W,
        "held": held,
        "forecasts": F,
        "asset_returns": R,
        "turnover": turnover,
        "ann_turnover": float(turnover.mean() * cfg.ann_factor),
        "direction": cfg.direction,
        "config": cfg,
    }

    if "SPY" in R.columns:
        spy_ret = R["SPY"].fillna(0.0)
        out["benchmark_spy"] = _metrics(spy_ret, (1.0 + spy_ret).cumprod(), cfg.ann_factor)
        denom = strat_ret.std() * spy_ret.std()
        out["corr_to_spy"] = float(strat_ret.cov(spy_ret) / denom) if denom > 0 else float("nan")
        if "TLT" in R.columns:
            r6040 = (0.6 * R["SPY"] + 0.4 * R["TLT"]).fillna(0.0)
            out["benchmark_6040"] = _metrics(r6040, (1.0 + r6040).cumprod(), cfg.ann_factor)
    return out


def run_both_directions(price_data: Dict[str, pd.DataFrame], cfg: TSMOMConfig = None,
                        close_col: str = "close") -> Dict[str, Dict[str, Any]]:
    """Run long/short and long/flat with otherwise-identical config, for comparison."""
    cfg = cfg or TSMOMConfig()
    return {
        "long_short": tsmom_backtest(price_data, replace(cfg, direction="long_short"), close_col),
        "long_flat": tsmom_backtest(price_data, replace(cfg, direction="long_flat"), close_col),
    }


# --------------------------------------------------------------------------- #
# Live signal                                                                  #
# --------------------------------------------------------------------------- #
def live_target_weights(price_data: Dict[str, pd.DataFrame], cfg: TSMOMConfig = None,
                        close_col: str = "close") -> pd.DataFrame:
    """Today's target weights per asset, from the SAME pipeline as the backtest.

    The last (un-shifted) weight row is what you would execute next session. Returns
    a DataFrame indexed by symbol with columns: forecast, realized_vol, target_weight.
    """
    cfg = cfg or TSMOMConfig()
    W, F, R = build_weights(price_data, cfg, close_col)
    closes = _aligned_closes(price_data, close_col)
    V = pd.DataFrame({sym: realized_vol(closes[sym], cfg.vol_lookback, cfg.ann_factor) for sym in closes})
    return pd.DataFrame({
        "forecast": F.iloc[-1],
        "realized_vol": V.iloc[-1],
        "target_weight": W.iloc[-1],
    }).sort_values("target_weight", ascending=False)
