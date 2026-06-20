"""Test whether EODHD news-sentiment adds predictive value over price signals.

Pulls EODHD daily news-sentiment (differentiated, history-bearing) + Yahoo
prices, builds a month-start mean-sentiment signal per symbol, and runs the
provider-agnostic orthogonality test: IC of sentiment vs the technical signal
vs the two combined, plus their correlation.

Setup
-----
    export EODHD_API_KEY=your_key       # free key: https://eodhd.com
    python examples/eodhd_sentiment_demo.py AAPL MSFT NVDA AMZN JPM XOM ...
"""

import argparse
import os
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

from data_service.fetchers.yahoo_fetcher import YahooFetcher
from data_service.fetchers.eodhd_fetcher import EODHDFetcher
from data_service.signals.analyst_signals import pooled_horizon_ic

DEFAULT = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "JPM", "XOM", "KO", "WMT"]


def main():
    p = argparse.ArgumentParser(description="EODHD sentiment orthogonality test")
    p.add_argument("symbols", nargs="*", default=DEFAULT)
    p.add_argument("--years", type=int, default=5)
    args = p.parse_args()
    symbols = args.symbols or DEFAULT

    if not os.environ.get("EODHD_API_KEY"):
        raise SystemExit("Set EODHD_API_KEY (free key: https://eodhd.com)")

    eod = EODHDFetcher()
    yf = YahooFetcher()
    end = datetime.now()
    start = end - timedelta(days=365 * args.years)
    fr, to = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    price_data, signal_data = {}, {}
    for s in symbols:
        try:
            sent = eod.get_sentiment(s, fr, to)
            df = yf.fetch_historical_data(s, start_time=start, end_time=end, interval="1d")
            if not sent.empty and not df.empty:
                signal_data[s] = sent["normalized"]  # daily sentiment series
                price_data[s] = df
                print(f"  {s}: {len(sent)} daily sentiment points")
        except Exception as e:
            print(f"skip {s}: {e}")

    print(f"\nLoaded sentiment + price for {len(signal_data)} symbols")
    # Sentiment is a short-horizon signal -> use the multi-horizon daily test.
    res = pooled_horizon_ic(price_data, signal_data, horizons=(1, 5, 21))
    print("\n=== Does EODHD sentiment add value over price? ===")
    print(f"  pooled daily observations: {res['n']}")
    print(f"  corr(sentiment, technical): {res['signal_correlation']:+.3f}  (near 0 => orthogonal)")
    print(f"  {'horizon':>7} {'IC_sent':>9} {'IC_tech':>9} {'IC_combo':>9}")
    for h, m in res["horizons"].items():
        print(f"  {h:>6}d {m['ic_signal']:>+9.4f} {m['ic_technical']:>+9.4f} "
              f"{m['ic_combined']:>+9.4f}")


if __name__ == "__main__":
    main()
