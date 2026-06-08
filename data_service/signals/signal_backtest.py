"""Backtest bridge + predictive-value evaluation for composite signals.

Connects the signals module to the repo's BacktestEngine and, more importantly,
provides an honest test of whether the composite signal actually *predicts*
anything -- via information coefficient (IC) and hit rate against forward
returns -- rather than relying on a single equity curve that is easy to overfit.

The technical components (RSI, MACD) are computed locally from the price
history so the backtest is fully reproducible and consumes no API quota. News
sentiment is excluded here because reliable historical sentiment is not
available on the free tier -- so this evaluates the *technical* composite, which
you can backtest, while sentiment remains a live-only forward-test overlay.
"""

import logging
from typing import Any, Callable, Dict, Optional

import numpy as np
import pandas as pd

from .base import clamp, score_to_label

logger = logging.getLogger(__name__)

# Technical-only weights (re-normalized; sentiment unavailable historically).
TECHNICAL_WEIGHTS = {"rsi": 0.5, "macd": 0.5}


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss  # avg_loss==0 -> inf -> RSI 100 (handled below)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    # Pure uptrend (no losses) -> RSI 100; flat (no gains or losses) -> neutral 50.
    rsi = rsi.where(avg_loss != 0, 100.0)
    rsi = rsi.where(~((avg_gain == 0) & (avg_loss == 0)), 50.0)
    return rsi


def _macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    """MACD line, signal line, and histogram."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame(
        {"macd": macd_line, "signal": signal_line, "hist": macd_line - signal_line}
    )


def compute_technical_signal_series(
    price_df: pd.DataFrame,
    close_col: str = "close",
    weights: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """Compute a composite technical signal for every bar in a price history.

    Returns a DataFrame indexed like ``price_df`` with columns:
    rsi_score, macd_score, score (composite in [-1,1]), label.
    Mapping matches AlphaVantageSignalProvider so live and backtest agree.
    """
    weights = weights or TECHNICAL_WEIGHTS
    close = price_df[close_col].astype(float)

    rsi = _rsi(close)
    # RSI 30->+1, 50->0, 70->-1 (same as the live provider).
    rsi_score = ((50.0 - rsi) / 20.0).clip(-1.0, 1.0)

    macd = _macd(close)
    denom = pd.concat([macd["macd"].abs(), macd["signal"].abs()], axis=1).max(axis=1)
    denom = denom.replace(0.0, np.nan)
    macd_score = (macd["hist"] / denom).clip(-1.0, 1.0)

    out = pd.DataFrame(index=price_df.index)
    out["rsi_score"] = rsi_score
    out["macd_score"] = macd_score

    w_rsi, w_macd = weights["rsi"], weights["macd"]
    # Re-normalize per-row over whichever components are present.
    num = (rsi_score.fillna(0) * w_rsi) + (macd_score.fillna(0) * w_macd)
    wsum = (rsi_score.notna() * w_rsi) + (macd_score.notna() * w_macd)
    out["score"] = (num / wsum.replace(0.0, np.nan)).clip(-1.0, 1.0)
    out["label"] = out["score"].apply(
        lambda s: score_to_label(s) if pd.notna(s) else None
    )
    return out


def evaluate_predictive_value(
    price_df: pd.DataFrame,
    horizon: int = 5,
    close_col: str = "close",
    n_buckets: int = 5,
) -> Dict[str, Any]:
    """Measure whether the composite signal predicts forward returns.

    Computes:
      - ic: Spearman rank correlation between signal at t and the return from
        t to t+horizon (the "information coefficient"). |IC| > ~0.03-0.05 is
        the threshold where a signal is plausibly useful; near 0 = no edge.
      - hit_rate: fraction of non-neutral signals whose sign matches the
        forward return's sign.
      - bucket_returns: mean forward return per signal quantile (monotonic
        increase = the signal is ordering returns correctly).
    """
    signals = compute_technical_signal_series(price_df, close_col=close_col)
    close = price_df[close_col].astype(float)
    fwd_ret = close.shift(-horizon) / close - 1.0

    df = pd.DataFrame({"score": signals["score"], "fwd_ret": fwd_ret}).dropna()
    n = len(df)
    if n < max(30, n_buckets * 5):
        return {"n": n, "ic": None, "hit_rate": None, "bucket_returns": None,
                "note": "insufficient data for a meaningful evaluation"}

    # Spearman = Pearson correlation of ranks (avoids a scipy dependency).
    ic = df["score"].rank().corr(df["fwd_ret"].rank())

    nonzero = df[df["score"].abs() > 1e-9]
    hit_rate = (
        float((np.sign(nonzero["score"]) == np.sign(nonzero["fwd_ret"])).mean())
        if len(nonzero) > 0
        else None
    )

    try:
        buckets = pd.qcut(df["score"].rank(method="first"), n_buckets, labels=False)
        bucket_returns = df.groupby(buckets)["fwd_ret"].mean().to_dict()
        bucket_returns = {int(k): float(v) for k, v in bucket_returns.items()}
    except (ValueError, IndexError):
        bucket_returns = None

    return {
        "n": int(n),
        "horizon": horizon,
        "ic": float(ic) if pd.notna(ic) else None,
        "hit_rate": hit_rate,
        "bucket_returns": bucket_returns,
    }


def make_signal_strategy(
    buy_threshold: float = 0.15,
    sell_threshold: float = -0.15,
    position_fraction: float = 0.95,
    close_col: str = "close",
) -> Callable:
    """Build a strategy_func for BacktestEngine.run_backtest.

    Long/flat: go long when the composite score crosses above ``buy_threshold``,
    fully exit when it drops below ``sell_threshold``. Signals are computed on
    data available up to each bar (no lookahead beyond the bar's own close).
    """

    def strategy(data: pd.DataFrame, engine, **_: Any) -> None:
        signals = compute_technical_signal_series(data, close_col=close_col)
        for ts, row in data.iterrows():
            score = signals.loc[ts, "score"]
            if pd.isna(score):
                continue
            price = float(row[close_col])
            symbol = str(row.get("symbol", "ASSET"))
            holding = engine.positions.get(symbol)

            if score >= buy_threshold and holding is None:
                qty = (engine.current_capital * position_fraction) / price
                if qty > 0:
                    engine.place_order(symbol, "buy", qty, price, ts)
            elif score <= sell_threshold and holding is not None:
                engine.place_order(symbol, "sell", holding.quantity, price, ts)

    return strategy
