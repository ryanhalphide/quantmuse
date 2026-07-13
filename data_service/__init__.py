# Core modules
try:
    from .fetchers import AlphaVantageFetcher, YahooFetcher, BinanceFetcher, KalshiFetcher
except ImportError:
    # Handle missing dependencies gracefully
    AlphaVantageFetcher = None
    YahooFetcher = None
    BinanceFetcher = None
    KalshiFetcher = None

try:
    from .processors import DataProcessor
except ImportError:
    DataProcessor = None

try:
    from .storage import DatabaseManager, FileStorage, CacheManager
except ImportError:
    DatabaseManager = None
    FileStorage = None
    CacheManager = None

try:
    from .utils import setup_logger, DataFetchError, ProcessingError, ValidationError
except ImportError:
    setup_logger = None
    DataFetchError = None
    ProcessingError = None
    ValidationError = None

# AI modules
try:
    from .ai import SentimentAnalyzer, NewsProcessor, SocialMediaMonitor, LLMIntegration, NLPProcessor, SentimentFactorCalculator, LangChainAgent
except ImportError:
    SentimentAnalyzer = None
    NewsProcessor = None
    SocialMediaMonitor = None
    LLMIntegration = None
    NLPProcessor = None
    SentimentFactorCalculator = None
    LangChainAgent = None

# Backtesting modules
try:
    from .backtest import BacktestEngine, PerformanceAnalyzer
except ImportError:
    BacktestEngine = None
    PerformanceAnalyzer = None

# Factor analysis modules
try:
    from .factors import FactorCalculator, FactorScreener, FactorBacktest, StockSelector, FactorOptimizer
except ImportError:
    FactorCalculator = None
    FactorScreener = None
    FactorBacktest = None
    StockSelector = None
    FactorOptimizer = None

# Signal providers
try:
    from .signals import SignalProvider, SignalResult, AlphaVantageSignalProvider
except ImportError:
    SignalProvider = None
    SignalResult = None
    AlphaVantageSignalProvider = None

# C++ engine bindings (optional -- requires building the quantmuse_engine
# extension per USAGE.md Sec.17; data_service.engine guards its own imports
# and exposes AVAILABLE=False when the extension isn't built)
try:
    from . import engine
except ImportError:
    engine = None

__version__ = "0.1.0"

__all__ = [
    # Data fetchers
    'AlphaVantageFetcher',
    'YahooFetcher',
    'BinanceFetcher',
    'KalshiFetcher',

    # Data processors
    'DataProcessor',
    
    # Storage
    'DatabaseManager',
    'FileStorage',
    'CacheManager',
    
    # Utilities
    'setup_logger',
    'DataFetchError',
    'ProcessingError',
    'ValidationError',
    
    # AI modules
    'SentimentAnalyzer',
    'NewsProcessor',
    'SocialMediaMonitor',
    'LLMIntegration',
    'NLPProcessor',
    'SentimentFactorCalculator',
    'LangChainAgent',
    
    # Backtesting
    'BacktestEngine',
    'PerformanceAnalyzer',
    
    # Quantitative factors
    'FactorCalculator',
    'FactorScreener',
    'FactorBacktest',
    'StockSelector',
    'FactorOptimizer',

    # Signal providers
    'SignalProvider',
    'SignalResult',
    'AlphaVantageSignalProvider'
] 