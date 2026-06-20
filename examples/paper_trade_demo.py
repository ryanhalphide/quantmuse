"""Paper-trade the trend (or trend+carry) strategy against a portfolio snapshot.

Read-only and order-free: computes today's target weights, compares them to a
portfolio snapshot (total equity + current shares), prints the trades that would
reconcile them, records the targets to a ledger, and marks the ledger to market to
report paper P&L accrued so far.

    python examples/paper_trade_demo.py --mode long_flat --record
    python examples/paper_trade_demo.py --carry --snapshot data/portfolio_snapshot.json

The snapshot is a JSON file ({"equity": ..., "positions": {SYM: shares}}). Populate
it from your broker (e.g. the Robinhood MCP) or use --notional for pure simulation.
See examples/portfolio_snapshot.example.json for the format.
"""

import argparse
import os
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

import pandas as pd

from data_service.strategies.trend_following import (
    TSMOMConfig, build_weights, build_combined_weights, _aligned_closes,
)
from data_service.strategies.trend_following_data import load_universe, align_calendar
from data_service.strategies.carry import build_carry_panel
from data_service.strategies import paper_trade as pt


def main():
    p = argparse.ArgumentParser(description="Paper-trade the trend strategy (read-only)")
    p.add_argument("--mode", default="long_flat", choices=["long_flat", "long_short"],
                   help="long_flat is realistic for a cash account (no shorting)")
    p.add_argument("--carry", action="store_true", help="use the gated trend+carry combo")
    p.add_argument("--years", type=int, default=12)
    p.add_argument("--snapshot", default="data/portfolio_snapshot.json")
    p.add_argument("--ledger", default="data/paper_trades/ledger.csv")
    p.add_argument("--notional", type=float, default=100_000.0,
                   help="equity to use if no snapshot file is present")
    p.add_argument("--record", action="store_true", help="append today's targets to the ledger")
    args = p.parse_args()

    end = datetime.now()
    start = end - timedelta(days=365 * args.years)
    print(f"Loading universe ({args.years}y)...")
    data = align_calendar(load_universe(start=start, end=end), anchor="SPY")
    cfg = TSMOMConfig(direction=args.mode, carry_weight=0.5 if args.carry else 0.0)

    if args.carry:
        C = build_carry_panel(data, start, end)
        W, _, _ = build_combined_weights(data, cfg, C)
        print("Targets: gated trend+carry combination")
    else:
        W, _, _ = build_weights(data, cfg)
        print(f"Targets: trend ({args.mode})")
    targets = W.iloc[-1]
    closes = _aligned_closes(data, "close")
    prices = {s: float(closes[s].iloc[-1]) for s in closes}

    # Snapshot: real broker data if present, else pure-simulation notional.
    if os.path.exists(args.snapshot):
        snap = pt.load_snapshot(args.snapshot)
        equity = float(snap["equity"]); positions = snap.get("positions", {})
        print(f"Snapshot {args.snapshot}: equity ${equity:,.0f}, "
              f"{len(positions)} mapped position(s) as of {snap.get('as_of','?')}")
    else:
        equity, positions = args.notional, {}
        print(f"No snapshot at {args.snapshot}; simulating with ${equity:,.0f} notional")

    print("\n=== Rebalance to strategy targets ===")
    rep = pt.rebalance_report(targets, equity, positions, prices)
    show = rep[(rep["target_weight"].abs() > 1e-4) | (rep["current_$"].abs() > 1.0)]
    print(show.round({"target_weight": 3, "target_$": 0, "current_$": 0,
                      "trade_$": 0, "trade_shares": 3}).to_string())
    gross = float(rep["target_weight"].abs().sum())
    print(f"\nGross exposure {gross:.2f}x  |  net {rep['target_weight'].sum():+.2f}x  "
          f"|  est. cash {equity*(1-rep['target_weight'].clip(lower=0).sum()):,.0f}")

    if args.record:
        pt.record_targets(targets, prices, equity, args.ledger)
        print(f"\nRecorded targets to {args.ledger}")

    marks = pt.mark_ledger(args.ledger)
    if marks.get("n_days", 0) >= 2:
        print(f"\n=== Paper P&L to date ({marks['n_days']} snapshots) ===")
        print(f"  cum return {marks['cum_return']:+.2%}  ann {marks['ann_return']:+.2%}  "
              f"Sharpe {marks['sharpe']:+.2f}  maxDD {marks['max_drawdown']:.1%}")
    elif marks.get("n_days"):
        print(f"\nPaper ledger has {marks['n_days']} snapshot(s); need >=2 to mark P&L.")


if __name__ == "__main__":
    main()
