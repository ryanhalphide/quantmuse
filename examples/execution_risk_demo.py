"""Risk-check today's trend-following rebalance against the native C++ engine.

Same pipeline as paper_trade_demo.py, but the final step runs the proposed
trades through data_service.execution.check_rebalance_risk() instead of raw
pt.rebalance_report() -- adding risk_ok/risk_reason columns computed by the
native RiskManager (quantmuse_engine, see USAGE.md Sec.17). Still read-only
and order-free: this only ever produces a DataFrame for a human/agent to
review before deciding whether to place anything via the broker's own tools.

    python examples/execution_risk_demo.py --mode long_flat
    python examples/execution_risk_demo.py --snapshot data/portfolio_snapshot.json

See examples/paper_trade_demo.py for the snapshot format. The native engine
must be built first (QUANTMUSE_BUILD_CPP=1 pip install -e ".[cpp]", or see
USAGE.md Sec.17) -- this still runs without it, just without risk_ok columns.
"""

import argparse
import os
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

from data_service.strategies.trend_following import TSMOMConfig, build_weights, _aligned_closes
from data_service.strategies.trend_following_data import load_universe, align_calendar
from data_service.strategies import paper_trade as pt
from data_service.execution import check_rebalance_risk, HAVE_NATIVE_RISK_ENGINE


def main():
    p = argparse.ArgumentParser(description="Risk-check the trend strategy's rebalance (read-only)")
    p.add_argument("--mode", default="long_flat", choices=["long_flat", "long_short"])
    p.add_argument("--years", type=int, default=12)
    p.add_argument("--snapshot", default="data/portfolio_snapshot.json")
    p.add_argument("--ledger", default="paper_trades/ledger.csv")
    p.add_argument("--notional", type=float, default=100_000.0,
                   help="equity to use if no snapshot file is present")
    args = p.parse_args()

    print(f"Native risk engine available: {HAVE_NATIVE_RISK_ENGINE}")
    if not HAVE_NATIVE_RISK_ENGINE:
        print("  (build it per USAGE.md Sec.17: QUANTMUSE_BUILD_CPP=1 pip install -e '.[cpp]')")

    end = datetime.now()
    start = end - timedelta(days=365 * args.years)
    print(f"\nLoading universe ({args.years}y)...")
    data = align_calendar(load_universe(start=start, end=end), anchor="SPY")
    cfg = TSMOMConfig(direction=args.mode)
    W, _, _ = build_weights(data, cfg)
    targets = W.iloc[-1]
    closes = _aligned_closes(data, "close")
    prices = {s: float(closes[s].iloc[-1]) for s in closes}

    if os.path.exists(args.snapshot):
        snap = pt.load_snapshot(args.snapshot)
        equity = float(snap["equity"]); positions = snap.get("positions", {})
        print(f"Snapshot {args.snapshot}: equity ${equity:,.0f}, {len(positions)} position(s)")
    else:
        equity, positions = args.notional, {}
        print(f"No snapshot at {args.snapshot}; simulating with ${equity:,.0f} notional")

    print("\n=== Risk-checked rebalance to strategy targets ===")
    rep = check_rebalance_risk(targets, equity, positions, prices, ledger_path=args.ledger)
    show = rep[(rep["target_weight"].abs() > 1e-4) | (rep["current_$"].abs() > 1.0)]
    cols = ["target_weight", "target_$", "current_$", "trade_$", "trade_shares",
            "action", "risk_ok", "risk_reason"]
    print(show[cols].round({"target_weight": 3, "target_$": 0, "current_$": 0,
                            "trade_$": 0, "trade_shares": 3}).to_string())

    blocked = show[(show["risk_ok"] == False)]  # noqa: E712 (explicit False, not falsy-check)
    if len(blocked):
        print(f"\n{len(blocked)} trade(s) flagged by the risk engine -- see risk_reason above.")
    else:
        print("\nNo trades flagged by the risk engine.")
    print("This is advisory only -- nothing here places or has placed any order.")


if __name__ == "__main__":
    main()
