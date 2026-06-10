"""Composite trading-signal demo (Alpha Vantage).

Fetches REAL signal components -- RSI, MACD, and news sentiment -- from Alpha
Vantage and blends them into a single directional score per symbol.

Setup
-----
Get a free Alpha Vantage key: https://www.alphavantage.co/support/#api-key

    export ALPHAVANTAGE_API_KEY=your_key
    python examples/signals_demo.py AAPL MSFT
    python examples/signals_demo.py BTC --interval daily   # crypto also works

Free-tier note: the free key allows ~25 requests/day and ~5/minute. Each
composite signal uses 3 requests, so the free tier covers ~8 symbols/day.
Upgrade for production use.

Signals are informational, not a profit guarantee.
"""

import argparse
import logging
import os
import sys

from data_service.signals.alpha_vantage_signals import AlphaVantageSignalProvider

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main():
    parser = argparse.ArgumentParser(description="Composite signal demo")
    parser.add_argument("symbols", nargs="+", help="Symbols, e.g. AAPL MSFT BTC")
    parser.add_argument("--interval", default="daily", help="Indicator interval")
    args = parser.parse_args()

    if not os.environ.get("ALPHAVANTAGE_API_KEY"):
        sys.exit("Set ALPHAVANTAGE_API_KEY (free: https://www.alphavantage.co/support/#api-key)")

    provider = AlphaVantageSignalProvider(interval=args.interval)

    print(f"\n{'SYMBOL':<10}{'SCORE':>8}  {'LABEL':<18}COMPONENTS")
    print("-" * 70)
    for symbol in args.symbols:
        sig = provider.composite_signal(symbol)
        comps = ", ".join(
            f"{k}={'' if v is None else round(v, 2)}" for k, v in sig.components.items()
        )
        print(f"{symbol:<10}{sig.score:>8.3f}  {sig.label:<18}{comps}")


if __name__ == "__main__":
    main()
