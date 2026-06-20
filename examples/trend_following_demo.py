"""Diversified multi-asset trend-following (time-series momentum) — full demo.

Loads a diversified ETF + crypto universe from free data, runs the vectorized
mark-to-market backtest for long/short and long/flat, validates robustness
(walk-forward OOS, parameter sensitivity, per-asset attribution, correlation to
SPY), and prints today's target weights.

    python examples/trend_following_demo.py --years 12 --target-vol 0.15

Honest framing: trend following's edge is diversification + crisis alpha, and it
is regime-dependent. The robustness section is the point — a single equity curve
proves nothing.
"""

import argparse
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

from data_service.strategies.trend_following import TSMOMConfig, run_both_directions, live_target_weights
from data_service.strategies.trend_following_data import load_universe, align_calendar
from data_service.strategies.trend_following_robustness import (
    walk_forward, parameter_sensitivity, per_asset_contribution, correlation_to_benchmark,
    core_plus_trend,
)


def _fmt(m):
    return (f"ann {m['ann_return']:+.2%}  vol {m['ann_vol']:.1%}  "
            f"Sharpe {m['sharpe']:+.2f}  maxDD {m['max_drawdown']:.1%}")


def main():
    p = argparse.ArgumentParser(description="Diversified trend-following demo")
    p.add_argument("--years", type=int, default=12)
    p.add_argument("--target-vol", type=float, default=0.15)
    args = p.parse_args()

    end = datetime.now()
    start = end - timedelta(days=365 * args.years)
    print(f"Loading universe ({args.years}y)...")
    data = load_universe(start=start, end=end)
    data = align_calendar(data, anchor="SPY")
    print(f"Loaded {len(data)} assets: {', '.join(data)}")

    cfg = TSMOMConfig(portfolio_target_vol=args.target_vol)
    both = run_both_directions(data, cfg)
    ls, lf = both["long_short"], both["long_flat"]

    print("\n=== Strategy vs benchmarks ===")
    print(f"  Trend long/short : {_fmt(ls['strategy'])}")
    print(f"  Trend long/flat  : {_fmt(lf['strategy'])}")
    if "benchmark_spy" in ls:
        print(f"  Buy & hold SPY   : {_fmt(ls['benchmark_spy'])}")
    if "benchmark_6040" in ls:
        print(f"  60/40 SPY/TLT    : {_fmt(ls['benchmark_6040'])}")
    if "corr_to_spy" in ls:
        print(f"  long/short correlation to SPY: {ls['corr_to_spy']:+.2f} "
              f"(low/negative = diversifying)")
    print(f"  long/short annualized turnover: {ls['ann_turnover']:.1f}x")

    print("\n=== Walk-forward (out-of-sample Sharpe by period) ===")
    wf = walk_forward(data, cfg, n_splits=5)
    print(f"  folds: {[round(f,2) if f is not None else None for f in wf['folds']]}")
    print(f"  mean {wf['mean_sharpe']:+.2f}  std {wf['std_sharpe']:.2f}  "
          f"frac_positive {wf['frac_positive']:.0%}")

    print("\n=== Parameter sensitivity (is the edge robust?) ===")
    ps = parameter_sensitivity(data, cfg)
    print(f"  {ps['n']} configs: Sharpe mean {ps['mean_sharpe']:+.2f}  "
          f"std {ps['std_sharpe']:.2f}  min {ps['min_sharpe']:+.2f}  "
          f"max {ps['max_sharpe']:+.2f}  frac>0.5 {ps['frac_above_0_5']:.0%}")

    print("\n=== Per-asset contribution (long/short) ===")
    contrib = per_asset_contribution(ls)
    print(contrib.round(3).to_string())

    corr = correlation_to_benchmark(ls, "SPY")
    print(f"\n  full-sample corr to SPY: {corr['corr']:+.2f}; "
          f"down-SPY-day corr: {corr['down_market_corr']}")

    print("\n=== The real use case: trend overlay on a buy-and-hold core ===")
    blend = core_plus_trend(ls, core="SPY", trend_weights=(0.3, 0.5))
    print(blend.round(4).to_string())

    print("\n=== Today's target weights (long/short) ===")
    print(live_target_weights(data, cfg).round(3).to_string())


if __name__ == "__main__":
    main()
