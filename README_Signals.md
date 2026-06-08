# Trading Signals Module

Real, composite directional signals from a legitimate market-data API, blended
into a single score per asset. Built to be **provider-pluggable**.

## Why not ZenBot Scanner?

The original request was to integrate [zenbotscanner.com](https://www.zenbotscanner.com/)
for "better signals." After investigating, that wasn't viable:

- **No public/developer API.** Its only integrations are *outbound* (launching
  tickers into TradingView/ThinkorSwim/IBKR charts). Pulling its signals would
  require scraping the web app — fragile and against its terms.
- **US equities only.** No crypto, no Kalshi/prediction markets, so it doesn't
  serve the markets the rest of this project targets.

Instead we integrated a **real signal API with documented developer access.**

## Provider chosen: Alpha Vantage

| Candidate | Verdict |
|-----------|---------|
| **Alpha Vantage** ✅ | 50+ technical indicators **+ News & Sentiment** on the free tier; covers stocks **and** crypto; already a project dependency. |
| Finnhub | Generous free tier, but technical-indicator/signal endpoints are **premium-gated**. |
| FMP / LunarCrush | Real APIs, but require **paid plans** (verified live — both returned "subscription required"). |

Docs: https://www.alphavantage.co/documentation/ · Free key: https://www.alphavantage.co/support/#api-key

## What it does

`AlphaVantageSignalProvider.composite_signal(symbol)` fetches three real
components and blends them into a score in `[-1, 1]`:

| Component | Endpoint | Mapping to score |
|-----------|----------|------------------|
| RSI | `RSI` | RSI 30→+1 (oversold/bullish), 50→0, 70→−1 (overbought/bearish) |
| MACD | `MACD` | `(MACD − signal)` normalized by magnitude → sign = direction |
| News sentiment | `NEWS_SENTIMENT` | average ticker sentiment score (already ~[-1,1]) |

Default weights: RSI 0.35, MACD 0.30, sentiment 0.35. Components that fail or
are unavailable are skipped (not fatal), and the composite re-normalizes over
whatever is available.

Score → label: `BULLISH ≥ 0.35`, `SOMEWHAT_BULLISH ≥ 0.15`, `NEUTRAL`,
`SOMEWHAT_BEARISH ≤ −0.15`, `BEARISH ≤ −0.35`.

## Usage

```bash
export ALPHAVANTAGE_API_KEY=your_key
python examples/signals_demo.py AAPL MSFT NVDA
```

```python
from data_service.signals import AlphaVantageSignalProvider

provider = AlphaVantageSignalProvider()          # reads ALPHAVANTAGE_API_KEY
sig = provider.composite_signal("AAPL")
print(sig.score, sig.label, sig.components, sig.rationale)
```

## Adding another provider

Subclass `SignalProvider` and implement `rsi_score`, `macd_score`,
`sentiment_score` (each returns a float in `[-1, 1]` or `None`). The base class
handles blending, error isolation, and labeling. So a `FinnhubSignalProvider`
or `FMPSignalProvider` is a drop-in once you have a paid key.

## Honest caveats

- **Free tier is limited:** ~25 requests/day, ~5/min. A composite signal = 3
  requests, so ~8 symbols/day on the free key. Production needs a paid key.
- **Free tier is end-of-day**, not real-time — fine for daily signals, not for
  intraday/fast markets.
- **Signals are informational, not a profit guarantee.** A composite score is
  one input; it does not predict outcomes and will be wrong regularly. Do not
  wire it directly to live order execution without your own validation and risk
  controls.

## Validating a signal (does it actually predict anything?)

A signal is only worth trading if it predicts forward returns. `signal_backtest`
connects the signals to the repo's `BacktestEngine` **and** measures predictive
value directly, which is the honest test (a single equity curve is easy to
overfit). The technical components (RSI, MACD) are computed locally from price
history, so this needs no API key and is fully reproducible.

```bash
pip install yfinance
python examples/signal_backtest_demo.py AAPL --years 5 --horizon 5
```

It reports:
- **Information Coefficient (IC)** — Spearman rank correlation of the signal at
  bar `t` vs the return from `t` to `t+horizon`. `|IC| ≳ 0.03` is the rough line
  where a signal is plausibly useful; near 0 means no edge.
- **Hit rate** — fraction of non-neutral signals whose sign matched the move.
- **Forward return by signal bucket** — monotonic increase = the signal orders
  returns correctly.
- A **long/flat backtest** plus a **buy-and-hold benchmark** — beat buy-and-hold
  or the signal added nothing.

```python
from data_service.signals import evaluate_predictive_value, make_signal_strategy
from data_service.backtest import BacktestEngine

ev = evaluate_predictive_value(price_df, horizon=5)   # {'ic':..., 'hit_rate':..., ...}
engine = BacktestEngine()
results = engine.run_backtest(price_df, make_signal_strategy(buy_threshold=0.15))
```

**Example result (AAPL, 5y daily):** IC ≈ +0.06 with monotonically increasing
bucket returns — a *weak* real edge — yet the long/flat strategy returned ~+55%
vs ~+148% buy-and-hold. Lesson: a small positive IC does **not** mean a tradeable
edge; sitting in cash during a strong uptrend cost more than the signal earned.
Always compare against buy-and-hold before trusting a signal.

## Testing

```bash
python -m pytest tests/test_signals.py tests/test_signal_backtest.py -v
```
