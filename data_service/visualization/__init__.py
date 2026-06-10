"""
Visualization Module
Provides advanced charting capabilities with Plotly
"""

try:
    from .plotly_charts import PlotlyChartGenerator
except ImportError as e:
    PlotlyChartGenerator = None

__all__ = ['PlotlyChartGenerator']
