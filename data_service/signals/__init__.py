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

try:
    from .signal_backtest import (
        compute_technical_signal_series,
        evaluate_predictive_value,
        make_signal_strategy,
    )
except ImportError:
    compute_technical_signal_series = None
    evaluate_predictive_value = None
    make_signal_strategy = None

__all__ = [
    "SignalProvider",
    "SignalResult",
    "score_to_label",
    "AlphaVantageSignalProvider",
    "compute_technical_signal_series",
    "evaluate_predictive_value",
    "make_signal_strategy",
]
