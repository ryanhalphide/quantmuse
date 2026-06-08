try:
    from .base import SignalProvider, SignalResult, score_to_label
except ImportError:
    SignalProvider = None
    SignalResult = None
    score_to_label = None

try:
    from .alpha_vantage_signals import AlphaVantageSignalProvider
except ImportError:
    AlphaVantageSignalProvider = None

__all__ = [
    "SignalProvider",
    "SignalResult",
    "score_to_label",
    "AlphaVantageSignalProvider",
]
