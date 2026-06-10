"""Test whether analyst-rating data adds predictive value over price signals.

Pulls FMP analyst rating history (differentiated, non-price data) and Yahoo
prices, then runs evaluate_orthogonality: IC of the analyst signal vs the
technical signal vs the two combined, plus their correlation.

Setup
-----
    export FMP_API_KEY=your_key      # https://site.financialmodelingprep.com/developer/docs
    python examples/analyst_signal_demo.py AAPL MSFT NVDA JPM ...

Free-tier caveat: FMP's free plan returns only a short window of analyst
history (~10 monthly snapshots) and gates insider/congressional/news data. That
is enough to exercise the pipeline but NOT to validate predictive value -- the
harness will report 'underpowered' until you supply deeper history (paid key).
"""

import argparse
import os
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

from data_service.fetchers.yahoo_fetcher import YahooFetcher
from data_service.fetchers.fmp_fetcher import FMPFetcher
from data_service.signals.analyst_signals import (
    consensus_score,
    revision_signal,
    evaluate_orthogonality,
)

DEFAULT = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "JPM", "XOM", "KO", "WMT"]


def main():
    p = argparse.ArgumentParser(description="Analyst signal orthogonality test")
    p.add_argument("symbols", nargs="*", default=DEFAULT)
    p.add_argument("--limit", type=int, default=10, help="Analyst history depth (months)")
    args = p.parse_args()
    symbols = args.symbols or DEFAULT

    if not os.environ.get("FMP_API_KEY"):
        raise SystemExit("Set FMP_API_KEY (https://site.financialmodelingprep.com/developer/docs)")

    fmp = FMPFetcher()
    yf = YahooFetcher()
    end = datetime.now()
    start = end - timedelta(days=365 * 12)

    price_data, analyst_data = {}, {}
    for s in symbols:
        try:
            grades = fmp.get_analyst_grades_history(s, limit=args.limit)
            df = yf.fetch_historical_data(s, start_time=start, end_time=end, interval="1d")
            if not grades.empty and not df.empty:
                analyst_data[s] = grades
                price_data[s] = df
        except Exception as e:
            print(f"skip {s}: {e}")

    print(f"\nLoaded analyst + price data for {len(analyst_data)} symbols")
    for s, g in list(analyst_data.items())[:3]:
        cs = consensus_score(g)
        rv = revision_signal(g)
        print(f"  {s}: latest consensus={cs.iloc[-1]:+.2f}  latest revision={rv.iloc[-1]:+.2f}")

    res = evaluate_orthogonality(price_data, analyst_data, use_revision=True)
    print("\n=== Orthogonality: does analyst data add value over price? ===")
    if res.get("note"):
        print(f"  {res['note']}")
    else:
        print(f"  pooled observations: {res['n']}")
        print(f"  IC analyst:   {res['ic_analyst']:+.4f}")
        print(f"  IC technical: {res['ic_technical']:+.4f}")
        print(f"  IC combined:  {res['ic_combined']:+.4f}  "
              f"(> both standalone => additive value)")
        print(f"  signal correlation: {res['signal_correlation']:+.3f}  "
              f"(near 0 => orthogonal)")


if __name__ == "__main__":
    main()
