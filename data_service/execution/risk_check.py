"""Advisory risk-check layer over the paper-trading rebalance report.

check_rebalance_risk() is the entry point: it computes the trades needed to
reach today's target weights (via the existing, unchanged
data_service.strategies.paper_trade.rebalance_report), then -- when the
native quantmuse_engine extension is built -- marks a snapshot Portfolio to
market and runs each proposed trade through the C++ RiskManager, annotating
the result with pass/fail + a warning reason.

This never submits orders. It produces a DataFrame for a human/agent to
review before deciding whether to place anything via the broker's own tools.
"""

import os
from typing import Dict, Optional

import pandas as pd

from ..strategies import paper_trade as pt

# Illustrative starting limits for a long-only, vol-targeted ETF book -- not
# derived from any specific account's real risk appetite or size. Tune after
# reviewing check_rebalance_risk()'s output against your actual portfolio.
DEFAULT_RISK_LIMITS = dict(
    max_position_size=0.35,
    max_leverage=1.10,
    max_drawdown=0.25,
    daily_loss_limit=0.05,   # fraction of equity, converted to dollars below
    position_concentration=0.35,
)


def _equity_history_from_ledger(ledger_path: str, fallback_equity: float):
    """Real dollar previous-equity + high-water-mark from the ledger's own
    ``equity`` column (recorded daily by paper_trade.record_targets). Falls
    back to today's equity for both (i.e. zero prior drawdown/P&L) if there's
    no ledger yet."""
    if not os.path.exists(ledger_path):
        return fallback_equity, fallback_equity
    df = pd.read_csv(ledger_path, parse_dates=["date"])
    if df.empty:
        return fallback_equity, fallback_equity
    daily_equity = df.groupby("date")["equity"].first().sort_index()
    previous_equity = float(daily_equity.iloc[-1])
    high_water_mark = float(daily_equity.max())
    return previous_equity, high_water_mark


def check_rebalance_risk(target_weights: pd.Series, equity: float,
                         positions: Dict[str, float], prices: Dict[str, float],
                         risk_limits: Optional[Dict[str, float]] = None,
                         previous_equity: Optional[float] = None,
                         high_water_mark: Optional[float] = None,
                         ledger_path: str = "paper_trades/ledger.csv",
                         min_trade: float = 1.0) -> pd.DataFrame:
    """Risk-check the trades implied by rebalance_report(). Advisory only --
    never submits or blocks anything on its own; returns a DataFrame for
    review, with ``risk_ok``/``risk_reason`` columns added.
    """
    trades = pt.rebalance_report(target_weights, equity, positions, prices, min_trade)

    from . import HAVE_NATIVE_RISK_ENGINE, RiskManager, RiskLimits, Portfolio, Order, OrderSide, OrderType

    if not HAVE_NATIVE_RISK_ENGINE:
        trades["risk_ok"] = None
        trades["risk_reason"] = (
            "native risk engine not built -- see USAGE.md Sec.17 "
            "(QUANTMUSE_BUILD_CPP=1 pip install -e '.[cpp]')"
        )
        return trades

    limits_dict = {**DEFAULT_RISK_LIMITS, **(risk_limits or {})}
    limits = RiskLimits()
    limits.max_position_size = limits_dict["max_position_size"]
    limits.max_leverage = limits_dict["max_leverage"]
    limits.max_drawdown = limits_dict["max_drawdown"]
    limits.daily_loss_limit = limits_dict["daily_loss_limit"] * equity
    limits.position_concentration = limits_dict["position_concentration"]
    rm = RiskManager(limits)

    if previous_equity is None or high_water_mark is None:
        auto_prev, auto_hwm = _equity_history_from_ledger(ledger_path, equity)
        previous_equity = previous_equity if previous_equity is not None else auto_prev
        high_water_mark = high_water_mark if high_water_mark is not None else auto_hwm

    portfolio = Portfolio()
    invested = 0.0
    for symbol, shares in positions.items():
        px = prices.get(symbol, 0.0)
        if shares:
            portfolio.update_position(symbol, float(shares), float(px))
            invested += float(shares) * float(px)
    # Portfolio() starts with a hardcoded cash default -- set it explicitly to
    # whatever of `equity` isn't already tied up in the given positions, never
    # relying on that default (see backend/include/common/types.hpp).
    portfolio.set_cash(equity - invested)
    portfolio.seed_equity_history(previous_equity, high_water_mark)

    price_map = {s: float(p) for s, p in prices.items()}
    portfolio.mark_to_market(price_map)
    rm.update_current_prices(price_map)

    ok_col, reason_col = [], []
    for symbol, row in trades.iterrows():
        if row["action"] == "HOLD":
            ok_col.append(True)
            reason_col.append("")
            continue
        if pd.isna(row["trade_shares"]):
            # rebalance_report() sets trade_shares=NaN when a price is
            # missing/non-positive -- that trade could not be risk-checked
            # at all, which is not the same as being approved.
            ok_col.append(None)
            reason_col.append("missing_price")
            continue
        side = OrderSide.BUY if row["action"] == "BUY" else OrderSide.SELL
        order = Order(symbol, side, OrderType.MARKET, abs(float(row["trade_shares"])))
        order.set_price(float(prices.get(symbol, 0.0)))
        passed = rm.check_order_risk(order, portfolio)
        ok_col.append(bool(passed))
        reason_col.append("" if passed else rm.get_last_rejection_reason())

    trades["risk_ok"] = ok_col
    trades["risk_reason"] = reason_col
    return trades
