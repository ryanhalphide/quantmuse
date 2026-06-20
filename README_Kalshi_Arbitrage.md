# Kalshi 15-Minute Market Scraper & Arbitrage Trader

Scrapes Kalshi's short-duration ("15 minute") binary markets and detects
**locked arbitrage** — the only "essentially guaranteed" profit available on a
binary market — with an optional, safety-gated auto-trader.

## The honest truth about "guaranteed profit"

There is no guaranteed profit in trading, with **one** narrow exception. On a
Kalshi binary market, one YES and one NO contract together settle to exactly
**$1.00** regardless of the outcome. So if you can buy one of each for a
combined cost **below $1.00 after fees**, you lock in the difference no matter
what happens. That is real, risk-free arbitrage.

Everything else — "predict the 15-minute move and profit" — is a directional
bet with real risk of loss.

**Caveats that make even true arbitrage hard:**
- It is rare and usually tiny (a cent or two per contract).
- It is short-lived and competitive (often gone in milliseconds).
- Quoted best prices are **not** guaranteed fills; books can be thin.
- If one leg fills and the other doesn't, you hold an *unhedged*, risky position.
- Fees can erase the edge.

This tool is a research/execution aid, **not financial advice**.

## Components

| File | Purpose |
|------|---------|
| `data_service/fetchers/kalshi_fetcher.py` | Scrapes markets/orderbooks via the public Kalshi Trade API v2 (with 429 backoff + paging). Also signs authenticated trading requests. |
| `data_service/strategies/kalshi_arbitrage.py` | Detects locked YES+NO arbitrage, sizes it against a fee model + capital limits, and executes (dry-run by default). |
| `examples/kalshi_arbitrage_demo.py` | CLI demo / runner. |
| `tests/test_kalshi_arbitrage.py` | Unit tests for parsing, detection, and execution gating. |

## Quick start (paper / dry-run — no account needed)

```bash
pip install requests pandas
PYTHONPATH=. python examples/kalshi_arbitrage_demo.py --iterations 1
```

Restrict to specific 15-minute series (lighter on rate limits):

```bash
PYTHONPATH=. python examples/kalshi_arbitrage_demo.py --series KXBTCD KXETHD --iterations 1
```

Programmatic use:

```python
from data_service.fetchers.kalshi_fetcher import KalshiFetcher
from data_service.strategies.kalshi_arbitrage import ArbConfig, KalshiArbitrageTrader

fetcher = KalshiFetcher()                      # public market data, no auth
markets = fetcher.get_15min_markets()          # DataFrame of markets closing <=15 min
trader = KalshiArbitrageTrader(fetcher, ArbConfig(min_edge=0.01))  # dry-run by default
for opp in trader.find_opportunities(markets):
    print(opp.ticker, opp.net_edge_per_pair, opp.total_profit)
```

## Going live (real money)

Live trading is **off by default**. To enable it you must:

1. Create a Kalshi API key (key id + RSA private key) in your account settings.
2. Provide credentials via environment variables.
3. Pass `--live` and set spend/contract limits.

```bash
export KALSHI_API_KEY_ID=...
export KALSHI_PRIVATE_KEY="$(cat kalshi_key.pem)"
pip install cryptography                        # required to sign requests
PYTHONPATH=. python examples/kalshi_arbitrage_demo.py \
    --series KXBTCD --live --max-spend 25 --max-contracts 5 --min-edge 0.02
```

Orders are placed as **immediate-or-cancel (IOC) limit** orders at the detected
prices, so they will not rest and chase the market. Start small. Watch for
single-leg fills (unhedged exposure).

## Safety model (`ArbConfig`)

| Field | Default | Meaning |
|-------|---------|---------|
| `dry_run` | `True` | No real orders unless explicitly `False`. |
| `min_edge` | `$0.01` | Minimum net profit per contract pair **after fees** to act. |
| `fee_rate` | `0.07` | Kalshi fee model: `ceil(rate · C · P · (1−P))` per leg. |
| `max_contracts` | `10` | Max contract pairs per opportunity. |
| `max_total_spend` | `$100` | Hard cap on dollars deployed per scan. |
| `min_liquidity` | `0` | Skip markets below this quoted liquidity. |

## Testing

```bash
PYTHONPATH=. python -m pytest tests/test_kalshi_arbitrage.py -v
```
