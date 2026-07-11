"""
C++ Engine Bindings
Thin import shim for the compiled `quantmuse_engine` pybind11 extension
module (see backend/src/bindings.cpp and backend/CMakeLists.txt).

The extension isn't built by a plain `pip install -e .` -- it requires a
C++ toolchain, CMake, pybind11, spdlog, nlohmann-json, and Boost. Build it
with:

    cmake -B backend/build -DBUILD_PYTHON_MODULE=ON backend
    cmake --build backend/build --target quantmuse_engine
    # then make it importable, e.g.:
    export PYTHONPATH="$PWD/backend/build:$PYTHONPATH"

See USAGE.md §17 for the full walkthrough. Everything else in
`data_service` works whether or not this extension is present -- check
`data_service.engine.AVAILABLE` before relying on any of these names.
"""

import logging

logger = logging.getLogger(__name__)

try:
    import quantmuse_engine as _engine

    Order = _engine.Order
    OrderSide = _engine.OrderSide
    OrderType = _engine.OrderType
    OrderStatus = _engine.OrderStatus
    MarketData = _engine.MarketData
    Position = _engine.Position
    Portfolio = _engine.Portfolio
    RiskLimits = _engine.RiskLimits
    RiskManager = _engine.RiskManager
    OrderExecutor = _engine.OrderExecutor
    Strategy = _engine.Strategy
    Signal = _engine.Signal
    MovingAverageStrategy = _engine.MovingAverageStrategy

    AVAILABLE = True
except ImportError:
    _engine = None
    Order = None
    OrderSide = None
    OrderType = None
    OrderStatus = None
    MarketData = None
    Position = None
    Portfolio = None
    RiskLimits = None
    RiskManager = None
    OrderExecutor = None
    Strategy = None
    Signal = None
    MovingAverageStrategy = None

    AVAILABLE = False
    logger.info(
        "quantmuse_engine C++ extension not built; data_service.engine's "
        "classes are unavailable (AVAILABLE=False). Build it per USAGE.md §17 "
        "to enable BacktestEngine.attach_cpp_risk_manager/attach_cpp_executor."
    )

__all__ = [
    'AVAILABLE', 'Order', 'OrderSide', 'OrderType', 'OrderStatus', 'MarketData',
    'Position', 'Portfolio', 'RiskLimits', 'RiskManager', 'OrderExecutor',
    'Strategy', 'Signal', 'MovingAverageStrategy',
]
