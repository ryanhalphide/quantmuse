"""Analyst-rating signals and an orthogonality test vs price-only signals.

Turns FMP analyst rating-count snapshots into:
  - consensus_score: a level signal in [-1, 1] (net bullishness of analysts)
  - revision_signal: month-over-month change in consensus (the documented
    alpha -- rating *changes* predict returns better than levels)

and provides evaluate_orthogonality, which answers the actual question: does the
analyst signal add predictive value *beyond* the technical (price-only) signal?
It pools a basket into monthly observations and reports:
  - IC of the analyst signal, the technical signal, and the two combined
  - the correlation between them (low corr + additive IC = orthogonal value)
"""

import logging
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from .signal_backtest import compute_technical_signal_series

logger = logging.getLogger(__name__)

RATING_WEIGHTS = {"strong_buy": 2.0, "buy": 1.0, "hold": 0.0, "sell": -1.0, "strong_sell": -2.0}


def consensus_score(grades_df: pd.DataFrame) -> pd.Series:
    """Net analyst bullishness in [-1, 1] from rating counts.

    score = (2*SB + 1*B + 0*H - 1*S - 2*SS) / (2 * total_ratings)
    """
    if grades_df is None or grades_df.empty:
        return pd.Series(dtype=float)
    cols = [c for c in RATING_WEIGHTS if c in grades_df.columns]
    total = grades_df[cols].sum(axis=1)
    weighted = sum(grades_df[c] * RATING_WEIGHTS[c] for c in cols)
    score = weighted / (2.0 * total.replace(0.0, np.nan))
    return score.clip(-1.0, 1.0)


def revision_signal(grades_df: pd.DataFrame) -> pd.Series:
    """Month-over-month change in consensus score, scaled to ~[-1, 1].

    Positive = net upgrades since the last snapshot. The change is multiplied by
    a factor because month-to-month consensus moves are small; we then clip.
    """
    score = consensus_score(grades_df)
    return (score.diff() * 5.0).clip(-1.0, 1.0)


def _rank_ic(signal: pd.Series, fwd_ret: pd.Series, min_n: int = 50) -> Optional[float]:
    df = pd.DataFrame({"s": signal, "r": fwd_ret}).dropna()
    if len(df) < min_n or df["s"].nunique() < 3:
        return None
    ic = df["s"].rank().corr(df["r"].rank())
    return float(ic) if pd.notna(ic) else None


