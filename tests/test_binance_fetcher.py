import unittest
from unittest.mock import Mock, patch
import pandas as pd
from datetime import datetime
import requests
from data_service.fetchers.binance_fetcher import BinanceFetcher
from binance.exceptions import BinanceAPIException

class TestBinanceFetcher(unittest.TestCase):
    """Test cases for BinanceFetcher"""

    def setUp(self):
        """Set up test fixtures"""
        # Patch the name the fetcher module actually holds (it does
        # `from binance.client import Client`), otherwise tests hit the real API
        self.client_patcher = patch('data_service.fetchers.binance_fetcher.Client')
        self.requests_patcher = patch('binance.client.requests.get')
        
        # Start patchers
        self.mock_client_class = self.client_patcher.start()
        self.mock_requests = self.requests_patcher.start()
        
        # Create a mock response
        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.text = '{"msg": "success"}'
        self.mock_requests.return_value = mock_response
        
        # Configure the mock client instance
        self.mock_client_instance = Mock()
        self.mock_client_class.return_value = self.mock_client_instance
        
        # Create fetcher with mocked client
        self.fetcher = BinanceFetcher()

    def tearDown(self):
        """Clean up after each test"""
        self.client_patcher.stop()
        self.requests_patcher.stop()

    def test_initialization(self):
        """Test if fetcher initializes correctly"""
        self.assertIsNotNone(self.fetcher.client)

    def test_fetch_historical_data(self):
        """Test historical data fetching"""
        # Mock data
        mock_klines = [
            [
                1499040000000,  # Timestamp
                "8100.0",       # Open
                "8200.0",       # High
                "8000.0",       # Low
                "8150.0",       # Close
                "100.0",        # Volume
                1499644799999,  # Close time
                "1000.0",       # Quote volume
                100,            # Number of trades
                "50.0",         # Taker buy base
                "400.0",        # Taker buy quote
                "0"            # Ignore
            ]
        ]
        
        # Configure mock
        self.mock_client_instance.get_klines.return_value = mock_klines
        
        # Execute test
        df = self.fetcher.fetch_historical_data("BTCUSDT")
        
        # Verify results
        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 1)
        self.assertEqual(float(df['close'].iloc[0]), 8150.0)

    def test_invalid_symbol(self):
        """Test handling of invalid symbol"""
        # Configure mock to raise an exception
        self.mock_client_instance.get_klines.side_effect = BinanceAPIException(
            response=Mock(status_code=400, text="Invalid symbol"),
            status_code=400,
            text="Invalid symbol"
        )
        
        with self.assertRaises(Exception):
            self.fetcher.fetch_historical_data("")

    def test_market_depth(self):
        """Test market depth fetching"""
        # Mock order book data
        mock_depth = {
            'bids': [['8100.0', '1.0'], ['8099.0', '2.0']],
            'asks': [['8101.0', '1.0'], ['8102.0', '2.0']]
        }
        
        # Configure mock
        self.mock_client_instance.get_order_book.return_value = mock_depth
        
        # Execute test
        depth = self.fetcher.get_market_depth("BTCUSDT")
        
        # Verify results
        self.assertIn('bids', depth)
        self.assertIn('asks', depth)
        self.assertEqual(len(depth['bids']), 2)
        self.assertEqual(len(depth['asks']), 2)

if __name__ == '__main__':
    unittest.main() 