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
        long_flat_backtest,
    )
except ImportError:
    compute_technical_signal_series = None
    evaluate_predictive_value = None
    make_signal_strategy = None
    long_flat_backtest = None

try:
    from .signal_sweep import ic_sweep, walk_forward_ic, cross_sectional_ls
except ImportError:
    ic_sweep = None
    walk_forward_ic = None
    cross_sectional_ls = None

try:
    from .analyst_signals import (
        consensus_score,
        revision_signal,
        evaluate_orthogonality,
        evaluate_signal_orthogonality,
        pooled_horizon_ic,
    )
except ImportError:
    consensus_score = None
    revision_signal = None
    evaluate_orthogonality = None
    evaluate_signal_orthogonality = None
    pooled_horizon_ic = None

__all__ = [
    "SignalProvider",
    "SignalResult",
    "score_to_label",
    "AlphaVantageSignalProvider",
    "compute_technical_signal_series",
    "evaluate_predictive_value",
    "make_signal_strategy",
    "long_flat_backtest",
    "ic_sweep",
    "walk_forward_ic",
    "cross_sectional_ls",
    "consensus_score",
    "revision_signal",
    "evaluate_orthogonality",
    "evaluate_signal_orthogonality",
    "pooled_horizon_ic",
]