def _strip_tz(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    idx = pd.to_datetime(idx)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return idx.normalize()


def pooled_horizon_ic(
    price_data: Dict[str, pd.DataFrame],
    signal_data: Dict[str, pd.Series],
    horizons=(1, 5, 21),
    close_col: str = "close",
    min_n: int = 200,
) -> Dict[str, Any]:
    """Pooled daily IC of a differentiated signal across multiple horizons.

    For short-horizon data (e.g. news sentiment) a monthly test is too coarse.
    This aligns each symbol's daily signal with the daily technical signal and
    forward returns at several horizons, pools across the basket, and reports --
    per horizon -- the IC of the signal, the technical signal, and the
    equal-weight z-blend, plus the (horizon-independent) correlation between the
    two signals. Indices are tz-normalized so price/signal sources can be mixed.
    """
    frames = []
    for sym, sig in signal_data.items():
        px = price_data.get(sym)
        if px is None or px.empty or sig is None or len(sig.dropna()) == 0:
            continue
        px = px.copy()
        px.index = _strip_tz(px.index)
        close = px[close_col].astype(float)
        tech = compute_technical_signal_series(px, close_col=close_col)["score"]
        s = sig.dropna().copy()
        s.index = _strip_tz(s.index)
        d = pd.DataFrame({"signal": s, "tech": tech, "close": close}).dropna()
        for h in horizons:
            d[f"f{h}"] = d["close"].shift(-h) / d["close"] - 1.0
        frames.append(d)

    if not frames:
        return {"n": 0, "horizons": {}, "note": "no aligned data"}

    panel = pd.concat(frames)

    def z(x: pd.Series) -> pd.Series:
        return (x - x.mean()) / x.std() if x.std() > 0 else x * 0.0

    combo = z(panel["signal"]) + z(panel["tech"])
    out = {
        "n": len(panel),
        "signal_correlation": float(panel["signal"].corr(panel["tech"])),
        "horizons": {},
    }
    for h in horizons:
        f = panel[f"f{h}"]
        out["horizons"][h] = {
            "ic_signal": _rank_ic(panel["signal"], f, min_n),
            "ic_technical": _rank_ic(panel["tech"], f, min_n),
            "ic_combined": _rank_ic(combo, f, min_n),
        }
    return out


def evaluate_signal_orthogonality(
    price_data: Dict[str, pd.DataFrame],
    signal_data: Dict[str, pd.Series],
    close_col: str = "close",
    min_n: int = 50,
    resample: str = "MS",
) -> Dict[str, Any]:
    """Does an arbitrary differentiated signal add value over the technical one?

    Provider-agnostic: ``signal_data`` maps symbol -> a dated signal Series (any
    frequency; resampled to ``resample`` buckets). This lets *any* alternative
    data source (analyst ratings, news/social sentiment, insider flow, ...) be
    tested with one call -- supply a signal series per symbol and it is pooled
    into per-bucket observations of (signal, technical_signal, next-bucket
    return), with no lookahead.

    Returns IC of the signal, the technical signal, and the two combined, plus
    their correlation. Low correlation + combined IC above each standalone IC
    indicates orthogonal, additive value.
    """
    records = []
    for sym, sig in signal_data.items():
        price_df = price_data.get(sym)
        if price_df is None or price_df.empty or sig is None or len(sig.dropna()) == 0:
            continue

        sig_b = sig.dropna().resample(resample).last()
        tech_daily = compute_technical_signal_series(price_df, close_col=close_col)["score"]
        tech_b = tech_daily.resample(resample).last()
        close_b = price_df[close_col].astype(float).resample(resample).first()
        fwd_ret = close_b.shift(-1) / close_b - 1.0

        for ts in sig_b.index:
            if ts in tech_b.index and ts in fwd_ret.index:
                a, t, r = sig_b.loc[ts], tech_b.loc[ts], fwd_ret.loc[ts]
                if pd.notna(a) and pd.notna(t) and pd.notna(r):
                    records.append((float(a), float(t), float(r)))

    n = len(records)
    if n < min_n:
        return {"n": n, "ic_signal": None, "ic_technical": None,
                "ic_combined": None, "signal_correlation": None,
                "note": f"underpowered: only {n} pooled observations (need >= {min_n}). "
                        "Supply deeper history (a paid data key) to validate."}

    panel = pd.DataFrame(records, columns=["signal", "technical", "fwd"])

    def z(s: pd.Series) -> pd.Series:
        return (s - s.mean()) / s.std() if s.std() > 0 else s * 0.0

    combined = z(panel["signal"]) + z(panel["technical"])
    return {
        "n": n,
        "ic_signal": _rank_ic(panel["signal"], panel["fwd"], min_n),
        "ic_technical": _rank_ic(panel["technical"], panel["fwd"], min_n),
        "ic_combined": _rank_ic(combined, panel["fwd"], min_n),
        "signal_correlation": float(panel["signal"].corr(panel["technical"])),
    }


def evaluate_orthogonality(
    price_data: Dict[str, pd.DataFrame],
    analyst_data: Dict[str, pd.DataFrame],
    use_revision: bool = True,
    close_col: str = "close",
    min_n: int = 50,
) -> Dict[str, Any]:
    """Analyst-rating wrapper around :func:`evaluate_signal_orthogonality`.

    Converts each symbol's grade history into a signal series (revision by
    default, else consensus level), then runs the generic orthogonality test.
    """
    signal_data = {
        sym: (revision_signal(g) if use_revision else consensus_score(g))
        for sym, g in analyst_data.items()
    }
    res = evaluate_signal_orthogonality(
        price_data, signal_data, close_col=close_col, min_n=min_n
    )
    res["ic_analyst"] = res.pop("ic_signal")  # name it for the analyst context
    res["use_revision"] = use_revision
    return res
