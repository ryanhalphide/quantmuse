"""Generate the dashboard data JSON from the real backtest + paper-trading ledger.

Runs the trend backtest (long/short and long/flat) over the full window, builds
benchmark curves, calendar-year returns (crisis alpha), the core+trend blend, the
current target weights, and the marked paper-trading P&L, then writes a compact
JSON the static frontend reads. No broker, no live orders -- pure backtest output.

    python examples/export_dashboard_data.py            # -> frontend/data.json
"""

import json
import os
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from data_service.strategies.trend_following import TSMOMConfig, tsmom_backtest, _metrics, ANN
from data_service.strategies.trend_following_data import load_universe, align_calendar
from data_service.strategies.trend_following_robustness import core_plus_trend, per_asset_contribution
from data_service.strategies import paper_trade as pt

OUT = os.path.join("frontend", "data.json")
LEDGER = "paper_trades/ledger.csv"


def _curve(series):
    """Weekly-downsampled equity curve as {dates, values} for charting."""
    s = (1.0 + series).cumprod()
    w = s.resample("W-FRI").last().dropna()
    return {"dates": [d.strftime("%Y-%m-%d") for d in w.index],
            "values": [round(float(v), 4) for v in w.values]}


def _annual(returns):
    yr = returns.groupby(returns.index.year).apply(lambda r: (1 + r).prod() - 1)
    return {int(y): round(float(v), 4) for y, v in yr.items()}


def main():
    end = datetime.now()
    start = end - timedelta(days=365 * 19)
    print("Loading 19y universe...")
    data = align_calendar(load_universe(start=start, end=end), anchor="SPY")

    ls = tsmom_backtest(data, TSMOMConfig(direction="long_short"))
    lf = tsmom_backtest(data, TSMOMConfig(direction="long_flat"))
    R = ls["asset_returns"]
    spy = R["SPY"].fillna(0.0)
    r6040 = (0.6 * R["SPY"] + 0.4 * R["TLT"]).fillna(0.0) if "TLT" in R else spy

    def m(res_or_ret, curve=None):
        if isinstance(res_or_ret, dict):
            return {k: round(float(res_or_ret["strategy"][k]), 4)
                    for k in ("sharpe", "ann_return", "ann_vol", "max_drawdown")}
        eq = (1 + res_or_ret).cumprod()
        d = _metrics(res_or_ret, eq)
        return {k: round(float(d[k]), 4) for k in ("sharpe", "ann_return", "ann_vol", "max_drawdown")}

    metrics = {
        "trend_ls": {**m(ls), "corr_to_spy": round(float(ls.get("corr_to_spy", float("nan"))), 3)},
        "trend_lf": m(lf),
        "spy": m(spy),
        "sixtyforty": m(r6040),
    }

    # Equity curves (weekly) on the common index.
    curves = {
        "trend_ls": _curve(ls["strat_returns"]),
        "trend_lf": _curve(lf["strat_returns"]),
        "spy": _curve(spy),
        "sixtyforty": _curve(r6040),
    }

    # Calendar-year trend vs SPY (crisis alpha).
    ann_trend = _annual(ls["strat_returns"])
    ann_spy = _annual(spy)
    years = sorted(set(ann_trend) | set(ann_spy))
    annual = {"years": years,
              "trend": [ann_trend.get(y) for y in years],
              "spy": [ann_spy.get(y) for y in years]}

    # Core + trend blend (the real value proposition).
    blend_df = core_plus_trend(ls, core="SPY", trend_weights=(0.3, 0.5))
    blend = [{"label": idx, "sharpe": round(float(row["sharpe"]), 3),
              "ann_return": round(float(row["ann_return"]), 4),
              "max_drawdown": round(float(row["max_drawdown"]), 4)}
             for idx, row in blend_df.iterrows()]

    # Current target weights (long/flat = realistic deployable).
    w = lf["weights"].iloc[-1]
    weights = [{"symbol": s, "weight": round(float(w[s]), 4)}
               for s in w.index if abs(float(w[s])) > 1e-4]
    weights.sort(key=lambda x: x["weight"], reverse=True)

    # Rolling 63-trading-day (~1 quarter) correlation of trend to SPY -- the
    # diversification claim over time, not just the single full-sample number.
    roll = ls["strat_returns"].rolling(63).corr(spy).dropna()
    roll_w = roll.resample("W-FRI").last().dropna()
    rolling_corr = {"dates": [d.strftime("%Y-%m-%d") for d in roll_w.index],
                    "values": [round(float(v), 3) for v in roll_w.values]}

    # Per-asset attribution: which sleeves actually drove the L/S result.
    attrib_df = per_asset_contribution(ls)
    attribution = [{"symbol": s, "total_contribution": round(float(row["total_contribution"]), 4),
                    "sleeve_sharpe": (None if pd.isna(row["sleeve_sharpe"]) else round(float(row["sleeve_sharpe"]), 3))}
                   for s, row in attrib_df.iterrows()]

    # Paper-trading P&L from the live ledger.
    paper = {"n_days": 0}
    marks = pt.mark_ledger(LEDGER)
    if marks.get("n_days", 0) >= 2:
        eq = marks["paper_equity_curve"]
        paper = {
            "n_days": marks["n_days"],
            "cum_return": round(float(marks["cum_return"]), 4),
            "sharpe": round(float(marks["sharpe"]), 3),
            "max_drawdown": round(float(marks["max_drawdown"]), 4),
            "curve": {"dates": [d.strftime("%Y-%m-%d") for d in eq.index],
                      "values": [round(float(v), 5) for v in eq.values]},
        }
    elif marks.get("n_days"):
        paper = {"n_days": marks["n_days"], "note": "need >=2 dated snapshots to mark P&L"}

    out = {
        "generated": end.strftime("%Y-%m-%d %H:%M UTC"),
        "window": f"{curves['spy']['dates'][0]} to {curves['spy']['dates'][-1]}",
        "n_assets": len(data),
        "assets": sorted(data.keys()),
        "metrics": metrics,
        "curves": curves,
        "annual": annual,
        "blend": blend,
        "weights": weights,
        "rolling_corr": rolling_corr,
        "attribution": attribution,
        "paper": paper,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"Wrote {OUT}: {len(json.dumps(out))//1024} KB, "
          f"trend L/S Sharpe {metrics['trend_ls']['sharpe']}, paper days {paper.get('n_days')}")


if __name__ == "__main__":
    main()
