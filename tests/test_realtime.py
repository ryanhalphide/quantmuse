import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from data_service.realtime.real_time_feed import MarketTick
from data_service.realtime.tick_processor import TickProcessor, AggregatedBar
from data_service.realtime.market_data_stream import MarketDataStream
from data_service.realtime.websocket_client import WebSocketMessage


def make_tick(symbol="BTCUSD", price=100.0, volume=1.0, ts=None):
    return MarketTick(symbol=symbol, price=price, volume=volume,
                      timestamp=ts or datetime(2024, 1, 1, 0, 0, 0), exchange="binance")


class TestTickProcessorFilters(unittest.IsolatedAsyncioTestCase):
    async def test_no_filters_passes_through(self):
        tp = TickProcessor()
        result = await tp.process(make_tick())
        self.assertIsNotNone(result)
        self.assertEqual(result.symbol, "BTCUSD")

    async def test_filter_drops_tick(self):
        tp = TickProcessor()
        tp.add_filter(lambda t: t.price > 1000)  # this tick is 100
        result = await tp.process(make_tick(price=100))
        self.assertIsNone(result)

    async def test_filter_allows_tick(self):
        tp = TickProcessor()
        tp.add_filter(lambda t: t.price > 50)
        result = await tp.process(make_tick(price=100))
        self.assertIsNotNone(result)

    async def test_filter_exception_drops_tick(self):
        tp = TickProcessor()
        tp.add_filter(lambda t: 1 / 0)
        result = await tp.process(make_tick())
        self.assertIsNone(result)


class TestTickProcessorNormalization(unittest.IsolatedAsyncioTestCase):
    async def test_normalized_price_none_until_two_points(self):
        tp = TickProcessor()
        r1 = await tp.process(make_tick(price=100))
        self.assertIsNone(r1.normalized_price)
        r2 = await tp.process(make_tick(price=110))
        self.assertIsNotNone(r2.normalized_price)

    async def test_normalized_price_zero_for_constant_series(self):
        tp = TickProcessor()
        await tp.process(make_tick(price=100))
        r = await tp.process(make_tick(price=100))
        self.assertEqual(r.normalized_price, 0.0)


class TestTickProcessorAggregation(unittest.IsolatedAsyncioTestCase):
    async def test_bar_callback_fires_on_next_bucket(self):
        tp = TickProcessor(aggregation_seconds=60)
        bars = []
        tp.add_bar_callback(bars.append)

        base = datetime(2024, 1, 1, 0, 0, 0)
        await tp.process(make_tick(price=100, ts=base))
        await tp.process(make_tick(price=105, ts=base + timedelta(seconds=30)))
        # Next bucket -- should flush the first bar.
        await tp.process(make_tick(price=110, ts=base + timedelta(seconds=61)))

        self.assertEqual(len(bars), 1)
        bar = bars[0]
        self.assertIsInstance(bar, AggregatedBar)
        self.assertEqual(bar.open, 100)
        self.assertEqual(bar.close, 105)
        self.assertEqual(bar.high, 105)
        self.assertEqual(bar.tick_count, 2)

    async def test_flush_all(self):
        tp = TickProcessor(aggregation_seconds=60)
        bars = []
        tp.add_bar_callback(bars.append)
        await tp.process(make_tick(price=100))
        tp.flush_all()
        self.assertEqual(len(bars), 1)

    def test_add_aggregator_sets_timeframe(self):
        tp = TickProcessor()
        tp.add_aggregator(30)
        self.assertEqual(tp.aggregation_seconds, 30)


class TestMarketDataStream(unittest.IsolatedAsyncioTestCase):
    async def test_on_tick_dispatches_message(self):
        received = []
        stream = MarketDataStream(exchanges=["binance"])
        stream.on_tick(lambda msg: received.append(msg))

        handler = stream._make_handler("binance")
        msg = WebSocketMessage(exchange="binance", symbol="btcusdt", data_type="ticker",
                               data={"price": 100}, timestamp=datetime.now(), raw_message="{}")
        await handler(msg)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].symbol, "btcusdt")

    async def test_on_tick_supports_async_callback(self):
        received = []

        async def cb(msg):
            received.append(msg)

        stream = MarketDataStream(exchanges=["binance"])
        stream.on_tick(cb)
        handler = stream._make_handler("binance")
        msg = WebSocketMessage(exchange="binance", symbol="ethusdt", data_type="ticker",
                               data={}, timestamp=datetime.now(), raw_message="{}")
        await handler(msg)
        self.assertEqual(len(received), 1)

    async def test_start_creates_task_per_exchange(self):
        with patch("data_service.realtime.market_data_stream.WebSocketClient") as MockClient:
            instance = MockClient.return_value
            instance.connect = AsyncMock()
            instance.is_connected = False  # loop exits immediately after connect
            instance.add_message_handler = MagicMock()

            stream = MarketDataStream(exchanges=["binance", "kraken"])
            await stream.start()
            self.assertEqual(len(stream._tasks), 2)
            await asyncio.sleep(0.05)  # let the tasks run past connect()
            await stream.stop()
            self.assertEqual(len(stream._tasks), 0)

    async def test_disconnect_callback_fires(self):
        with patch("data_service.realtime.market_data_stream.WebSocketClient") as MockClient:
            instance = MockClient.return_value
            instance.connect = AsyncMock()
            instance.is_connected = False
            instance.add_message_handler = MagicMock()

            disconnects = []
            stream = MarketDataStream(exchanges=["binance"], initial_reconnect_delay=0.01,
                                      max_reconnect_delay=0.02)
            stream.on_disconnect(disconnects.append)
            await stream.start()
            await asyncio.sleep(0.1)
            await stream.stop()
            self.assertIn("binance", disconnects)


if __name__ == "__main__":
    unittest.main()
