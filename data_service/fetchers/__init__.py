# Import fetchers with error handling
try:
    from .binance_fetcher import BinanceFetcher
except ImportError:
    BinanceFetcher = None

try:
    from .alpha_vantage_fetcher import AlphaVantageFetcher
except ImportError:
    AlphaVantageFetcher = None

try:
    from .yahoo_fetcher import YahooFetcher
except ImportError:
    YahooFetcher = None

__all__ = ['BinanceFetcher', 'AlphaVantageFetcher', 'YahooFetcher']
