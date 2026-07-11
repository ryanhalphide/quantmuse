#!/usr/bin/env python3
"""
Matplotlib Chart Generator
Static-image mirror of PlotlyChartGenerator's chart methods, for contexts
that need a plain image (reports, PDFs, headless environments) rather than
an interactive Plotly figure.
"""

import logging
from typing import Any, Dict, List, Optional

import matplotlib.figure
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 -- registers 3d projection


class MatplotlibChartGenerator:
    """Generate static Matplotlib charts mirroring PlotlyChartGenerator's API."""

    # Same theme shape/keys as PlotlyChartGenerator, so callers can share config.
    themes = {
        'light': {
            'bgcolor': '#ffffff',
            'textcolor': '#2c3e50',
            'gridcolor': '#ecf0f1',
            'up_color': '#27ae60',
            'down_color': '#e74c3c',
        },
        'dark': {
            'bgcolor': '#1a1a1a',
            'textcolor': '#ffffff',
            'gridcolor': '#2c2c2c',
            'up_color': '#00ff88',
            'down_color': '#ff4444',
        },
    }

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.current_theme = 'light'

    def create_candlestick_chart(self, data: pd.DataFrame, symbol: str,
                                 title: Optional[str] = None,
                                 theme: str = 'light') -> matplotlib.figure.Figure:
        """Create a candlestick chart with a volume subplot."""
        colors = self.themes[theme]
        title = title or f"{symbol} Price Chart"

        has_volume = 'volume' in data.columns
        if has_volume:
            fig, (ax_price, ax_vol) = plt.subplots(
                2, 1, figsize=(12, 8), sharex=True,
                gridspec_kw={'height_ratios': [3, 1]},
            )
        else:
            fig, ax_price = plt.subplots(figsize=(12, 6))
            ax_vol = None

        fig.patch.set_facecolor(colors['bgcolor'])
        self._draw_candlesticks(ax_price, data, colors)
        ax_price.set_title(title, color=colors['textcolor'])
        ax_price.set_ylabel('Price', color=colors['textcolor'])
        ax_price.grid(color=colors['gridcolor'], alpha=0.5)

        if has_volume and ax_vol is not None:
            ax_vol.bar(range(len(data)), data['volume'], color='#3498db', alpha=0.5)
            ax_vol.set_ylabel('Volume', color=colors['textcolor'])
            ax_vol.grid(color=colors['gridcolor'], alpha=0.5)

        fig.tight_layout()
        return fig

    def _draw_candlesticks(self, ax, data: pd.DataFrame, colors: Dict[str, str]):
        for i, (_, row) in enumerate(data.iterrows()):
            up = row['close'] >= row['open']
            color = colors['up_color'] if up else colors['down_color']
            ax.plot([i, i], [row['low'], row['high']], color=color, linewidth=1)
            body_bottom = min(row['open'], row['close'])
            body_height = abs(row['close'] - row['open']) or 1e-9
            ax.add_patch(plt.Rectangle((i - 0.3, body_bottom), 0.6, body_height,
                                       color=color))
        ax.set_xlim(-1, len(data))

    def create_technical_analysis_chart(self, data: pd.DataFrame, symbol: str,
                                        indicators: Optional[List[str]] = None
                                        ) -> matplotlib.figure.Figure:
        """Price + volume + RSI, three stacked subplots (mirrors the Plotly version)."""
        indicators = indicators or ['sma', 'ema', 'bollinger']
        colors = self.themes[self.current_theme]

        fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True,
                                 gridspec_kw={'height_ratios': [3, 1, 1]})
        ax_price, ax_vol, ax_rsi = axes

        self._draw_candlesticks(ax_price, data, colors)
        if 'sma' in indicators and 'sma_20' in data.columns:
            ax_price.plot(range(len(data)), data['sma_20'], color='#e74c3c',
                         linewidth=2, label='SMA 20')
        if 'ema' in indicators and 'ema_20' in data.columns:
            ax_price.plot(range(len(data)), data['ema_20'], color='#f39c12',
                         linewidth=2, label='EMA 20')
        if 'bollinger' in indicators and 'bb_upper' in data.columns:
            ax_price.plot(range(len(data)), data['bb_upper'], color='#9b59b6',
                         linewidth=1, linestyle='--', label='BB Upper')
            ax_price.plot(range(len(data)), data['bb_lower'], color='#9b59b6',
                         linewidth=1, linestyle='--', label='BB Lower')
        ax_price.set_title(f'{symbol} Technical Analysis')
        ax_price.legend(loc='upper left', fontsize=8)

        if 'volume' in data.columns:
            ax_vol.bar(range(len(data)), data['volume'], color='#3498db', alpha=0.7)
        ax_vol.set_ylabel('Volume')

        if 'rsi' in data.columns:
            ax_rsi.plot(range(len(data)), data['rsi'], color='#e67e22', linewidth=2)
            ax_rsi.axhline(70, color='red', linestyle='--')
            ax_rsi.axhline(30, color='green', linestyle='--')
        ax_rsi.set_ylabel('RSI')

        fig.tight_layout()
        return fig

    def create_factor_analysis_chart(self, factor_data: pd.DataFrame,
                                     factor_names: List[str]) -> matplotlib.figure.Figure:
        """2x2 grid: factor performance, correlation heatmap, mean returns, weights pie."""
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        present = [f for f in factor_names if f in factor_data.columns]

        for factor in present:
            axes[0, 0].plot(factor_data.index, factor_data[factor], label=factor)
        axes[0, 0].set_title('Factor Performance')
        axes[0, 0].legend(fontsize=8)

        if present:
            corr = factor_data[present].corr()
            im = axes[0, 1].imshow(corr.values, cmap='RdBu', vmin=-1, vmax=1)
            axes[0, 1].set_xticks(range(len(present)))
            axes[0, 1].set_xticklabels(present, rotation=45, ha='right', fontsize=8)
            axes[0, 1].set_yticks(range(len(present)))
            axes[0, 1].set_yticklabels(present, fontsize=8)
            axes[0, 1].set_title('Factor Correlation')
            fig.colorbar(im, ax=axes[0, 1])

        if present:
            means = [factor_data[f].mean() for f in present]
            axes[1, 0].bar(present, means, color='#1f77b4')
            axes[1, 0].set_title('Factor Returns')
            axes[1, 0].tick_params(axis='x', rotation=45)

        if present:
            weights = [1 / len(present)] * len(present)
            axes[1, 1].pie(weights, labels=present, autopct='%1.1f%%')
            axes[1, 1].set_title('Factor Weights')

        fig.suptitle('Factor Analysis Dashboard')
        fig.tight_layout()
        return fig

    def create_portfolio_performance_chart(self, equity_curve: pd.Series,
                                           benchmark: Optional[pd.Series] = None,
                                           trades: Optional[pd.DataFrame] = None
                                           ) -> matplotlib.figure.Figure:
        """Equity curve (+ optional benchmark/trade markers) over a drawdown subplot."""
        colors = self.themes[self.current_theme]
        fig, (ax_eq, ax_dd) = plt.subplots(2, 1, figsize=(12, 8), sharex=True,
                                           gridspec_kw={'height_ratios': [2, 1]})

        ax_eq.plot(equity_curve.index, equity_curve.values, color=colors['up_color'],
                  linewidth=2, label='Portfolio')
        if benchmark is not None:
            ax_eq.plot(benchmark.index, benchmark.values, color=colors['down_color'],
                      linewidth=2, linestyle='--', label='Benchmark')
        if trades is not None and not trades.empty:
            buys = trades[trades['side'] == 'buy']
            sells = trades[trades['side'] == 'sell']
            if not buys.empty:
                ax_eq.scatter(buys['timestamp'], buys['price'], color='green',
                             marker='^', s=60, label='Buy Trades', zorder=5)
            if not sells.empty:
                ax_eq.scatter(sells['timestamp'], sells['price'], color='red',
                             marker='v', s=60, label='Sell Trades', zorder=5)
        ax_eq.set_title('Portfolio Performance Analysis')
        ax_eq.legend(fontsize=8)

        returns = equity_curve.pct_change().dropna()
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        ax_dd.fill_between(drawdown.index, drawdown.values * 100, 0,
                          color='red', alpha=0.3)
        ax_dd.plot(drawdown.index, drawdown.values * 100, color='red', linewidth=2)
        ax_dd.set_title('Drawdown')

        fig.tight_layout()
        return fig

    def create_heatmap_chart(self, data: pd.DataFrame, x_col: str, y_col: str,
                             value_col: str, title: str = "Heatmap"
                             ) -> matplotlib.figure.Figure:
        pivot = data.pivot_table(index=y_col, columns=x_col, values=value_col,
                                 aggfunc='mean')
        fig, ax = plt.subplots(figsize=(10, 6))
        im = ax.imshow(pivot.values, cmap='viridis', aspect='auto')
        ax.set_xticks(range(len(pivot.columns)))
        ax.set_xticklabels(pivot.columns, rotation=45, ha='right')
        ax.set_yticks(range(len(pivot.index)))
        ax.set_yticklabels(pivot.index)
        ax.set_xlabel(x_col)
        ax.set_ylabel(y_col)
        ax.set_title(title)
        fig.colorbar(im, ax=ax, label=value_col)
        fig.tight_layout()
        return fig

    def create_3d_surface_chart(self, x_data: np.ndarray, y_data: np.ndarray,
                                z_data: np.ndarray, title: str = "3D Surface"
                                ) -> matplotlib.figure.Figure:
        fig = plt.figure(figsize=(10, 8))
        ax = fig.add_subplot(111, projection='3d')
        ax.plot_surface(x_data, y_data, z_data, cmap='viridis')
        ax.set_xlabel('X')
        ax.set_ylabel('Y')
        ax.set_zlabel('Z')
        ax.set_title(title)
        return fig

    def export_chart(self, fig: matplotlib.figure.Figure, filename: str,
                     format: str = 'png', dpi: int = 150):
        """Export chart to file. format is any format matplotlib's savefig supports."""
        try:
            fig.savefig(filename, format=format, dpi=dpi, bbox_inches='tight')
            self.logger.info(f"Chart exported to {filename}")
        except Exception as e:
            self.logger.error(f"Failed to export chart: {e}")
            raise
