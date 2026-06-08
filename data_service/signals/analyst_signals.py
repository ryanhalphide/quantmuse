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


def evaluate_orthogonality(
    price_data: Dict[str, pd.DataFrame],
    analyst_data: Dict[str, pd.DataFrame],
    use_revision: bool = True,
    close_col: str = "close",
    min_n: int = 50,
) -> Dict[str, Any]:
    """Does the analyst signal add predictive value over the technical signal?

    Pools all symbols into monthly observations of (analyst_signal,
    technical_signal, next-month return) and computes the IC of each signal
    alone, the combined (equal-weight z-blend) IC, and the correlation between
    the two signals. Low signal correlation + a combined IC above each
    standalone IC indicates orthogonal, additive value.

    Monthly alignment uses month-start snapshots and the next month's return,
    so there is no lookahead.
    """
    records = []
    for sym, grades in analyst_data.items():
        price_df = price_data.get(sym)
        if price_df is None or price_df.empty or grades is None or grades.empty:
            continue

        analyst = revision_signal(grades) if use_revision else consensus_score(grades)
        analyst = analyst.dropna()
        if analyst.empty:
            continue

        # Technical signal resampled to month start (last obs of each month).
        tech_daily = compute_technical_signal_series(price_df, close_col=close_col)["score"]
        tech_monthly = tech_daily.resample("MS").last()

        # Next-month return from month-start close.
        monthly_close = price_df[close_col].astype(float).resample("MS").first()
        fwd_ret = monthly_close.shift(-1) / monthly_close - 1.0

        idx = analyst.index.normalize()
        analyst.index = idx
        for ts in idx:
            if ts in tech_monthly.index and ts in fwd_ret.index:
                a, t, r = analyst.loc[ts], tech_monthly.loc[ts], fwd_ret.loc[ts]
                if pd.notna(a) and pd.notna(t) and pd.notna(r):
                    records.append((float(a), float(t), float(r)))

    n = len(records)
    if n < min_n:
        return {"n": n, "ic_analyst": None, "ic_technical": None,
                "ic_combined": None, "signal_correlation": None,
                "note": f"underpowered: only {n} pooled observations (need >= {min_n}). "
                        "Free-tier analyst history is too shallow; use a paid key "
                        "or deeper history to validate."}

    panel = pd.DataFrame(records, columns=["analyst", "technical", "fwd"])

    def z(s: pd.Series) -> pd.Series:
        return (s - s.mean()) / s.std() if s.std() > 0 else s * 0.0

    combined = z(panel["analyst"]) + z(panel["technical"])
    return {
        "n": n,
        "ic_analyst": _rank_ic(panel["analyst"], panel["fwd"], min_n),
        "ic_technical": _rank_ic(panel["technical"], panel["fwd"], min_n),
        "ic_combined": _rank_ic(combined, panel["fwd"], min_n),
        "signal_correlation": float(panel["analyst"].corr(panel["technical"])),
        "use_revision": use_revision,
    }
