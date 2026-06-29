# QuantMuse — Usage Guide

A practical, **verified** guide to every feature in this repository: what the
system contains, how to install and configure it, runnable examples for each
module, how to launch the UIs, and an honest catalog of the bugs/gaps you will
hit (with concrete fixes).

> Status legend used throughout: ✅ works as shipped · ⚠️ works only after a
> small fix or extra dependency · ❌ does not import / not implemented.

---

## 1. What this project is

Two cooperating layers:

| Layer | Location | Purpose |
|-------|----------|---------|
| Python data/quant service | `data_service/` | Data fetching, processing, factor analysis, strategy framework, backtesting, AI/LLM/NLP, ML, storage, visualization, web & dashboard UIs |
| C++ execution engine | `backend/` | Order executor, risk manager, strategy, data loader (CMake build, standalone) |

The Python package is named `data_service` (see `setup.py`). The two layers are
independent today — there is no binding between the C++ engine and the Python
package.

### Module map (`data_service/`)

| Subpackage | Public classes | Status |
|-----------|----------------|--------|
| `fetchers` | `BinanceFetcher`, `AlphaVantageFetcher`, `YahooFetcher` | ✅ |
| `processors` | `DataProcessor` (returns `MarketAnalysis`) | ✅ |
| `factors` | `FactorCalculator`, `FactorScreener`, `StockSelector`, `FactorBacktest`, `FactorOptimizer` | ✅ |
| `strategies` | `StrategyBase`, `StrategyRegistry`, `StrategyRunner`, `StrategyOptimizer`, 5 builtins | ✅ |
| `backtest` | `BacktestEngine`, `PerformanceAnalyzer` | ✅ |
| `ai` | `LLMIntegration`, `NLPProcessor`, `SentimentAnalyzer`, `NewsProcessor`, `SocialMediaMonitor`, `SentimentFactorCalculator`, `LangChainAgent` | ✅ (needs `ai` extra for full features) |
| `ml` | `MLModelManager`, `PredictionModel`, `ClassificationModel`, `FeatureEngineer` | ✅ (needs scikit-learn) |
| `storage` | `DatabaseManager`, `FileStorage`, `CacheManager` | ✅ |
| `visualization` | `PlotlyChartGenerator` | ✅ (needs plotly) |
| `web` | `APIServer` (FastAPI), `WebDashboard`, `StrategyUI` | ⚠️ needs `web`+`visualization` extras |
| `dashboard` | `TradingDashboard` (Streamlit), `ChartGenerator`, `DashboardWidgets` | ⚠️ needs `streamlit` |
| `realtime` | `WebSocketClient`, `RealTimeDataFeed` | ✅ (needs `realtime` extra to run) |
| `vector_db` | `VectorStore`, `EmbeddingManager`, `DocumentProcessor`, `SearchEngine` | ✅ |
| `api` | `APIManager`, `APIDocumentation`, `APITesting`, `APIGateway` | ✅ |
| `utils` | `DataFetchError`, `ProcessingError`, `ValidationError`, `setup_logger` | ✅ |

> The import bugs originally cataloged in §9 of this guide have been **fixed**
> (see §9 for the record of what changed). Every subpackage above now imports
> cleanly once its dependencies are installed.

---

## 2. Installation

Python 3.11 recommended.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .                 # base runtime deps
# Optional extras (declared in setup.py):
pip install -e ".[ai]"           # openai, langchain, transformers, torch, spacy, nltk, scikit-learn, ...
pip install -e ".[visualization]"# matplotlib, seaborn, plotly, streamlit, kaleido
pip install -e ".[web]"          # fastapi, uvicorn[standard], jinja2, aiofiles
pip install -e ".[realtime]"     # websockets, aiohttp, asyncio-mqtt, redis
pip install -e ".[test]"         # pytest, pytest-cov, pytest-asyncio
```

`matplotlib`, `seaborn`, and `scipy` are declared in the base `install_requires`
(factors/backtest/strategies import them at module load).

A "make everything importable" install:

```bash
pip install -e ".[ai,visualization,web,realtime,test]"
```

---

## 3. Configuration

Copy the template and fill in keys you have:

```bash
cp config.example.json config.json
```

`config.json` covers `database` (sqlite/postgres), `redis`, `api_keys`
(`binance`, `openai`, `alpha_vantage`), `trading`, `risk_management`, `data`,
and `logging`. Everything that doesn't need an external key (Yahoo data,
processing, factors, backtesting on supplied data, ML, plotting, sqlite storage,
vector store) works without filling anything in.

---

## 4. The 60-second quick start (no API keys)

`DataProcessor` is the simplest end-to-end feature:

```python
import pandas as pd, numpy as np
from data_service.processors import DataProcessor

