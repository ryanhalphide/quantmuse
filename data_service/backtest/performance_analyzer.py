import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import logging

class PerformanceAnalyzer:
    """Performance analysis and reporting for trading strategies"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
    def analyze_performance(self, backtest_results: Dict[str, Any]) -> Dict[str, Any]:
        """Comprehensive performance analysis"""
        if not backtest_results:
            return {}
        
        analysis = {}
        
        # Basic metrics
        analysis['basic_metrics'] = self._calculate_basic_metrics(backtest_results)
        
        # Risk metrics
        analysis['risk_metrics'] = self._calculate_risk_metrics(backtest_results)
        
        # Trade analysis
        analysis['trade_analysis'] = self._analyze_trades(backtest_results)
        
        # Drawdown analysis
        analysis['drawdown_analysis'] = self._analyze_drawdowns(backtest_results)
        
        # Monthly/yearly returns
        analysis['periodic_returns'] = self._calculate_periodic_returns(backtest_results)
        
        return analysis
    
    def _calculate_basic_metrics(self, results: Dict[str, Any]) -> Dict[str, float]:
        """Calculate basic performance metrics"""
        equity_curve = results.get('equity_curve', pd.DataFrame())
        if equity_curve.empty:
            return {}
        
        initial_capital = results.get('initial_capital', 0)
        final_value = results.get('final_value', 0)
        
        # Calculate returns
        total_return = (final_value - initial_capital) / initial_capital if initial_capital > 0 else 0
        annualized_return = results.get('annualized_return', 0)
        
        # Calculate volatility
        returns = equity_curve['total_value'].pct_change().dropna()
        volatility = returns.std() * np.sqrt(252) if len(returns) > 0 else 0
        
        # Sharpe ratio
        risk_free_rate = 0.02  # Assume 2% risk-free rate
        sharpe_ratio = (annualized_return - risk_free_rate) / volatility if volatility > 0 else 0
        
        # Sortino ratio
        downside_returns = returns[returns < 0]
        downside_volatility = downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 else 0
        sortino_ratio = (annualized_return - risk_free_rate) / downside_volatility if downside_volatility > 0 else 0
        
        return {
            'total_return': total_return,
            'annualized_return': annualized_return,
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'final_value': final_value,
            'total_pnl': final_value - initial_capital
        }
    
    def _calculate_risk_metrics(self, results: Dict[str, Any]) -> Dict[str, float]:
        """Calculate risk metrics"""
        equity_curve = results.get('equity_curve', pd.DataFrame())
        if equity_curve.empty:
            return {}
        
        returns = equity_curve['total_value'].pct_change().dropna()
        
        # Value at Risk (VaR)
        var_95 = np.percentile(returns, 5) if len(returns) > 0 else 0
        var_99 = np.percentile(returns, 1) if len(returns) > 0 else 0
        
        # Conditional Value at Risk (CVaR)
        cvar_95 = returns[returns <= var_95].mean() if len(returns[returns <= var_95]) > 0 else 0
        cvar_99 = returns[returns <= var_99].mean() if len(returns[returns <= var_99]) > 0 else 0
        
        # Maximum drawdown
        max_drawdown = results.get('max_drawdown', 0)
        
        # Calmar ratio
        annualized_return = results.get('annualized_return', 0)
        calmar_ratio = annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0
        
        return {
            'var_95': var_95,
            'var_99': var_99,
            'cvar_95': cvar_95,
            'cvar_99': cvar_99,
            'max_drawdown': max_drawdown,
            'calmar_ratio': calmar_ratio
        }
    
    def _analyze_trades(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze trade performance"""
        trades = results.get('trades', [])
        if not trades:
            return {}
        
        # Convert trades to DataFrame
        trade_data = []
        for trade in trades:
            trade_data.append({
                'timestamp': trade.timestamp,
                'symbol': trade.symbol,
                'side': trade.side,
                'quantity': trade.quantity,
                'price': trade.price,
                'value': trade.quantity * trade.price
            })
        
        trades_df = pd.DataFrame(trade_data)
        
        # Calculate trade statistics
        total_trades = len(trades)
        buy_trades = len(trades_df[trades_df['side'] == 'buy'])
        sell_trades = len(trades_df[trades_df['side'] == 'sell'])
        
        # Average trade size
        avg_trade_size = trades_df['value'].mean() if len(trades_df) > 0 else 0
        
        # Trade frequency
        if len(trades_df) > 1:
            trade_dates = trades_df['timestamp'].sort_values()
            avg_days_between_trades = (trade_dates.iloc[-1] - trade_dates.iloc[0]).days / (len(trade_dates) - 1)
        else:
            avg_days_between_trades = 0
        
        return {
            'total_trades': total_trades,
            'buy_trades': buy_trades,
            'sell_trades': sell_trades,
            'avg_trade_size': avg_trade_size,
            'avg_days_between_trades': avg_days_between_trades,
            'trades_df': trades_df
        }
    
    def _analyze_drawdowns(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze drawdown periods"""
        equity_curve = results.get('equity_curve', pd.DataFrame())
        if equity_curve.empty:
            return {}
        
        # Calculate drawdown series
        peak = equity_curve['total_value'].expanding().max()
        drawdown = (equity_curve['total_value'] - peak) / peak
        
        # Find drawdown periods
        drawdown_periods = self._find_drawdown_periods(drawdown)
        
        # Calculate drawdown statistics
        max_drawdown = drawdown.min()
        avg_drawdown = drawdown[drawdown < 0].mean() if len(drawdown[drawdown < 0]) > 0 else 0
        drawdown_duration = len(drawdown_periods)
        
        return {
            'max_drawdown': max_drawdown,
            'avg_drawdown': avg_drawdown,
            'drawdown_duration': drawdown_duration,
            'drawdown_periods': drawdown_periods,
            'drawdown_series': drawdown
        }
    
    def _find_drawdown_periods(self, drawdown_series: pd.Series) -> List[Dict[str, Any]]:
        """Find individual drawdown periods"""
        periods = []
        in_drawdown = False
        start_idx = None
        
        for i, dd in enumerate(drawdown_series):
            if dd < 0 and not in_drawdown:
                # Start of drawdown
                in_drawdown = True
                start_idx = i
            elif dd >= 0 and in_drawdown:
                # End of drawdown
                in_drawdown = False
                periods.append({
                    'start_idx': start_idx,
                    'end_idx': i,
                    'duration': i - start_idx,
                    'max_drawdown': drawdown_series.iloc[start_idx:i].min()
                })
        
        # Handle ongoing drawdown
        if in_drawdown:
            periods.append({
                'start_idx': start_idx,
                'end_idx': len(drawdown_series) - 1,
                'duration': len(drawdown_series) - 1 - start_idx,
                'max_drawdown': drawdown_series.iloc[start_idx:].min()
            })
        
        return periods
    
    def _calculate_periodic_returns(self, results: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        """Calculate monthly and yearly returns"""
        equity_curve = results.get('equity_curve', pd.DataFrame())
        if equity_curve.empty:
            return {}
        
        # Calculate daily returns
        equity_curve['returns'] = equity_curve['total_value'].pct_change()
        
        # Monthly returns ('ME'/'YE': pandas 2.2+ replaced the 'M'/'Y' aliases)
        monthly_returns = equity_curve['returns'].resample('ME').apply(
            lambda x: (1 + x).prod() - 1
        )

        # Yearly returns
        yearly_returns = equity_curve['returns'].resample('YE').apply(
            lambda x: (1 + x).prod() - 1
        )
        
        return {
            'monthly_returns': monthly_returns,
            'yearly_returns': yearly_returns
        }
    
    def generate_report(self, analysis: Dict[str, Any]) -> str:
        """Generate performance report as text"""
        report = []
        report.append("=" * 50)
        report.append("PERFORMANCE ANALYSIS REPORT")
        report.append("=" * 50)
        
        # Basic metrics
        basic = analysis.get('basic_metrics', {})
        if basic:
            report.append("\nBASIC METRICS:")
            report.append(f"Total Return: {basic.get('total_return', 0):.2%}")
            report.append(f"Annualized Return: {basic.get('annualized_return', 0):.2%}")
            report.append(f"Volatility: {basic.get('volatility', 0):.2%}")
            report.append(f"Sharpe Ratio: {basic.get('sharpe_ratio', 0):.2f}")
            report.append(f"Sortino Ratio: {basic.get('sortino_ratio', 0):.2f}")
        
        # Risk metrics
        risk = analysis.get('risk_metrics', {})
        if risk:
            report.append("\nRISK METRICS:")
            report.append(f"Max Drawdown: {risk.get('max_drawdown', 0):.2%}")
            report.append(f"VaR (95%): {risk.get('var_95', 0):.2%}")
            report.append(f"CVaR (95%): {risk.get('cvar_95', 0):.2%}")
            report.append(f"Calmar Ratio: {risk.get('calmar_ratio', 0):.2f}")
        
        # Trade analysis
        trades = analysis.get('trade_analysis', {})
        if trades:
            report.append("\nTRADE ANALYSIS:")
            report.append(f"Total Trades: {trades.get('total_trades', 0)}")
            report.append(f"Buy Trades: {trades.get('buy_trades', 0)}")
            report.append(f"Sell Trades: {trades.get('sell_trades', 0)}")
            report.append(f"Avg Trade Size: ${trades.get('avg_trade_size', 0):,.2f}")
        
        return "\n".join(report)
    
    def plot_performance(self, results: Dict[str, Any], save_path: Optional[str] = None):
        """Create performance visualization plots"""
        equity_curve = results.get('equity_curve', pd.DataFrame())
        if equity_curve.empty:
            return
        
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        
        # Equity curve
        axes[0, 0].plot(equity_curve.index, equity_curve['total_value'])
        axes[0, 0].set_title('Portfolio Value Over Time')
        axes[0, 0].set_ylabel('Portfolio Value ($)')
        axes[0, 0].grid(True)
        
        # Returns distribution
        returns = equity_curve['total_value'].pct_change().dropna()
        axes[0, 1].hist(returns, bins=50, alpha=0.7)
        axes[0, 1].set_title('Returns Distribution')
        axes[0, 1].set_xlabel('Returns')
        axes[0, 1].set_ylabel('Frequency')
        axes[0, 1].grid(True)
        
        # Drawdown
        peak = equity_curve['total_value'].expanding().max()
        drawdown = (equity_curve['total_value'] - peak) / peak
        axes[1, 0].fill_between(drawdown.index, drawdown, 0, alpha=0.3, color='red')
        axes[1, 0].set_title('Drawdown')
        axes[1, 0].set_ylabel('Drawdown (%)')
        axes[1, 0].grid(True)
        
        # Monthly returns heatmap
        monthly_returns = returns.resample('ME').apply(lambda x: (1 + x).prod() - 1)
        monthly_returns_pivot = monthly_returns.groupby([monthly_returns.index.year, 
                                                       monthly_returns.index.month]).first()
        monthly_returns_pivot = monthly_returns_pivot.unstack()
        
        sns.heatmap(monthly_returns_pivot, annot=True, fmt='.2%', cmap='RdYlGn', 
                   center=0, ax=axes[1, 1])
        axes[1, 1].set_title('Monthly Returns Heatmap')
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        plt.show() 