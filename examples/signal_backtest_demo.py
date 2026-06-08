"""Test whether the composite signal actually predicts returns.

Pulls daily price history (Yahoo Finance, no API key needed), then:
  1. Reports the signal's predictive value: information coefficient (IC),
     hit rate, and mean forward return by signal bucket.
  2. Runs a long/flat backtest of the signal through the repo's BacktestEngine.

The IC/hit-rate analysis is the honest answer to "does this signal work?" -- a
single equity curve can look good by luck, but a near-zero IC across many bars
means there is no real edge.

Usage
-----
    python examples/signal_backtest_demo.py AAPL --years 5 --horizon 5
"""

import argparse
from datetime import datetime, timedelta

from data_service.fetchers.yahoo_fetcher import YahooFetcher
from data_service.backtest.backtest_engine import BacktestEngine
from data_service.signals.signal_backtest import (
    evaluate_predictive_value,
    make_signal_strategy,
)


def main():
    parser = argparse.ArgumentParser(description="Signal predictive-value test")
    parser.add_argument("symbol", help="Ticker, e.g. AAPL")
    parser.add_argument("--years", type=int, default=5, help="Years of history")
    parser.add_argument("--horizon", type=int, default=5, help="Forward-return horizon (bars)")
    parser.add_argument("--buy", type=float, default=0.15, help="Buy threshold")
    parser.add_argument("--sell", type=float, default=-0.15, help="Sell threshold")
    args = parser.parse_args()

    end = datetime.now()
    start = end - timedelta(days=365 * args.years)
    df = YahooFetcher().fetch_historical_data(
        args.symbol, start_time=start, end_time=end, interval="1d"
    )
    if df.empty:
        raise SystemExit(f"No data for {args.symbol}")
    df["symbol"] = args.symbol

    # 1) Predictive value -- the honest test.
    ev = evaluate_predictive_value(df, horizon=args.horizon)
    print(f"\n=== Predictive value: {args.symbol} ({ev.get('n')} bars, "
          f"{args.horizon}-bar forward return) ===")
    ic = ev.get("ic")
    print(f"Information Coefficient (Spearman): {ic:+.4f}" if ic is not None else "IC: n/a")
    if ic is not None:
        verdict = ("plausible edge" if abs(ic) >= 0.03 else "no meaningful edge")
        print(f"  -> {verdict} (|IC| >= ~0.03 is the rough usefulness threshold)")
    hr = ev.get("hit_rate")
    print(f"Hit rate (sign match): {hr:.3f}" if hr is not None else "Hit rate: n/a")
    if ev.get("bucket_returns"):
        print("Mean forward return by signal bucket (low->high signal):")
        for b, r in sorted(ev["bucket_returns"].items()):
            print(f"  bucket {b}: {r:+.4%}")

    # 2) Equity-curve backtest (secondary -- easy to overfit).
    engine = BacktestEngine(initial_capital=100_000, commission_rate=0.001)
    strat = make_signal_strategy(buy_threshold=args.buy, sell_threshold=args.sell)
    results = engine.run_backtest(df, strat)
    print(f"\n=== Backtest (long/flat) ===")
    if results:
        print(f"Total return:   {results.get('total_return', 0):+.2%}")
        print(f"Sharpe:         {results.get('sharpe_ratio', 0):.2f}")
        print(f"Max drawdown:   {results.get('max_drawdown', 0):.2%}")
        print(f"Trades:         {results.get('total_trades', 0)}")
    else:
        print("No trades generated.")
    # Buy-and-hold benchmark for honest comparison.
    bh = df["close"].iloc[-1] / df["close"].iloc[0] - 1.0
    print(f"Buy & hold:     {bh:+.2%}  <-- beat this, or the signal added nothing")


if __name__ == "__main__":
    main()
