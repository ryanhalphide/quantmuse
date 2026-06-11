from binance.client import Client
try:
    # python-binance >= 1.0
    from binance import ThreadedWebsocketManager as _WebsocketManager
    _MODERN_WS = True
except ImportError:
    # python-binance < 1.0
    from binance.websockets import BinanceSocketManager as _WebsocketManager
    _MODERN_WS = False
from datetime import datetime
import pandas as pd
import logging
from typing import Optional, Dict, Any, Callable
import asyncio
from ..utils.exceptions import DataFetchError

class BinanceFetcher:
    """Binance数据获取器"""
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        """
        初始化Binance客户端
        :param api_key: Binance API key (可选)
        :param api_secret: Binance API secret (可选)
        """
        self.logger = logging.getLogger(__name__)
        try:
            self.api_key = api_key
            self.api_secret = api_secret
            self.client = Client(api_key, api_secret, tld='us')
            self.bm = None  # WebSocket管理器
            self.ws_connections = {}  # 存储WebSocket连接
            self.logger.info("Binance fetcher initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize Binance client: {str(e)}")
            raise

    def fetch_historical_data(
        self,
        symbol: str = "BTCUSD",
        interval: str = "1h",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> pd.DataFrame:
        """
        获取历史K线数据
        :param symbol: 交易对
        :param interval: K线间隔
        :param start_time: 开始时间
        :param end_time: 结束时间
        :param limit: 返回的K线数量
        :return: DataFrame包含OHLCV数据
        """
        try:
            # 转换时间格式
            start_str = int(start_time.timestamp() * 1000) if start_time else None
            end_str = int(end_time.timestamp() * 1000) if end_time else None
            
            # 获取K线数据
            klines = self.client.get_klines(
                symbol=symbol,
                interval=interval,
                startTime=start_str,
                endTime=end_str,
                limit=limit
            )
            
            # 转换为DataFrame
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                'taker_buy_quote', 'ignore'
            ])
            
            # 处理数据类型
            numeric_columns = ['open', 'high', 'low', 'close', 'volume']
            df[numeric_columns] = df[numeric_columns].astype(float)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            self.logger.info(f"Successfully fetched {len(df)} records for {symbol}")
            return df
            
        except Exception as e:
            self.logger.error(f"Error fetching historical data: {str(e)}")
            raise DataFetchError(f"Failed to fetch historical data: {str(e)}")

    async def start_websocket(self, symbol: str, callback: Callable[[Dict], None]):
        """
        启动WebSocket实时数据流
        :param symbol: 交易对
        :param callback: 处理实时数据的回调函数
        """
        try:
            # 创建K线数据连接
            conn_key = f"{symbol.lower()}@kline_1m"

            def handle_socket_message(msg):
                try:
                    if msg['e'] == 'kline':
                        data = {
                            'symbol': msg['s'],
                            'timestamp': pd.to_datetime(msg['E'], unit='ms'),
                            'open': float(msg['k']['o']),
                            'high': float(msg['k']['h']),
                            'low': float(msg['k']['l']),
                            'close': float(msg['k']['c']),
                            'volume': float(msg['k']['v'])
                        }
                        callback(data)
                except Exception as e:
                    self.logger.error(f"Error processing websocket message: {str(e)}")

            if _MODERN_WS:
                if not self.bm:
                    self.bm = _WebsocketManager(
                        api_key=self.api_key, api_secret=self.api_secret, tld='us'
                    )
                    self.bm.start()  # must be running before sockets are added
                self.ws_connections[conn_key] = self.bm.start_kline_socket(
                    callback=handle_socket_message,
                    symbol=symbol,
                    interval='1m'
                )
            else:
                if not self.bm:
                    self.bm = _WebsocketManager(self.client)
                self.ws_connections[conn_key] = self.bm.start_kline_socket(
                    symbol=symbol,
                    callback=handle_socket_message,
                    interval='1m'
                )
                self.bm.start()

            self.logger.info(f"WebSocket started for {symbol}")
            
        except Exception as e:
            self.logger.error(f"Error starting websocket: {str(e)}")
            raise

    def stop_websocket(self, symbol: str):
        """停止WebSocket连接"""
        try:
            conn_key = f"{symbol.lower()}@kline_1m"
            if conn_key in self.ws_connections:
                self.bm.stop_socket(self.ws_connections[conn_key])
                del self.ws_connections[conn_key]
                self.logger.info(f"WebSocket stopped for {symbol}")
        except Exception as e:
            self.logger.error(f"Error stopping websocket: {str(e)}")
            raise

    def get_order_book(self, symbol: str = "BTCUSD", limit: int = 100) -> Dict:
        """
        获取订单簿数据
        :param symbol: 交易对
        :param limit: 订单簿深度
        :return: 订单簿数据
        """
        try:
            depth = self.client.get_order_book(symbol=symbol, limit=limit)
            return {
                'bids': [[float(price), float(qty)] for price, qty in depth['bids']],
                'asks': [[float(price), float(qty)] for price, qty in depth['asks']]
            }
        except Exception as e:
            self.logger.error(f"Error fetching order book: {str(e)}")
            raise DataFetchError(f"Failed to fetch order book: {str(e)}")

    def get_current_price(self, symbol: str = "BTCUSD") -> float:
        """
        获取当前价格
        :param symbol: 交易对
        :return: 最新成交价
        """
        try:
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            return float(ticker['price'])
        except Exception as e:
            self.logger.error(f"Error fetching current price: {str(e)}")
            raise DataFetchError(f"Failed to fetch current price: {str(e)}")

    def get_market_depth(self, symbol: str = "BTCUSD", limit: int = 100) -> Dict:
        """
        获取市场深度 (get_order_book 的别名, 兼容旧调用方)
        :param symbol: 交易对
        :param limit: 订单簿深度
        :return: 订单簿数据
        """
        return self.get_order_book(symbol=symbol, limit=limit)

    def get_recent_trades(self, symbol: str = "BTCUSD", limit: int = 100) -> pd.DataFrame:
        """
        获取最近成交
        :param symbol: 交易对
        :param limit: 返回的成交数量
        :return: 最近成交数据
        """
        try:
            trades = self.client.get_recent_trades(symbol=symbol, limit=limit)
            df = pd.DataFrame(trades)
            df['time'] = pd.to_datetime(df['time'], unit='ms')
            df['price'] = df['price'].astype(float)
            df['qty'] = df['qty'].astype(float)
            return df
        except Exception as e:
            self.logger.error(f"Error fetching recent trades: {str(e)}")
            raise DataFetchError(f"Failed to fetch recent trades: {str(e)}") 