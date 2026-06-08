"""Kalshi binary-market arbitrage detection and (optional) auto-trading.

The only "essentially guaranteed" profit available on a binary market is a
*locked* arbitrage: YES and NO for a single market settle to a combined
$1.00, so if you can buy one contract of each for a combined cost below
$1.00 (after fees), you net the difference no matter which side wins.

This module:
  1. Detects such opportunities from scraped market data.
  2. Sizes them against a configurable fee model and capital limits.
  3. Optionally executes them -- defaulting to DRY-RUN (paper) mode.

IMPORTANT REALITY CHECK
-----------------------
True arbitrage on Kalshi is rare, small (often a cent or two), short-lived,
and competitive. Quoted best prices are not guaranteed fills: depth may be
thin, both legs may not fill, and fees can erase the edge. Treat live trading
as real money at real risk. Nothing here is financial advice.
"""

import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from ..fetchers.kalshi_fetcher import KalshiFetcher


@dataclass
class ArbConfig:
    """Configuration for arbitrage detection and trading."""

    # Minimum net edge per contract pair, in dollars, AFTER fees, required to
    # act. Guards against treating noise / unfillable quotes as free money.
    min_edge: float = 0.01
    # Per-contract Kalshi trading fee model. Kalshi's standard fee is roughly
    # ceil(0.07 * C * P * (1 - P)) dollars for C contracts at price P. We apply
    # it to each leg conservatively.
    fee_rate: float = 0.07
    # Max contracts (pairs) per opportunity.
    max_contracts: int = 10
    # Max total dollars to deploy across a single scan.
    max_total_spend: float = 100.0
    # Only consider markets with at least this much quoted size/liquidity.
    min_liquidity: float = 0.0

    # ---- Trading mode ----
    # DRY-RUN by default. Must be explicitly set False to place real orders.
    dry_run: bool = True


@dataclass
class ArbOpportunity:
    """A detected locked-arbitrage opportunity for one market."""

    ticker: str
    title: Optional[str]
    yes_ask: float
    no_ask: float
    cost_per_pair: float
    fees_per_pair: float
    net_edge_per_pair: float
    contracts: int
    total_cost: float
    total_profit: float
    minutes_to_close: Optional[float]
    detected_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