# Any OHLCV DataFrame indexed by timestamp with columns open/high/low/close/volume
idx = pd.date_range("2024-01-01", periods=300, freq="D")
close = 100 + np.cumsum(np.random.default_rng(0).normal(0, 1, 300))
df = pd.DataFrame({"open": close, "high": close+1, "low": close-1,
                   "close": close, "volume": 1000}, index=idx)

analysis = DataProcessor().process_market_data(df)   # -> MarketAnalysis
print(analysis.indicators.keys())   # MA5/MA10/MA20, MACD/Signal, RSI, BB_*
print(analysis.statistics)          # daily_return, volatility, current_price, ...
print(analysis.signals)             # golden_cross, rsi overbought/oversold, macd_*
```

`process_market_data` returns a `MarketAnalysis` dataclass with three dicts:
`indicators` (each a `pd.Series`), `statistics` (floats), and `signals` (bools).
Invalid input (empty frame, missing OHLCV columns) raises
`data_service.utils.exceptions.ProcessingError`.

---

## 5. Data fetching (`data_service.fetchers`)

### Yahoo Finance — ✅ no key required

```python
from data_service.fetchers import YahooFetcher
from datetime import datetime, timedelta

yf = YahooFetcher()
df = yf.fetch_historical_data(
    "AAPL",
    start_time=datetime.now() - timedelta(days=365),
    end_time=datetime.now(),
    interval="1d",                 # '1d' | '1wk' | '1mo'
)                                  # OHLCV columns lower-cased
info  = yf.get_company_info("AAPL")     # name, sector, market_cap, pe_ratio, beta, ...
fins  = yf.get_financial_data("AAPL")   # balance_sheet / income_statement / cash_flow
```

> `fetch_historical_data` takes `start_time` / `end_time` / `interval` — there is
> **no** `period=` argument.

### Binance — ✅ key optional for public endpoints

```python
from data_service.fetchers import BinanceFetcher
f = BinanceFetcher(api_key=None, api_secret=None)         # public endpoints need no key
klines = f.fetch_historical_data("BTCUSD", interval="1h", limit=500)
price  = f.get_current_price("BTCUSD")                    # float, latest trade price
book   = f.get_order_book("BTCUSD", limit=100)            # {'bids': [...], 'asks': [...]}
depth  = f.get_market_depth("BTCUSD", limit=5)            # alias of get_order_book
trades = f.get_recent_trades("BTCUSD", limit=100)
```

`start_websocket(symbol, callback)` / `stop_websocket(symbol)` stream 1-minute
klines; the implementation supports both modern `python-binance`
(`ThreadedWebsocketManager`) and the legacy `BinanceSocketManager` API.

### Alpha Vantage — ⚠️ requires a free key

```python
from data_service.fetchers.alpha_vantage_fetcher import AlphaVantageFetcher
av = AlphaVantageFetcher(api_key="YOUR_KEY")
df  = av.fetch_historical_data("AAPL")
ov  = av.get_company_overview("AAPL")
inc = av.get_income_statement("AAPL")      # also get_balance_sheet / get_cash_flow
```

---

## 6. Factor analysis (`data_service.factors`)

```python
from data_service.factors import (
    FactorCalculator, FactorScreener, StockSelector, FactorBacktest, FactorOptimizer
)
import pandas as pd

fc = FactorCalculator()
mom   = fc.calculate_price_momentum(prices, periods=[20, 60, 252])   # prices: pd.Series
vol   = fc.calculate_volatility_factors(prices)
tech  = fc.calculate_technical_factors(prices)
value = fc.calculate_value_factors({"pe": 15, "pb": 2, ...})         # dict of fundamentals

# Screening: build a screener, then screen a wide DataFrame of factors
screener = FactorScreener().create_momentum_screener(min_momentum=10.0)
results  = screener.screen_stocks(factor_df)        # factor_df: rows=symbols, cols=factors

