#!/usr/bin/env python3
"""
Tick Processor
A small pipeline (filter -> aggregate -> normalize) that sits on top of
RealTimeDataFeed's tick stream. Register directly as a tick callback:

    processor = TickProcessor()
    feed.add_tick_callback(processor.process)
"""

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Deque, Dict, List, Optional

from .real_time_feed import MarketTick


@dataclass
class ProcessedTick:
    """Result of running a MarketTick through the processor pipeline."""
    symbol: str
    price: float
    volume: float
    timestamp: datetime
    normalized_price: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AggregatedBar:
    """OHLCV bar produced by the time-based aggregator."""
    symbol: str
    start: datetime
    end: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    tick_count: int


class TickProcessor:
    """Filter, aggregate, and normalize a live tick stream."""

    def __init__(self, aggregation_seconds: Optional[float] = None,
                 normalization_window: int = 100):
        self.logger = logging.getLogger(__name__)
        self._filters: List[Callable[[MarketTick], bool]] = []
        self._bar_callbacks: List[Callable[[AggregatedBar], None]] = []
        self.aggregation_seconds = aggregation_seconds
        self.normalization_window = normalization_window

        # Per-symbol rolling price history, used for normalization (z-score).
        self._price_history: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=normalization_window)
        )
        # Per-symbol open bar under construction, keyed by bar start time.
        self._open_bars: Dict[str, AggregatedBar] = {}

    def add_filter(self, fn: Callable[[MarketTick], bool]):
        """Register a predicate; a tick is dropped if any filter returns False."""
        self._filters.append(fn)

    def add_aggregator(self, timeframe_seconds: float):
        """Enable bar aggregation over a fixed timeframe, in seconds."""
        self.aggregation_seconds = timeframe_seconds

    def add_bar_callback(self, fn: Callable[[AggregatedBar], None]):
        """Register a callback fired whenever an aggregated bar completes."""
        self._bar_callbacks.append(fn)

    def add_normalizer(self, window: Optional[int] = None):
        """Enable/reconfigure rolling z-score normalization of price."""
        if window is not None:
            self.normalization_window = window
            self._price_history = defaultdict(
                lambda: deque(maxlen=self.normalization_window)
            )

    def _passes_filters(self, tick: MarketTick) -> bool:
        for f in self._filters:
            try:
                if not f(tick):
                    return False
            except Exception as e:
                self.logger.error(f"Filter raised, dropping tick: {e}")
                return False
        return True

    def _normalize(self, symbol: str, price: float) -> Optional[float]:
        history = self._price_history[symbol]
        history.append(price)
        if len(history) < 2:
            return None
        mean = sum(history) / len(history)
        variance = sum((p - mean) ** 2 for p in history) / len(history)
        std = variance ** 0.5
        return (price - mean) / std if std > 0 else 0.0

    def _bar_start(self, timestamp: datetime) -> datetime:
        epoch_seconds = timestamp.timestamp()
        bucket = epoch_seconds - (epoch_seconds % self.aggregation_seconds)
        return datetime.fromtimestamp(bucket)

    def _update_aggregation(self, tick: MarketTick):
        bar_start = self._bar_start(tick.timestamp)
        key = f"{tick.symbol}:{bar_start.isoformat()}"
        bar = self._open_bars.get(key)

        if bar is None:
            # A new bucket started -- flush any older open bar for this symbol first.
            for existing_key in [k for k in self._open_bars if k.startswith(f"{tick.symbol}:")]:
                if existing_key != key:
                    self._flush_bar(existing_key)
            bar = AggregatedBar(
                symbol=tick.symbol, start=bar_start, end=bar_start, open=tick.price,
                high=tick.price, low=tick.price, close=tick.price, volume=0.0,
                tick_count=0,
            )
            self._open_bars[key] = bar

        bar.high = max(bar.high, tick.price)
        bar.low = min(bar.low, tick.price)
        bar.close = tick.price
        bar.end = tick.timestamp
        bar.volume += tick.volume
        bar.tick_count += 1

    def _flush_bar(self, key: str):
        bar = self._open_bars.pop(key, None)
        if bar is None:
            return
        for cb in self._bar_callbacks:
            try:
                cb(bar)
            except Exception as e:
                self.logger.error(f"Bar callback error: {e}")

    async def process(self, tick: MarketTick) -> Optional[ProcessedTick]:
        """Run a tick through filter -> aggregate -> normalize.

        Async so it can be registered directly with
        RealTimeDataFeed.add_tick_callback (whose callbacks are awaited).
        Returns None if the tick was dropped by a filter.
        """
        if not self._passes_filters(tick):
            return None

        if self.aggregation_seconds:
            self._update_aggregation(tick)

        normalized = self._normalize(tick.symbol, tick.price)

        return ProcessedTick(
            symbol=tick.symbol, price=tick.price, volume=tick.volume,
            timestamp=tick.timestamp, normalized_price=normalized,
            metadata={'bid': tick.bid, 'ask': tick.ask},
        )

    def flush_all(self):
        """Force-flush every open aggregation bar (e.g. on shutdown)."""
        for key in list(self._open_bars.keys()):
            self._flush_bar(key)
