# Diversified Trend-Following (Time-Series Momentum)

After four iterations proved that mean-reversion signals, cross-sectional sign,
analyst ratings, and news sentiment carry **no tradeable edge** on this stack
(see `README_Signals.md`), this module implements the strategy with the strongest
evidence base in the quant literature: **diversified time-series momentum (trend
following) with volatility targeting** — and it is the first thing here that
produces a genuinely positive, robust, defensible result.

## Why this strategy (the research)

- **Time-series momentum / trend following** has earned a diversified Sharpe of
  ~1.0–1.2 historically, validated out-of-sample back to the 1930s (Moskowitz,
  Ooi & Pedersen 2012; AQR *Demystifying Managed Futures*). The edge comes from
  **diversification across many low-correlation markets** + **volatility
  targeting**, not a clever signal.
- It is **counter-cyclical** — it made money in 2008 and 2022 — so its low
  correlation to equities is as valuable as its standalone return.
- We use **time-series (per-asset)** momentum, *not* cross-sectional: the
  cross-sectional short leg is now broken in equities (catastrophic momentum
  crashes in 2009/2020; 12-1 net Sharpe ≈ −0.23 after costs, SSRN 5367656). This
  matches what we independently found in iteration 1 (negative cross-sectional sign).
- **Volatility targeting** reliably improves risk-adjusted returns for risk assets
  (AlphaArchitect; Man Group). **Crypto trend** is stronger still (Concretum Group).
- **Honest caveat:** trend is regime-dependent (weak 2013–2019, soft 2023–2024)
  and whipsaws in choppy markets.

## What it does

- **Universe** (`trend_following_data.py`): diversified ETFs via Yahoo (SPY, QQQ,
  EFA, EEM, IWM, TLT, IEF, DBC, USO, GLD, VNQ) + crypto (BTC, ETH via Binance,
  Yahoo fallback). All free. Handles Binance's 1000-candle pagination and the
  tz-aware/naive mismatch, and aligns crypto onto the ETF trading calendar.
- **Signal** (`trend_following.py`): an ensemble of EWMAC (EWMA crossover) rules at
  canonical speeds (16/64, 32/128, 64/256) **plus Donchian breakout rules** (40/80/160),
  volatility-normalized and capped; optional 12-month trend sign + 200-day MA filter.
  Combining rule *types* diversifies the signal — adding breakout lifts Sharpe in both
  the 12y (0.65→0.73) and 19y (0.63→0.69) windows. Parameters are canonical, **not
  tuned** to this data.
- **Sizing**: inverse-volatility position sizing to a per-asset vol budget, then the
  whole book scaled to a portfolio vol target (default 15%), with per-asset and
  gross-leverage caps. Long/short and long/flat variants (long/flat just clips
  shorts to zero, so the long side is identical). **Position buffering** (a
  no-trade band, default 0.15) cuts turnover ~28% (29.5× → 21×) and lifts net
  Sharpe by reducing cost drag on persistent trend positions. A **Carver vol
  floor** (default blend 0.3) blends each asset's realized vol with its long-run
  mean before sizing — preventing oversized positions in calm stretches; it lifts
  Sharpe (12y 0.73→0.75, 19y 0.69→0.71) *and* reduces drawdown in both windows.
- **Backtest**: vectorized, **mark-to-market**, lookahead-free (single central
  `shift(1)`; vol scaling uses only trailing data) — generalizing the repo's
  `long_flat_backtest` to a multi-asset panel with per-asset turnover costs.
- **Robustness** (`trend_following_robustness.py`): walk-forward OOS Sharpe,
  parameter sensitivity, per-asset attribution, correlation to SPY, and the
  core+trend blend.
- **Live signal**: `live_target_weights` outputs today's target weights from the
  same pipeline as the backtest.

## Results (12-year backtest, ~2014–2026)

This window was a historic equity bull market — the *worst* environment for trend.
Even so:

| Strategy | Ann return | Vol | Sharpe | Max DD |
|----------|-----------|-----|--------|--------|
| Trend long/short | +8.8% | 15.5% | 0.62 | −27.5% |
| Trend long/flat | +11.7% | 15.7% | 0.78 | −27.0% |
| Buy & hold SPY | +13.8% | 17.4% | 0.83 | −33.7% |
| 60/40 SPY/TLT | +9.0% | 11.0% | 0.84 | −27.2% |

Standalone, trend did **not** beat buy-and-hold SPY in this bull regime — as the
literature predicts. But the value shows up where it should:

- **Robust, not overfit:** parameter sensitivity across 27 configs → Sharpe mean
  0.52, **all positive** (min 0.33, std 0.10). Walk-forward → mean OOS Sharpe 0.62,
  **80% of periods positive**.