# Stock selection into a portfolio
sel = StockSelector(max_positions=50).select_stocks(
    factor_df, price_df, selection_method="top_n", n=20, factor_name="momentum_60d"
)
print(sel.selected_stocks, sel.weights)

# Single/multi-factor backtests and weight optimization
bt  = FactorBacktest(lookback_period=252, holding_period=21)
res = bt.run_factor_backtest(factor_df, price_df, factor_name="momentum_60d")
opt = FactorOptimizer().optimize_factor_weights(factor_df, returns)
```

`FactorScreener` also offers `create_value_screener`, `create_quality_screener`,
`create_multi_factor_screener`, and `add_*_filter` helpers. `FactorBacktest`
provides `run_multi_factor_backtest`, `calculate_information_coefficient`,
`plot_factor_performance`, and `generate_performance_report`.

---

## 7. Strategy framework (`data_service.strategies`)

Strategies subclass `StrategyBase` and implement
`generate_signals(factor_data, price_data, **kwargs) -> StrategyResult`. Five
builtins ship: `MomentumStrategy`, `ValueStrategy`, `QualityGrowthStrategy`,
`MultiFactorStrategy`, `MeanReversionStrategy`.

```python
from data_service.strategies import StrategyRegistry, StrategyRunner
from data_service.strategies.builtin_strategies import register_builtin_strategies

register_builtin_strategies()                  # populates the global registry
runner = StrategyRunner()
result = runner.run_strategy(
    "MomentumStrategy", factor_data=factor_df, price_data=price_df,
    parameters={"top_n": 20, "min_momentum": 5.0},
)
print(result.selected_stocks, result.weights, result.performance_metrics)

# Combine several strategies
ensemble = runner.run_strategy_ensemble(
    ["MomentumStrategy", "ValueStrategy"], factor_df, price_df,
    ensemble_method="voting", ensemble_parameters={"vote_threshold": 0.5},
)
```

Register your own:

```python
from data_service.strategies import StrategyBase, StrategyResult, StrategyRegistry

class MyStrategy(StrategyBase):
    def __init__(self): super().__init__("MyStrategy", "demo")
    def generate_signals(self, factor_data, price_data, **kw) -> StrategyResult:
        ...   # return a StrategyResult(strategy_name, selected_stocks, weights, ...)

reg = StrategyRegistry()
reg.register_strategy(MyStrategy)              # or reg.register_instance(MyStrategy())
inst = reg.create_strategy("MyStrategy", {"top_n": 10})
```

`StrategyOptimizer` (`optimize_strategy`, `grid_search_optimization`) tunes
parameters. See `examples/extensible_strategy_demo.py` and
`examples/quantitative_strategies.py`.

> The strategy framework operates on **cross-sectional** `factor_data`/`price_data`
> (rows = symbols) and selects a basket of stocks. This is a different abstraction
> from the time-series `BacktestEngine` in §8 — they are not wired together.

---

## 8. Backtesting (`data_service.backtest`)

`BacktestEngine.run_backtest(data, strategy_func, strategy_params=None)`. The
strategy is a **callback** invoked once as `strategy_func(data, engine, **params)`;
inside it you iterate over `data` and call `engine.place_order(...)`.

```python
from data_service.backtest import BacktestEngine, PerformanceAnalyzer

def sma_crossover(data, engine, fast=5, slow=20):
    ma_fast = data["close"].rolling(fast).mean()
    ma_slow = data["close"].rolling(slow).mean()
    holding = False
    for ts, row in data.iterrows():
        if ma_fast.loc[ts] > ma_slow.loc[ts] and not holding:
            qty = (engine.current_capital * 0.95) / row["close"]
            if engine.place_order("SYM", "buy", qty, row["close"], ts): holding = True
        elif ma_fast.loc[ts] < ma_slow.loc[ts] and holding:
            pos = engine.get_current_positions().get("SYM")
            if pos and engine.place_order("SYM", "sell", pos.quantity, row["close"], ts):
                holding = False

engine = BacktestEngine(initial_capital=100_000, commission_rate=0.001)
results = engine.run_backtest(df, sma_crossover, {"fast": 5, "slow": 20})
# results: total_return, annualized_return, volatility, sharpe_ratio, max_drawdown,
#          win_rate, equity_curve (DataFrame), trades, final_positions

