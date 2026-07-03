"""
Real-time Data Module
Provides real-time market data streaming via WebSocket
"""

try:
    from .websocket_client import WebSocketClient, WebSocketMessage
    from .real_time_feed import RealTimeDataFeed, MarketTick, MarketSnapshot
    from .tick_processor import TickProcessor, ProcessedTick, AggregatedBar
    from .market_data_stream import MarketDataStream
except ImportError as e:
    WebSocketClient = None
    WebSocketMessage = None
    RealTimeDataFeed = None
    MarketTick = None
    MarketSnapshot = None
    TickProcessor = None
    ProcessedTick = None
    AggregatedBar = None
    MarketDataStream = None

__all__ = [
    'WebSocketClient', 'WebSocketMessage', 'RealTimeDataFeed', 'MarketTick',
    'MarketSnapshot', 'TickProcessor', 'ProcessedTick', 'AggregatedBar',
    'MarketDataStream'
]
