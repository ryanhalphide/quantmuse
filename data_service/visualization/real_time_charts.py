#!/usr/bin/env python3
"""
Real-Time Chart Manager
Maintains a rolling OHLCV window per symbol from live ticks and regenerates
a chart on demand. Designed to sit on RealTimeDataFeed.add_tick_callback.
"""

import logging
from collections import deque
from typing import Any, Deque, Dict, Optional

import pandas as pd

from .plotly_charts import PlotlyChartGenerator


class RealTimeChartManager:
    """Buffer live ticks per symbol and render charts from the rolling window."""

    def __init__(self, max_points: int = 200, chart_generator: Optional[Any] = None):
        self.logger = logging.getLogger(__name__)
        self.max_points = max_points
        # Default to PlotlyChartGenerator; pass a MatplotlibChartGenerator to
        # swap backends -- both expose create_candlestick_chart / export_chart.
        self.chart_generator = chart_generator or PlotlyChartGenerator()
        self._buffers: Dict[str, Deque[Dict[str, Any]]] = {}

    def _buffer_for(self, symbol: str) -> Deque[Dict[str, Any]]:
        if symbol not in self._buffers:
            self._buffers[symbol] = deque(maxlen=self.max_points)
        return self._buffers[symbol]

    async def on_tick(self, tick: Any):
        """Async tick handler -- register directly with
        RealTimeDataFeed.add_tick_callback(manager.on_tick).
        """
        self.add_tick(tick.symbol, tick.price, tick.timestamp,
                     volume=getattr(tick, 'volume', 0))

    def add_tick(self, symbol: str, price: float, timestamp, volume: float = 0):
        """Append a single tick to the symbol's rolling buffer."""
        self._buffer_for(symbol).append({
            'timestamp': timestamp, 'price': price, 'volume': volume,
        })

    def get_ohlcv(self, symbol: str) -> pd.DataFrame:
        """Return the buffered ticks as an OHLCV-shaped DataFrame.

        Each row is one tick (open == high == low == close == price) rather
        than a resampled bar -- sufficient for a live line/candlestick view.
        """
        buf = self._buffers.get(symbol, deque())
        if not buf:
            return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
        rows = [{
            'open': t['price'], 'high': t['price'], 'low': t['price'],
            'close': t['price'], 'volume': t['volume'],
        } for t in buf]
        index = [t['timestamp'] for t in buf]
        return pd.DataFrame(rows, index=pd.Index(index, name='timestamp'))

    def get_chart(self, symbol: str):
        """Render the current buffer for a symbol into a chart figure."""
        data = self.get_ohlcv(symbol)
        if data.empty:
            self.logger.warning(f"No data buffered for {symbol}")
        return self.chart_generator.create_candlestick_chart(data, symbol)

    def clear(self, symbol: Optional[str] = None):
        """Clear the buffer for one symbol, or all symbols if none given."""
        if symbol:
            self._buffers.pop(symbol, None)
        else:
            self._buffers.clear()

    def symbols(self):
        """Symbols currently buffered."""
        return list(self._buffers.keys())