report = PerformanceAnalyzer().analyze_performance(results)
print(PerformanceAnalyzer().generate_report(report))
```

> README still shows `run_backtest(strategy, historical_data)` — that argument order
> is wrong. Use `run_backtest(data, strategy_func, params)`.

---

## 9. Known gaps & bugs — status: **fixed**

The bugs this section originally cataloged have been fixed in the codebase:

| # | Was | Fix applied |
|---|-----|-------------|
| 9.1 | `processors/__init__.py` imported nonexistent `ProcessedData` → package unimportable. | Imports/`__all__` now use the real class `MarketAnalysis`. |
| 9.2 | `api`/`vector_db` `__init__` did unguarded imports of files that don't exist → `ModuleNotFoundError`. | Trimmed to the shipped modules (`APIManager`; `VectorStore`). |
| 9.3 | `matplotlib`/`seaborn`/`scipy` imported at module load by factors/backtest/strategies but not in base deps. | Added to `install_requires` in `setup.py`. |
| 9.4 | `ml`, `realtime`, `visualization` advertised submodules that don't ship; names silently became `None`. | `__init__`/`__all__` trimmed to what ships. (The missing submodules remain unimplemented — roadmap items, not bugs.) |
| 9.5 | `BinanceFetcher.get_current_price()`/`get_market_depth()` called by README/`main.py`/examples but missing. | Both added (`get_symbol_ticker` wrapper; `get_order_book` alias). |
| 9.6 | `from binance.websockets import ...` fails on modern `python-binance` → `BinanceFetcher = None`. | Import now tries `ThreadedWebsocketManager` (≥1.0) with legacy fallback; `start_websocket` supports both APIs. |
| 9.7 | `YahooFetcher` not exported by `fetchers/__init__` → top-level guarded import killed **all three** fetchers. | Exported (guarded). |
| 9.8 | Top-level/`web` imports of nonexistent `Logger`/`TradingException` (the latter silently disabled **all** of `api_server`'s trading-module imports). | Top-level re-exports `setup_logger` + real exception classes; dead import removed from `api_server.py`. |
| 9.9 | `PerformanceAnalyzer` used pandas frequency aliases `'M'`/`'Y'`, removed in pandas 2.2+ → `analyze_performance` raised `ValueError`. | Changed to `'ME'`/`'YE'`. |
| 9.10 | `tests/test_binance_fetcher.py` patched `binance.client.Client`, not the name the fetcher holds — mocks never applied and tests hit the real Binance API. `DataProcessor` raised `ValueError` where tests expect `ProcessingError`. | Patch target corrected; `DataProcessor` validation now raises `ProcessingError`. |

**§20 roadmap progress** — the originally-missing submodules are being filled
in across phased PRs:

- ✅ `api.api_documentation` / `api_testing` / `api_gateway` — implemented (§16).
- ✅ `vector_db.embedding_manager` / `search_engine` / `document_processor` —
  implemented (§16).
- ✅ README backtest/strategy/LLM snippet drift — fixed (see README + §7/§8).
- ⏳ `ml.deep_learning` / `ensemble_models` / `model_evaluation` / `optimization`.
- ⏳ `realtime.tick_processor` / `market_data_stream`.
- ⏳ `visualization.matplotlib_charts` / `real_time_charts` / `dashboard_charts`.
- ⏳ C++ engine ↔ Python bindings.

---

## 10. AI / LLM / NLP (`data_service.ai`) — needs `.[ai]` extra

```python
from data_service.ai import LLMIntegration, NLPProcessor, SentimentAnalyzer

llm = LLMIntegration(provider="openai", api_key="sk-...", model="gpt-3.5-turbo")
#  or provider="local" to use a local HuggingFace model (no key)
insight = llm.analyze_market_data(market_df, symbols=["AAPL"])
answer  = llm.answer_trading_question("Is AAPL overbought?", context={...})

nlp = NLPProcessor(use_spacy=True, use_transformers=True)
processed = nlp.preprocess_text("Apple beats earnings, stock soars")
sent = nlp.analyze_sentiment_batch(["headline 1", "headline 2"])
market_sent = nlp.calculate_market_sentiment(sent)

sa = SentimentAnalyzer(openai_api_key="sk-...")     # key optional
sd = sa.analyze_text_sentiment("Great quarter for NVDA", symbol="NVDA")
```

`LangChainAgent(llm_integration, nlp_processor)` builds on top of these for
`generate_strategy_recommendation`, `analyze_market_intelligence`, and
`generate_automated_report`. See `examples/langchain_llm_demo.py`,
`examples/llm_nlp_complete_demo.py`, and `demo_llm_nlp_simple.py`.

---

## 11. Machine learning (`data_service.ml`) — needs scikit-learn (in `.[ai]`)

```python
from data_service.ml import MLModelManager, PredictionModel, FeatureEngineer

