"""Kalshi 15-minute market arbitrage demo.

Scrapes Kalshi's open 15-minute markets and looks for *locked* arbitrage --
the only "essentially guaranteed" profit on a binary market: when one YES and
one NO contract can be bought for a combined cost below $1.00 (after fees),
the $1.00 settlement guarantees a profit regardless of outcome.

By default this runs in DRY-RUN (paper) mode and places no real orders.

Usage
-----
Scan once, paper mode (no credentials needed)::

    python examples/kalshi_arbitrage_demo.py

Restrict to specific 15-min series::

    python examples/kalshi_arbitrage_demo.py --series KXBTCD KXETHD

Go LIVE (real money -- requires Kalshi API credentials)::

    export KALSHI_API_KEY_ID=...                 # API key id
    export KALSHI_PRIVATE_KEY="$(cat key.pem)"   # RSA private key PEM
    python examples/kalshi_arbitrage_demo.py --live --max-spend 25

Reality check: true arbitrage is rare, small, short-lived and competitive.
Quoted prices are not guaranteed fills. Live trading risks real money. This is
not financial advice.
"""

import argparse
import logging
import os

from data_service.fetchers.kalshi_fetcher import (
    KALSHI_API_BASE,
    KALSHI_DEMO_API_BASE,
    KalshiFetcher,
)
from data_service.strategies.kalshi_arbitrage import (
    ArbConfig,
    KalshiArbitrageTrader,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)


def parse_args():
    p = argparse.ArgumentParser(description="Kalshi 15-min arbitrage scanner")
    p.add_argument("--series", nargs="*", help="Series tickers to restrict the scan to")
    p.add_argument("--live", action="store_true", help="Place REAL orders (default: dry-run)")
    p.add_argument("--demo", action="store_true", help="Use Kalshi demo/sandbox API")
    p.add_argument("--min-edge", type=float, default=0.01, help="Min net edge per pair ($)")
    p.add_argument("--max-contracts", type=int, default=10, help="Max contract pairs per opp")
    p.add_argument("--max-spend", type=float, default=50.0, help="Max total spend per scan ($)")
    p.add_argument("--poll", type=float, default=5.0, help="Seconds between scans")
    p.add_argument("--iterations", type=int, default=1, help="Number of scans (0 = forever)")
    return p.parse_args()


def main():
    args = parse_args()

    api_base = KALSHI_DEMO_API_BASE if args.demo else KALSHI_API_BASE
    api_key_id = os.environ.get("KALSHI_API_KEY_ID")
    private_key = os.environ.get("KALSHI_PRIVATE_KEY")

    if args.live and not (api_key_id and private_key):
        raise SystemExit(
            "Live mode requires KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY env vars."
        )

    fetcher = KalshiFetcher(
        api_base=api_base, api_key_id=api_key_id, private_key_pem=private_key
    )
    config = ArbConfig(
        min_edge=args.min_edge,
        max_contracts=args.max_contracts,
        max_total_spend=args.max_spend,
        dry_run=not args.live,
    )
    trader = KalshiArbitrageTrader(fetcher, config)

    def report(opp):
        print(
            f"  ARB {opp.ticker}: YES {opp.yes_ask} + NO {opp.no_ask} = "
            f"{opp.cost_per_pair} | net {opp.net_edge_per_pair}/pair x "
            f"{opp.contracts} = ${opp.total_profit} "
            f"(closes in {opp.minutes_to_close} min)"
        )

    iterations = None if args.iterations == 0 else args.iterations
    mode = "LIVE (real money)" if args.live else "DRY-RUN (paper)"
    print(f"Scanning Kalshi 15-min markets in {mode} mode...\n")

    results = trader.run(
        series_tickers=args.series,
        poll_seconds=args.poll,
        iterations=iterations,
        on_opportunity=report,
    )

    print(f"\nDone. {len(results)} opportunities acted on.")
    if results:
        total = sum(r.get("expected_profit", 0) for r in results)
        print(f"Total expected profit: ${round(total, 2)}")


if __name__ == "__main__":
    main()
