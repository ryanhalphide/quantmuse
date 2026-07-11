#!/usr/bin/env python3
"""
Market Data Stream
Wraps multiple WebSocketClient instances (one per exchange), multiplexing
their messages into a single callback stream with exponential-backoff
reconnection when a connection drops.
"""

import asyncio
import logging
from typing import Callable, Dict, List, Optional

from .websocket_client import WebSocketClient, WebSocketMessage


class MarketDataStream:
    """Multi-exchange WebSocket stream with automatic reconnect."""

    def __init__(self, exchanges: List[str], symbols: Optional[List[str]] = None,
                 max_reconnect_delay: float = 60.0, initial_reconnect_delay: float = 1.0):
        self.logger = logging.getLogger(__name__)
        self.exchanges = exchanges
        self.symbols = symbols
        self.max_reconnect_delay = max_reconnect_delay
        self.initial_reconnect_delay = initial_reconnect_delay

        self.clients: Dict[str, WebSocketClient] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._tick_callbacks: List[Callable] = []
        self._disconnect_callbacks: List[Callable] = []
        self._running = False

    def on_tick(self, callback: Callable[[WebSocketMessage], None]):
        """Register a callback invoked for every message from any exchange."""
        self._tick_callbacks.append(callback)

    def on_disconnect(self, callback: Callable[[str], None]):
        """Register a callback invoked with the exchange name on disconnect."""
        self._disconnect_callbacks.append(callback)

    async def start(self):
        """Connect to every configured exchange and begin streaming."""
        self._running = True
        for exchange in self.exchanges:
            self._tasks[exchange] = asyncio.create_task(self._run_exchange(exchange))

    async def stop(self):
        """Stop streaming and disconnect all exchanges."""
        self._running = False
        for task in self._tasks.values():
            task.cancel()
        for client in self.clients.values():
            try:
                await client.disconnect()
            except Exception as e:
                self.logger.error(f"Error disconnecting: {e}")
        self.clients.clear()
        self._tasks.clear()

    async def _run_exchange(self, exchange: str):
        """Connect one exchange, reconnecting with exponential backoff on failure."""
        delay = self.initial_reconnect_delay
        while self._running:
            try:
                client = WebSocketClient(exchange)
                client.add_message_handler(self._make_handler(exchange))
                self.clients[exchange] = client

                await client.connect(self.symbols)
                self.logger.info(f"MarketDataStream connected to {exchange}")
                delay = self.initial_reconnect_delay  # reset backoff on success

                # Poll connection health; WebSocketClient's own message loop
                # runs in the background via asyncio.create_task.
                while self._running and client.is_connected:
                    await asyncio.sleep(1)

                if self._running:
                    self.logger.warning(f"{exchange} disconnected, will reconnect")
                    self._notify_disconnect(exchange)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger.error(f"{exchange} connection error: {e}")
                self._notify_disconnect(exchange)

            if not self._running:
                break

            await asyncio.sleep(delay)
            delay = min(delay * 2, self.max_reconnect_delay)

    def _make_handler(self, exchange: str) -> Callable:
        async def handler(message: WebSocketMessage):
            for cb in self._tick_callbacks:
                try:
                    result = cb(message)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    self.logger.error(f"Tick callback error ({exchange}): {e}")
        return handler

    def _notify_disconnect(self, exchange: str):
        for cb in self._disconnect_callbacks:
            try:
                cb(exchange)
            except Exception as e:
                self.logger.error(f"Disconnect callback error: {e}")

    def is_connected(self, exchange: str) -> bool:
        client = self.clients.get(exchange)
        return bool(client and client.is_connected)

    def connected_exchanges(self) -> List[str]:
        return [ex for ex in self.exchanges if self.is_connected(ex)]