fe = FeatureEngineer()
feats = fe.engineer_features(ohlcv_df)         # or create_technical_indicators / _lag_features / etc.

mgr = MLModelManager()
mgr.add_model("rf", PredictionModel(model_type="random_forest"))
mgr.train_model("rf", X, y, validation_split=0.2)
preds = mgr.predict("rf", X_test)
best_name, best_result = mgr.get_best_model(metric="validation_score")
```

`ClassificationModel` mirrors `PredictionModel` with `predict_proba`. Models
support `save_model`/`load_model`. *(`model_evaluation`, `ensemble_models`,
`deep_learning`, `optimization` are roadmap items — see §9/§20.)*

---

## 12. Storage (`data_service.storage`) — ✅ sqlite needs no setup

```python
from data_service.storage import DatabaseManager, FileStorage, CacheManager

db = DatabaseManager(db_type="sqlite", db_path="trading_data.db")
db.save_market_data("AAPL", ohlcv_df)
hist = db.get_market_data("AAPL", start_date="2024-01-01")
db.save_trade({...}); db.save_signal({...}); db.save_performance({...})
db.close()
```

`db_type="postgres"` is also supported (configure host/credentials).
`CacheManager` wraps Redis (needs a running Redis); `FileStorage` persists
DataFrames/artifacts to disk.

---

## 13. Visualization (`data_service.visualization`) — needs `.[visualization]`

```python
from data_service.visualization import PlotlyChartGenerator
g = PlotlyChartGenerator()
fig = g.create_candlestick_chart(ohlcv_df, title="AAPL")
fig = g.create_technical_analysis_chart(ohlcv_df)      # also factor / portfolio / heatmap / 3d
g.export_chart(fig, "chart.html", format="html")       # or 'png' (needs kaleido)
```

(`MatplotlibChartGenerator`, `RealTimeChartManager`, `DashboardChartGenerator`
are roadmap items — see §9/§20.)

---

## 14. Real-time data (`data_service.realtime`) — needs `.[realtime]`

```python
from data_service.realtime import RealTimeDataFeed, WebSocketClient

feed = RealTimeDataFeed(exchanges=["binance"])
feed.add_tick_callback(lambda tick: print(tick))
feed.set_price_alert("BTCUSDT", alert_type="above", threshold=70000)
feed.add_alert_callback(lambda a: print("ALERT", a))
last = feed.get_latest_tick("BTCUSDT")
```

`WebSocketClient(exchange="binance")` is the lower-level client with
`add_message_handler` / `add_error_handler`. See `demo_charts_websocket.py`.
(`TickProcessor`, `MarketDataStream` are roadmap items — see §9/§20.)

---

## 15. Web API & dashboards

### FastAPI server (`data_service.web.APIServer`) — needs `.[web,visualization]`

```bash
python run_web_interface.py     # serves http://localhost:8000
# or: python run_web_simple.py
```

Routes (from `web/api_server.py`): `GET /`, `GET /api/health`,
`GET /api/system/status`, `GET /api/strategies`, `POST /api/backtest/run`,
`POST /api/factors/analyze`, `POST /api/ai/analyze`,
`GET /api/market/data/{symbol}`, `GET /api/portfolio/status`,
`GET /api/trades/recent`.

```python
from data_service.web import APIServer
APIServer(host="0.0.0.0", port=8000).run(debug=True)
```

### Streamlit dashboard (`data_service.dashboard.TradingDashboard`) — needs `streamlit`

```bash
python run_dashboard.py          # serves http://localhost:8501
```

---

## 16. Vector store & API manager

### Vector store + embeddings + search (`data_service.vector_db`)

`VectorStore` is a self-contained sqlite-backed vector store. Around it,
`EmbeddingManager` turns text into vectors, `DocumentProcessor` cleans/chunks/
embeds raw text into `VectorDocument`s, and `SearchEngine` adds plain-text
querying with optional reranking and metadata filters.

```python
from data_service.vector_db import (
    VectorStore, EmbeddingManager, DocumentProcessor, SearchEngine
)