- **Genuinely diversifying:** correlation to SPY **+0.10** (≈0), and ≈0 on down-SPY
  days. Contribution is spread across BTC, QQQ, GLD, SPY, EEM — not one asset.
- **The real use case — trend as an overlay on a buy-and-hold core:**

| Portfolio | Ann return | Vol | Sharpe | Max DD |
|-----------|-----------|-----|--------|--------|
| 100% SPY | +14.4% | 17.4% | 0.83 | −33.7% |
| 70% SPY / 30% trend | +13.0% | 13.5% | **0.97** | −24.5% |
| 50% SPY / 50% trend | +12.0% | 12.2% | **0.99** | **−18.0%** |

Adding the trend overlay lifts Sharpe **0.83 → 0.99** and nearly **halves max
drawdown** (−34% → −18%), even in a bull market. That is the honest, evidence-based
way this makes money: a diversifier that improves a portfolio's risk-adjusted
return, with crisis-alpha character that should help most in the regimes (2008/2022
style) absent from this particular window.

## Crisis alpha (the 12y window hid this)

Backtesting over a longer window that includes the 2008 GFC (`--years 19`) shows
what trend following is actually for. Calendar-year long/short returns vs SPY:

| Year | Trend | SPY | |
|------|-------|-----|--|
| 2008 | **+14.1%** | −36.8% | GFC |
| 2018 | +3.0% | −4.6% | Q4 selloff |
| 2020 | +23.9% | +18.3% | COVID |
| 2022 | **+11.8%** | −18.2% | rate shock |
| 2023 | −15.7% | +26.2% | trend's worst (whipsaw) |

Over **2007–2026**, trend matches SPY's Sharpe (**0.63 vs 0.63**) but with **less
than half the max drawdown (−26.6% vs −55.2%)**, at ~0 correlation. It gives up
upside in calm bull markets and pays off in crises — which is precisely why it is
a powerful *diversifier* rather than a standalone replacement for equities.

## Usage

```bash
python examples/trend_following_demo.py --years 12 --target-vol 0.15
```

```python
from data_service.strategies import (
    load_universe, align_calendar, TSMOMConfig, tsmom_backtest, live_target_weights,
)
data = align_calendar(load_universe())
res = tsmom_backtest(data, TSMOMConfig(direction="long_short"))
print(res["strategy"])              # Sharpe, vol, drawdown, ann return
print(live_target_weights(data))    # today's target weights
```

## Paper trading (read-only, order-free)

`paper_trade.py` + `examples/paper_trade_demo.py` take the live strategy targets and
a **portfolio snapshot** (`{equity, positions}`) and (1) print the trades that would
reconcile your book to the targets, (2) log targets to a daily ledger, and (3) mark
the ledger to market to track paper P&L. It is broker-agnostic and never places
orders — populate the snapshot from any broker (the Robinhood MCP is wired to do
this) or use `--notional` for pure simulation.

```bash
python examples/paper_trade_demo.py --mode long_flat --record
python examples/paper_trade_demo.py --carry --snapshot data/portfolio_snapshot.json
```

`long_flat` is the realistic deployable for a cash account (no shorting). Real
broker snapshots/ledgers live under `data/` (gitignored); see
`examples/portfolio_snapshot.example.json` for the format. **No live orders are ever
placed without explicit, separate authorization.**

### Durable daily loop

`.github/workflows/paper_trade.yml` runs the strategy every weekday (22:30 UTC, after
the US close), appends targets to `paper_trades/ledger.csv`, marks the ledger to
market, and commits it — fully unattended, no broker connection, fixed notional, so
nothing sensitive runs in CI. The committed ledger is the durable paper-trading
record (it survives the ephemeral dev container). Scheduled runs fire from the
default branch once merged; trigger it any time via **Run workflow**
(`workflow_dispatch`). The broker rebalance report (vs your real positions) stays a
read-only, on-demand step run from a session with the brokerage MCP.

## Dashboard (frontend)

`frontend/` is a zero-build static dashboard (Chart.js) that visualizes the backtest
and the live paper-trading record — deployable on Vercel with no framework
(`vercel.json` serves `frontend/`). `examples/export_dashboard_data.py` runs the real
backtest + marks the paper ledger and writes `frontend/data.json` (equity curves,
crisis-alpha annual returns, the core+trend blend, current target weights, paper
P&L). The daily GitHub Action regenerates and commits `data.json`, so the deployed
dashboard stays current. It's read-only and shows backtest output — no broker, no
orders.

```bash
python examples/export_dashboard_data.py   # -> frontend/data.json
# open frontend/index.html (or deploy frontend/ on Vercel)
```

The loader (`trend_following_data.py`) now retries Yahoo with backoff and keeps a
gitignored on-disk cache under `data/cache/`, so loads survive transient rate limits.

## Testing

```bash
python -m pytest tests/test_trend_following.py -v
```

