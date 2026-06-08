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

## Multi-symbol & walk-forward validation (don't trust one backtest)

`signal_sweep` stress-tests a signal across a basket and across time, and checks
whether it is actually monetizable:

- **`ic_sweep`** — time-series IC per symbol across multiple horizons + aggregate.
- **`walk_forward_ic`** — IC across contiguous time folds (regime stability).
- **`cross_sectional_ls`** — market-neutral long/short backtest (long top-signal
  names, short bottom) vs a hold-the-basket benchmark.

```bash
python examples/signal_sweep_demo.py            # default 16-name basket
```

### Findings on the current composite (16-name basket, ~8y daily)

| Test | Result | Read |
|------|--------|------|
| Aggregate time-series IC | **+0.02 to +0.05**, 83–92% of symbols positive | Weak but real predictive value |
| Where it works | Strong on indices/mean-reverters (SPY ~0.13, WMT, KO); weak/negative on momentum tech (NVDA, META) | It's a **mean-reversion** signal |
| Walk-forward (SPY) | All 5 folds positive (0.07–0.28) | Stable over time |
| **Cross-sectional L/S** | **−8% ann, Sharpe −0.42** vs **+20%, Sharpe ~1.0** hold-basket | **Not monetizable** as a selector |

**The key lesson (baked into the tooling):** a positive *time-series* IC did
**not** become a tradeable edge. Cross-sectionally the signal longs recent
losers / shorts recent winners — an anti-momentum bet that underperformed badly.
Always run `cross_sectional_ls` and compare to the hold-basket benchmark before
believing a signal makes money. This is why the module ships the benchmark in
the same call.

### Iteration 2: mean-reversion long/flat on the strongest names

The IC sweep showed the signal is strongest and most stable on indices, so we
built a mark-to-market long/flat mean-reversion backtest (`long_flat_backtest`,
with real Sharpe / max-drawdown, unlike the avg-cost BacktestEngine) and tested
it where the signal looked best:

| Asset | Best strategy | Buy & hold | Read |
|-------|---------------|-----------|------|
| SPY (15y) | ann +6.4%, **Sharpe 0.66**, maxDD −17% (14% time in market) | ann +14.5%, **Sharpe 0.87**, maxDD −34% | B&H wins risk-adjusted |
| QQQ (15y) | ann +9.3%, **Sharpe 0.72**, maxDD −20% (24% time in market) | ann +19.7%, **Sharpe 0.97**, maxDD −35% | B&H wins risk-adjusted |

The smaller drawdowns come only from sitting in cash most of the time, not from
skill — on Sharpe (which controls for that) the signal **loses to buy-and-hold**
even on its best assets.

### Iteration 3: differentiated (non-price) data — analyst ratings

Price-only signals showed no edge, so we added a *differentiated* data provider
(`FMPFetcher`) and an analyst-rating signal (`consensus_score`, `revision_signal`),
plus `evaluate_orthogonality` — which tests whether the analyst signal adds value
*over* the technical signal (IC of each vs combined, plus their correlation).

```bash
export FMP_API_KEY=your_key
python examples/analyst_signal_demo.py AAPL MSFT NVDA JPM KO WMT
```

**Honest constraint found:** on FMP's **free tier**, analyst history is only ~10
monthly snapshots and insider/congressional/news data are paid-gated. That is
enough to wire up and unit-test the pipeline, but **too shallow to validate**
predictive value — `evaluate_orthogonality` correctly reports `underpowered`
rather than printing a meaningless IC from a handful of points. The integration
is ready to produce a real verdict the moment a paid key (or deeper history)
is supplied. Insider and congressional-trade signals are stubbed for the same
reason: real, plausibly-differentiated, but gated behind a paid plan here.

### Differentiated-data providers: all gated behind paid keys

Surveying alternatives (per the FMP-alternatives list and the live data MCPs
available here) for a *free, history-bearing, differentiated* feed came up empty:

| Source | Differentiated data | Status here |
|--------|--------------------|-------------|
| FMP free | analyst rating counts | ~10 monthly snapshots only; insider/congress/news paid |
| LunarCrush | social-sentiment **time series** | paid — no active subscription, time series locked |
| EODHD / FinancialData.Net | sentiment, insider, deep history | need an API key (not configured) |
| Alpha Vantage | NEWS_SENTIMENT, fundamentals | needs key; free tier 25 req/day |

So the harness is now **provider-agnostic**: `evaluate_signal_orthogonality`
takes `{symbol: dated_signal_series}` from *any* source and runs the same
IC-vs-technical / combined-IC / correlation test. The moment a key for any
provider above is supplied, wiring a fetcher + one signal series produces a real
verdict — no changes to the test harness needed.

### Conclusion after three iterations

Rigorous, repeatable testing finds **no simple price-only signal that beats
buy-and-hold** here — matching the prediction-market research — and the one free
*differentiated* source (analyst ratings) is too shallow to validate. The honest
takeaway: a real edge needs data we don't have for free (deep history, paid
alt-data) — and even then it must clear this bar. The durable deliverable is the
**measurement framework** — IC, walk-forward stability, cross-sectional L/S,
risk-adjusted long/flat, and now an orthogonality test for new data sources —
that makes "does this actually make money?" answerable in seconds and stops any
signal from looking good in isolation.

## Testing

```bash
python -m pytest tests/test_signals.py tests/test_signal_backtest.py \
  tests/test_signal_sweep.py tests/test_analyst_signals.py -v
```
