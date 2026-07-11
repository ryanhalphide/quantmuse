#!/usr/bin/env python3
"""
Dashboard Chart Generator
Composes multi-chart layouts for the web/Streamlit dashboards, built on top
of PlotlyChartGenerator's individual chart methods.
"""

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from .plotly_charts import PlotlyChartGenerator


class DashboardChartGenerator:
    """Bundle related charts into named layouts for a dashboard page."""

    def __init__(self, chart_generator: Optional[PlotlyChartGenerator] = None):
        self.logger = logging.getLogger(__name__)
        self.charts = chart_generator or PlotlyChartGenerator()

    def build_overview_layout(self, data: pd.DataFrame, symbol: str = "PORTFOLIO"
                              ) -> List[Any]:
        """Price + technical-analysis view for a single instrument's overview page."""
        figures = [self.charts.create_candlestick_chart(data, symbol)]
        try:
            figures.append(self.charts.create_technical_analysis_chart(data, symbol))
        except Exception as e:
            self.logger.warning(f"Skipping technical analysis chart: {e}")
        return figures

    def build_strategy_layout(self, result: Dict[str, Any]) -> List[Any]:
        """Equity curve (+ trades) for a StrategyResult/backtest-results dict.

        Expects a dict with an 'equity_curve' Series/DataFrame column
        'total_value', optionally 'benchmark' and 'trades'.
        """
        figures = []
        equity_curve = result.get('equity_curve')
        if equity_curve is None:
            self.logger.warning("No equity_curve in result; strategy layout is empty")
            return figures

        if isinstance(equity_curve, pd.DataFrame) and 'total_value' in equity_curve.columns:
            equity_series = equity_curve['total_value']
        else:
            equity_series = equity_curve

        figures.append(self.charts.create_portfolio_performance_chart(
            equity_series, benchmark=result.get('benchmark'), trades=result.get('trades'),
        ))
        return figures

    def build_factor_layout(self, factor_data: pd.DataFrame,
                            factor_names: Optional[List[str]] = None) -> List[Any]:
        """Factor-analysis dashboard view for a cross-sectional factor table."""
        names = factor_names or [c for c in factor_data.columns
                                 if pd.api.types.is_numeric_dtype(factor_data[c])]
        if not names:
            self.logger.warning("No numeric factor columns found for factor layout")
            return []
        return [self.charts.create_factor_analysis_chart(factor_data, names)]

    def export_layout(self, figures: List[Any], prefix: str, format: str = 'html'):
        """Export each figure in a layout to prefix_0.<ext>, prefix_1.<ext>, ..."""
        for i, fig in enumerate(figures):
            self.charts.export_chart(fig, f"{prefix}_{i}.{format}", format=format)