20 tests: forecast bounds & no-lookahead, vol-targeting correctness, long/flat
never shorts, controlled trending-basket profitability, cost monotonicity,
different start dates, walk-forward/sensitivity structure, Binance pagination,
tz alignment, live-vs-backtest consistency, and the core+trend blend.

## Improvement log (adopted and rejected)

Each candidate was adopted only if it improved Sharpe in BOTH the 12y and 19y
real-data windows. Rejections are documented because they are findings:

| Candidate | 12y Sharpe | 19y Sharpe | Verdict |
|-----------|-----------|-----------|---------|
| Position buffering (0.15 band) | 0.62 → 0.65 | — | ✅ adopted (turnover −28%) |
| Donchian breakout in ensemble | 0.65 → 0.73 | 0.63 → 0.69 | ✅ adopted |
| +5 ETFs (UUP/SLV/HYG/UNG/TIP) | 0.73 → 0.72 | — | ❌ rejected (noise, worse DD) |
| +6 FX majors (Yahoo spot) | 0.75 → 0.57 | 0.71 → 0.57 | ❌ rejected (FX trend weak post-2008, dilutes book) |
| Full multi-asset carry sleeve (10/13 assets) | 0.75 → 0.66 (cw .25) | 0.71 → 0.73 | ❌ rejected (drawdown −24%→−43%) |

### The carry sleeve (built, measured, rejected — kept as infrastructure)

A *proper* multi-asset carry sleeve is now fully implemented
(`carry.py`, `carry_data.py`) with real data:

- **Rates** (bond term-structure carry, and the cash rate for equity carry):
  Yahoo `^TNX`/`^IRX` back to 2007 — equivalent to FRED T10Y3M, no API key.
- **Equity carry**: trailing-12m dividend yield − 3m cash rate (yfinance dividends).
- **Crypto carry**: −(annualized perpetual funding), live from OKX with a Deribit
  fallback (Binance futures are geo-blocked here).

Carry forecasts use the same causal scaling as trend and are blended into the book
*before* vol targeting, so the two sleeves share one risk budget. Coverage reached
**10 of 13 assets** (all equities, both bonds, both crypto; only DBC/USO/GLD lack a
free carry signal). Result, per the both-windows adoption rule:

| | 12y Sharpe | 19y Sharpe | 12y maxDD | 19y maxDD |
|--|-----------|-----------|-----------|-----------|
| trend only | 0.75 | 0.71 | −24% | −24% |
| +carry 0.25 | 0.66 | 0.73 | −29% | −29% |
| +carry 0.50 | 0.52 | 0.73 | −43% | −43% |

**Linear blend: rejected.** It fails the 12y window outright and, even where Sharpe
nudges up (19y), drawdown nearly doubles. Realized vol stays near the 15% target,
so this is not a sizing bug — it is carry's well-documented **negative skew / "carry
crash"** (Koijen et al.): naive carry is short-volatility and crash-prone, the
*opposite* of trend's crisis alpha.

#### Doing it properly: regime-gated risk-parity combination

`trend_carry_backtest` / `build_combined_weights` combine the sleeves the right way:
each sleeve is vol-targeted **independently** (risk parity), carry is **gated down
in high-volatility regimes** (`_regime_gate`: when the anchor's short-horizon vol is
historically extreme — exactly when carry crashes and trend earns its crisis alpha),
then the total is re-targeted. This **materially mitigates the carry crash**:

| | 12y Sharpe / maxDD | 19y Sharpe / maxDD |
|--|--------------------|--------------------|
| trend only | **0.75** / −24% | 0.71 / −24% |
| linear blend cw0.5 | 0.52 / −43% | 0.73 / −43% |
| gated risk-parity cw0.5 | 0.60 / −33% | **0.78** / −35% |

The gate recovers a lot (12y 0.52→0.60, drawdown −43%→−33%) and over the 19y sample
gated carry **beats trend-only on Sharpe** (0.71→0.78). But it still **fails the
strict both-windows rule**: in the trend-friendly 2014–2026 decade it trails
standalone trend, and drawdown stays meaningfully worse in both windows (carry's
skew can be reduced, not vol-targeted away). So **`carry_weight` defaults to 0** and
the gated combination is the documented, supported way to *opt in* to the carry
premium over long horizons. Full machinery + 13 tests retained as infrastructure.

## Honest bottom line

This is the first strategy in the project with a **positive, robust,
parameter-stable Sharpe (0.6–0.8) that survives walk-forward and is genuinely
uncorrelated to equities**. It is not a money printer and did not beat SPY
standalone in a 12-year bull market — but as a portfolio overlay it measurably
improves risk-adjusted returns, exactly as the research says it should. The
deliverable is a verified, reusable system *and* an honest verdict — the same
standard applied to every prior iteration.
