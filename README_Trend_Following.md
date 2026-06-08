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
  canonical speeds (16/64, 32/128, 64/256), volatility-normalized and capped;
  optional 12-month trend sign + 200-day MA filter. Parameters are canonical, **not
  tuned** to this data.
- **Sizing**: inverse-volatility position sizing to a per-asset vol budget, then the
  whole book scaled to a portfolio vol target (default 15%), with per-asset and
  gross-leverage caps. Long/short and long/flat variants (long/flat just clips
  shorts to zero, so the long side is identical).
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

## Testing

```bash
python -m pytest tests/test_trend_following.py -v
```

20 tests: forecast bounds & no-lookahead, vol-targeting correctness, long/flat
never shorts, controlled trending-basket profitability, cost monotonicity,
different start dates, walk-forward/sensitivity structure, Binance pagination,
tz alignment, live-vs-backtest consistency, and the core+trend blend.

## Honest bottom line

This is the first strategy in the project with a **positive, robust,
parameter-stable Sharpe (0.6–0.8) that survives walk-forward and is genuinely
uncorrelated to equities**. It is not a money printer and did not beat SPY
standalone in a 12-year bull market — but as a portfolio overlay it measurably
improves risk-adjusted returns, exactly as the research says it should. The
deliverable is a verified, reusable system *and* an honest verdict — the same
standard applied to every prior iteration.
