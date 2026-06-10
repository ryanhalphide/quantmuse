"""Multi-symbol IC sweep, walk-forward stability, and cross-sectional L/S.

Rigorously tests whether the composite signal predicts returns across a basket
and across time -- and whether it is actually monetizable as a market-neutral
long/short, versus just holding the basket.

Usage
-----
    python examples/signal_sweep_demo.py                 # default basket
    python examples/signal_sweep_demo.py AAPL MSFT SPY QQQ KO WMT --years 8
"""

import argparse
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

from data_service.fetchers.yahoo_fetcher import YahooFetcher
from data_service.signals.signal_sweep import (
    ic_sweep,
    walk_forward_ic,
    cross_sectional_ls,
)

DEFAULT_BASKET = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "JPM", "XOM",
    "SPY", "QQQ", "KO", "WMT", "PG", "JNJ", "HD", "BAC",
]


def main():
    p = argparse.ArgumentParser(description="Signal sweep")
    p.add_argument("symbols", nargs="*", default=DEFAULT_BASKET, help="Universe")
    p.add_argument("--years", type=int, default=8)
    p.add_argument("--quantile", type=float, default=0.3)
    args = p.parse_args()
    symbols = args.symbols or DEFAULT_BASKET

    yf = YahooFetcher()
    end = datetime.now()
    start = end - timedelta(days=365 * args.years)
    data = {}
    for s in symbols:
        try:
            df = yf.fetch_historical_data(s, start_time=start, end_time=end, interval="1d")
            if not df.empty:
                data[s] = df
        except Exception:
            pass
    print(f"Loaded {len(data)} symbols over ~{args.years}y\n")

    res = ic_sweep(data)
    print("=== Time-series IC per symbol (composite RSI+MACD) ===")
    print(res["per_symbol"].round(3))
    print("\n=== Aggregate IC ===")
    for h, a in res["aggregate"].items():
        print(f"  h={h:>2}: mean={a['mean_ic']:+.4f} median={a['median_ic']:+.4f} "
              f"frac_pos={a['frac_positive']:.2f} (n={a['n_symbols']})")

    print("\n=== Cross-sectional long/short (is it monetizable?) ===")
    for h in [1, 5, 10]:
        r = cross_sectional_ls(data, horizon=h, quantile=args.quantile)
        if r.get("n_days"):
            print(f"  h={h:>2}: L/S ann={r['ls_ann_return']:+.2%} sharpe={r['ls_sharpe']:.2f} "
                  f"hit={r['ls_hit_rate']:.2f} | hold-basket ann={r['benchmark_ann_return']:+.2%} "
                  f"sharpe={r['benchmark_sharpe']:.2f}")
    print("\nReminder: a positive time-series IC does NOT imply a tradeable edge. "
          "If L/S Sharpe <= the hold-basket Sharpe, the signal adds nothing.")


if __name__ == "__main__":
    main()
