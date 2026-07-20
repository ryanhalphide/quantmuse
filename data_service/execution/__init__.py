"""
Execution risk-check module.

Wraps the native C++ risk/portfolio engine (backend/, bound via pybind11 as
the `quantmuse_engine` extension -- see data_service.engine and USAGE.md
Sec.17) and combines it with the existing paper-trading pipeline to turn
today's strategy target weights into a risk-checked, human/agent-reviewable
order proposal.

This module is advisory only: it never submits orders or talks to a broker.
See risk_check.check_rebalance_risk() for the entry point.
"""

from data_service import engine as _engine

RiskManager = _engine.RiskManager
RiskLimits = _engine.RiskLimits
Portfolio = _engine.Portfolio
Order = _engine.Order
Position = _engine.Position
OrderSide = _engine.OrderSide
OrderType = _engine.OrderType
OrderStatus = _engine.OrderStatus
HAVE_NATIVE_RISK_ENGINE = _engine.AVAILABLE

from .risk_check import check_rebalance_risk, DEFAULT_RISK_LIMITS

__all__ = [
    'RiskManager',
    'RiskLimits',
    'Portfolio',
    'Order',
    'Position',
    'OrderSide',
    'OrderType',
    'OrderStatus',
    'HAVE_NATIVE_RISK_ENGINE',
    'check_rebalance_risk',
    'DEFAULT_RISK_LIMITS',
]
