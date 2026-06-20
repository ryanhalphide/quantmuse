"""Paper-trading harness for the trend / trend+carry strategy.

Deliberately broker-agnostic: it consumes a *portfolio snapshot* (total equity +
current share counts) and the strategy's latest target weights, and produces
(a) a rebalance report -- what you'd trade to reach target -- and (b) a persisted
daily ledger of targets that can be marked to market to track paper P&L over time.

No broker API lives here. The snapshot is supplied as a dict or JSON file; the
Robinhood MCP (operated by the agent/CLI) populates it. Crucially this module
never places orders -- it only reports and records.
"""

import json
import os
from datetime import datetime
from typing import Dict, Optional

import numpy as np
import pandas as pd

from .trend_following import _metrics, ANN


def load_snapshot(path: str) -> Dict:
    """Load a portfolio snapshot {equity, positions, ...} from JSON."""
    with open(path) as f:
        return json.load(f)


def save_snapshot(path: str, equity: float, positions: Dict[str, float],
                  **extra) -> Dict:
    """Persist a portfolio snapshot. ``positions`` maps symbol -> share count."""
    snap = {"as_of": datetime.now().strftime("%Y-%m-%d"),
            "equity": float(equity), "positions": positions, **extra}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(snap, f, indent=2)
    return snap


def rebalance_report(target_weights: pd.Series, equity: float,
                     positions: Dict[str, float], prices: Dict[str, float],
                     min_trade: float = 1.0) -> pd.DataFrame:
    """Compare target weights to current holdings; return the trades to reconcile.

    target_weights: strategy weight per symbol (fraction of equity, may be negative).
    equity: total capital to size against. positions: symbol -> current shares.
    prices: symbol -> latest price. Trades below ``min_trade`` dollars are marked HOLD.
    """
    symbols = sorted(set(target_weights.index) | set(positions))
    rows = []
    for s in symbols:
        w = float(target_weights.get(s, 0.0))
        px = float(prices.get(s, float("nan")))
        cur_sh = float(positions.get(s, 0.0))
        tgt_dollars = equity * w
        cur_dollars = cur_sh * px if px == px else 0.0
        trade_dollars = tgt_dollars - cur_dollars
        trade_shares = trade_dollars / px if px == px and px > 0 else float("nan")
        action = "HOLD"
        if abs(trade_dollars) >= min_trade:
            action = "BUY" if trade_dollars > 0 else "SELL"
        rows.append({
            "symbol": s, "target_weight": w, "target_$": tgt_dollars,
            "current_$": cur_dollars, "trade_$": trade_dollars,
            "trade_shares": trade_shares, "action": action,
        })
    df = pd.DataFrame(rows).set_index("symbol")
    return df.sort_values("target_weight", ascending=False)


def record_targets(target_weights: pd.Series, prices: Dict[str, float], equity: float,
                   ledger_path: str, as_of: Optional[str] = None) -> None:
    """Append today's target weights + prices to the paper-trade ledger CSV."""
    as_of = as_of or datetime.now().strftime("%Y-%m-%d")
    rows = [{"date": as_of, "symbol": s, "weight": float(target_weights[s]),
             "price": float(prices.get(s, float("nan"))), "equity": float(equity)}
            for s in target_weights.index]
    new = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(ledger_path) or ".", exist_ok=True)
    if os.path.exists(ledger_path):
        old = pd.read_csv(ledger_path)
        new = pd.concat([old[old["date"] != as_of], new], ignore_index=True)
    new.to_csv(ledger_path, index=False)


def mark_ledger(ledger_path: str, ann: int = ANN) -> Dict:
    """Mark the recorded paper targets to market: each day's weights earn the next
    day's realized asset returns. Returns the paper equity curve + risk metrics."""
    if not os.path.exists(ledger_path):
        return {}
    df = pd.read_csv(ledger_path, parse_dates=["date"])
    W = df.pivot_table(index="date", columns="symbol", values="weight").sort_index()
    P = df.pivot_table(index="date", columns="symbol", values="price").sort_index()
    if len(W) < 2:
        return {"n_days": int(len(W)), "note": "need >=2 dated snapshots to mark P&L"}
    R = P.pct_change()
    strat_ret = (W.shift(1) * R).sum(axis=1).fillna(0.0)
    equity = (1.0 + strat_ret).cumprod()
    out = _metrics(strat_ret, equity, ann)
    out.update({"n_days": int(len(W)), "paper_equity_curve": equity,
                "paper_returns": strat_ret, "cum_return": float(equity.iloc[-1] - 1.0)})
    return out
