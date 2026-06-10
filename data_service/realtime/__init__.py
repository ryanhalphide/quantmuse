"""
Real-time Data Module
Provides real-time market data streaming via WebSocket
"""

try:
    from .websocket_client import WebSocketClient
    from .real_time_feed import RealTimeDataFeed
except ImportError as e:
    WebSocketClient = None
    RealTimeDataFeed = None

__all__ = ['WebSocketClient', 'RealTimeDataFeed']