store = VectorStore(db_path="vector_store.db")
# backend="auto" picks sentence-transformers > openai > a dependency-free
# hash backend (great for offline/tests). Force one with backend="hash".
em = EmbeddingManager(backend="auto")
dp = DocumentProcessor(em)
engine = SearchEngine(store, em)

# Ingest: clean -> chunk (word windows w/ overlap) -> embed -> store
dp.process_and_store(store, "Apple beats earnings; chip stocks rally...",
                     source="news", metadata={"ticker": "AAPL"},
                     collection="news")

# Query with plain text (embeds the query for you)
hits = engine.search("semiconductor rally", collection="news", top_k=5)
hybrid = engine.hybrid_search("semiconductor rally", collection="news")  # + lexical rerank
filtered = engine.search("rally", collection="news",
                         metadata_filter={"ticker": "AAPL"})
for doc, score in hits:
    print(score, doc.source, doc.content[:60])
```

`EmbeddingManager`: `generate_embedding(text)`, `batch_embed(texts)`, built-in
cache. `DocumentProcessor`: `clean_text`, `chunk_text(chunk_size, overlap)`,
`process(...)`, `process_and_store(...)`. `SearchEngine`: `search`, `rerank`,
`hybrid_search`.

### API manager + docs + testing + gateway (`data_service.api`)

`APIManager` is a generic HTTP client with caching, retry logic, rate limiting,
and per-endpoint performance metrics. `APIDocumentation` introspects registered
endpoints, `APITesting` runs test cases against them, and `APIGateway` adds a
request/response middleware layer in front of `make_request`.

```python
from data_service.api import (
    APIManager, APIEndpoint, APIDocumentation, APITesting, APITestCase, APIGateway
)

api = APIManager()
api.register_endpoint("quotes", APIEndpoint(
    name="quotes", url="https://example.com/quotes", method="GET",
    headers={}, params={"symbol": "AAPL"}, rate_limit=60))

# Auto-generate docs (Markdown or OpenAPI 3.0)
APIDocumentation(api).export("api_docs.md", format="markdown")

# Register and run endpoint tests
tester = APITesting(api)
tester.register_test(APITestCase("quotes-ok", "quotes", expected_status=200,
                                 validator=lambda r: "price" in r.data))
print(tester.generate_report())

# Route through middleware (auth/logging/param injection)
gw = APIGateway(api)
gw.add_middleware(lambda name, params: {**params, "token": "secret"})
resp = gw.route("quotes", {"symbol": "MSFT"})
```

---

## 17. C++ execution engine (`backend/`)

Standalone CMake project — `order_executor`, `risk_manager`, `strategy`,
`data_loader`, with tests under `backend/tests/`.

```bash
cd backend && mkdir -p build && cd build
cmake .. && make
ctest            # run C++ tests
```

---

## 18. Running the demos & examples

```bash
python examples/yahoo_example.py            # Yahoo fetch (no key)
python examples/factor_analysis_demo.py     # needs matplotlib+scipy
python examples/quantitative_strategies.py  # strategy framework
python examples/extensible_strategy_demo.py
python examples/ai_sentiment_analysis.py    # needs .[ai]
python examples/langchain_llm_demo.py       # needs .[ai] + OpenAI key
demo_charts_websocket.py / demo_llm_nlp_simple.py / test_nlp_effect.py
```

> `main.py` and `examples/fetch_public_data.py` use `get_current_price` /
> `get_market_depth` and the top-level imports — all functional since the §9
> fixes landed (network access to the exchanges still required, of course).

---

## 19. Testing

```bash
pip install -e ".[test]"
pytest tests/ -v        # test_binance_fetcher, test_data_processor,
                        # test_integration, test_llm_integration
```

C++: `cd backend/build && ctest` (see §17).

---

## 20. Roadmap (the fixes from §9 are applied)

All §9 fixes have landed; every subpackage imports cleanly and the test suite
passes (21 passed, 1 intentionally skipped). What remains is net-new feature
work, in rough value order:

1. Implement the advertised-but-missing submodules listed at the end of §9
   (deep learning / ensemble ML, tick processing, matplotlib & real-time charts,
   API gateway/docs/testing, embedding manager & search engine).
2. Update the README code snippets to the real signatures (notably
   `run_backtest(data, strategy_func, params)`).
3. Wire the C++ engine to the Python package (currently independent).