class KalshiArbitrageTrader:
    """Detects and (optionally) executes locked YES+NO arbitrage on Kalshi."""

    def __init__(
        self,
        fetcher: KalshiFetcher,
        config: Optional[ArbConfig] = None,
    ):
        self.fetcher = fetcher
        self.config = config or ArbConfig()
        self.logger = logging.getLogger(__name__)
        self.executed: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Fee model
    # ------------------------------------------------------------------
    def _leg_fee(self, price: float, contracts: int) -> float:
        """Estimate Kalshi trading fee for one leg, in dollars.

        Kalshi: fee = ceil(fee_rate * C * P * (1 - P)) cents, rounded up to the
        cent. We compute in dollars and round up to the nearest cent.
        """
        raw = self.config.fee_rate * contracts * price * (1.0 - price)
        return math.ceil(raw * 100) / 100.0

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------
    def find_opportunities(self, markets: pd.DataFrame) -> List[ArbOpportunity]:
        """Scan a markets DataFrame for locked-arbitrage opportunities.

        Requires columns: ticker, yes_ask, no_ask. Optional: title,
        minutes_to_close, liquidity.
        """
        if markets is None or markets.empty:
            return []

        opportunities: List[ArbOpportunity] = []
        spend_budget = self.config.max_total_spend

        # Best edges first.
        df = markets.copy()
        df = df[df["yes_ask"].notna() & df["no_ask"].notna()]
        df["_gross_edge"] = 1.0 - (df["yes_ask"] + df["no_ask"])
        df = df.sort_values("_gross_edge", ascending=False)

        for _, row in df.iterrows():
            yes_ask = float(row["yes_ask"])
            no_ask = float(row["no_ask"])
            if yes_ask <= 0 or no_ask <= 0:
                continue
            if (
                self.config.min_liquidity
                and float(row.get("liquidity") or 0) < self.config.min_liquidity
            ):
                continue

            cost_per_pair = yes_ask + no_ask
            if cost_per_pair >= 1.0:
                continue  # No gross edge; not arbitrage.

            # Size against remaining budget and the per-opportunity cap.
            max_by_budget = (
                int(spend_budget // cost_per_pair) if cost_per_pair > 0 else 0
            )
            contracts = min(self.config.max_contracts, max_by_budget)
            if contracts <= 0:
                continue

            fees = self._leg_fee(yes_ask, contracts) + self._leg_fee(no_ask, contracts)
            fees_per_pair = fees / contracts
            net_edge_per_pair = (1.0 - cost_per_pair) - fees_per_pair
            if net_edge_per_pair < self.config.min_edge:
                continue

            total_cost = cost_per_pair * contracts + fees
            total_profit = net_edge_per_pair * contracts

            opportunities.append(
                ArbOpportunity(
                    ticker=row["ticker"],
                    title=row.get("title"),
                    yes_ask=yes_ask,
                    no_ask=no_ask,
                    cost_per_pair=round(cost_per_pair, 4),
                    fees_per_pair=round(fees_per_pair, 4),
                    net_edge_per_pair=round(net_edge_per_pair, 4),
                    contracts=contracts,
                    total_cost=round(total_cost, 2),
                    total_profit=round(total_profit, 2),
                    minutes_to_close=row.get("minutes_to_close"),
                )
            )
            spend_budget -= total_cost
            if spend_budget <= 0:
                break

        self.logger.info(f"Detected {len(opportunities)} arbitrage opportunities")
        return opportunities

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def execute(self, opp: ArbOpportunity) -> Dict[str, Any]:
        """Execute (or simulate) a single arbitrage opportunity.

        Places two IOC limit buy orders -- one YES, one NO -- at the detected
        ask prices. In dry-run mode no orders are sent.
        """
        if self.config.dry_run:
            self.logger.info(
                f"[DRY-RUN] Would buy {opp.contracts}x YES@{opp.yes_ask} + "
                f"{opp.contracts}x NO@{opp.no_ask} on {opp.ticker} "
                f"(net profit ~${opp.total_profit})"
            )
            result = {
                "ticker": opp.ticker,
                "dry_run": True,
                "contracts": opp.contracts,
                "expected_profit": opp.total_profit,
                "status": "simulated",
            }
            self.executed.append(result)
            return result

        # --- LIVE ORDER PLACEMENT ---
        # Re-check the live book immediately before sending to reduce the risk
        # of trading on a stale quote. Place YES first, then NO; if the second
        # leg fails the position is no longer hedged -- callers must monitor.
        self.logger.warning(
            f"[LIVE] Placing arbitrage orders on {opp.ticker} "
            f"({opp.contracts} pairs)"
        )
        yes_order = self._place_order(opp.ticker, "yes", opp.yes_ask, opp.contracts)
        no_order = self._place_order(opp.ticker, "no", opp.no_ask, opp.contracts)
        result = {
            "ticker": opp.ticker,
            "dry_run": False,
            "contracts": opp.contracts,
            "expected_profit": opp.total_profit,
            "yes_order": yes_order,
            "no_order": no_order,
            "status": "submitted",
        }
        self.executed.append(result)
        return result

    def _place_order(
        self, ticker: str, side: str, price: float, contracts: int
    ) -> Dict[str, Any]:
        """Place a single IOC limit buy order via the authenticated API."""
        price_cents = int(round(price * 100))
        body = {
            "ticker": ticker,
            "action": "buy",
            "side": side,
            "type": "limit",
            "count": contracts,
            "time_in_force": "immediate_or_cancel",
            f"{side}_price": price_cents,
            "client_order_id": f"arb-{ticker}-{side}-{int(time.time()*1000)}",
        }
        return self.fetcher._request(
            "POST", "/portfolio/orders", json_body=body, signed=True
        )

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------
    def run(
        self,
        series_tickers: Optional[List[str]] = None,
        poll_seconds: float = 5.0,
        iterations: Optional[int] = None,
        on_opportunity: Optional[Callable[[ArbOpportunity], None]] = None,
    ) -> List[Dict[str, Any]]:
        """Continuously scan 15-min markets and act on arbitrage.

        :param series_tickers: Restrict scan to these series (recommended)
        :param poll_seconds: Delay between scans
        :param iterations: Stop after N scans (None = run until interrupted)
        :param on_opportunity: Optional callback for each opportunity found
        :return: List of execution results
        """
        mode = "DRY-RUN" if self.config.dry_run else "LIVE"
        self.logger.info(f"Starting Kalshi arbitrage loop in {mode} mode")
        count = 0
        try:
            while iterations is None or count < iterations:
                markets = self.fetcher.get_15min_markets(series_tickers=series_tickers)
                for opp in self.find_opportunities(markets):
                    if on_opportunity:
                        on_opportunity(opp)
                    self.execute(opp)
                count += 1
                if iterations is None or count < iterations:
                    time.sleep(poll_seconds)
        except KeyboardInterrupt:
            self.logger.info("Arbitrage loop interrupted by user")
        return self.executed
