try:
    from .strategy_base import StrategyBase, StrategyResult
except ImportError:
    StrategyBase = None
    StrategyResult = None

try:
    from .strategy_registry import StrategyRegistry
except ImportError:
    StrategyRegistry = None

try:
    from .strategy_runner import StrategyRunner
except ImportError:
    StrategyRunner = None

try:
    from .strategy_optimizer import StrategyOptimizer
except ImportError:
    StrategyOptimizer = None

try:
    from .kalshi_arbitrage import (
        ArbConfig,
        ArbOpportunity,
        KalshiArbitrageTrader,
    )
except ImportError:
    ArbConfig = None
    ArbOpportunity = None
    KalshiArbitrageTrader = None

__all__ = [
    'StrategyBase',
    'StrategyResult',
    'StrategyRegistry',
    'StrategyRunner',
    'StrategyOptimizer',
    'ArbConfig',
    'ArbOpportunity',
    'KalshiArbitrageTrader',
]

try:
    from .trend_following import (
        TSMOMConfig,
        compute_forecast_series,
        realized_vol,
        build_weights,
        tsmom_backtest,
        trend_carry_backtest,
        build_combined_weights,
        run_both_directions,
        live_target_weights,
    )
except ImportError:
    TSMOMConfig = None
    compute_forecast_series = None
    realized_vol = None
    build_weights = None
    tsmom_backtest = None
    trend_carry_backtest = None
    build_combined_weights = None
    run_both_directions = None
    live_target_weights = None

try:
    from .trend_following_data import load_universe, align_calendar, ETF_UNIVERSE, CRYPTO_UNIVERSE
except ImportError:
    load_universe = None
    align_calendar = None
    ETF_UNIVERSE = None
    CRYPTO_UNIVERSE = None

try:
    from .carry import build_carry_panel, bond_carry, equity_carry, crypto_carry
except ImportError:
    build_carry_panel = None
    bond_carry = None
    equity_carry = None
    crypto_carry = None

try:
    from .trend_following_robustness import (
        walk_forward,
        parameter_sensitivity,
        per_asset_contribution,
        correlation_to_benchmark,
        core_plus_trend,
    )
except ImportError:
    walk_forward = None
    parameter_sensitivity = None
    per_asset_contribution = None
    correlation_to_benchmark = None
    core_plus_trend = None

__all__ += [
    'TSMOMConfig',
    'compute_forecast_series',
    'realized_vol',
    'build_weights',
    'tsmom_backtest',
    'trend_carry_backtest',
    'build_combined_weights',
    'run_both_directions',
    'live_target_weights',
    'load_universe',
    'align_calendar',
    'ETF_UNIVERSE',
    'CRYPTO_UNIVERSE',
    'build_carry_panel',
    'bond_carry',
    'equity_carry',
    'crypto_carry',
    'walk_forward',
    'parameter_sensitivity',
    'per_asset_contribution',
    'correlation_to_benchmark',
    'core_plus_trend',
]
