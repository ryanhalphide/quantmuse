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

try:
    from .kalshi_fetcher import KalshiFetcher
except ImportError:
    KalshiFetcher = None

try:
    from .fmp_fetcher import FMPFetcher
except ImportError:
    FMPFetcher = None

try:
    from .eodhd_fetcher import EODHDFetcher
except ImportError:
    EODHDFetcher = None

__all__ = ['BinanceFetcher', 'AlphaVantageFetcher', 'YahooFetcher', 'KalshiFetcher', 'FMPFetcher', 'EODHDFetcher']
