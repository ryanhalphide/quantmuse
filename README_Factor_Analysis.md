# Quantitative Factor Analysis Module

This module provides comprehensive tools for quantitative factor analysis, including factor calculation, screening, backtesting, stock selection, and optimization.

## Overview

The quantitative factor analysis module consists of five main components:

1. **FactorCalculator** - Calculate various quantitative factors
2. **FactorScreener** - Screen and filter stocks based on factors
3. **FactorBacktest** - Backtest factor performance
4. **StockSelector** - Implement stock selection strategies
5. **FactorOptimizer** - Optimize factor weights and parameters

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

```python
from data_service.factors import FactorCalculator, FactorScreener, FactorBacktest

# Initialize components
factor_calculator = FactorCalculator()
factor_screener = FactorScreener()
factor_backtest = FactorBacktest()

# Calculate factors
factors = factor_calculator.calculate_all_factors(symbol, prices, volumes, financial_data)

# Screen stocks (params optional; defaults shown)
screener = factor_screener.create_momentum_screener(
    min_momentum=10.0, min_volume_momentum=5.0
)
results = screener.screen_stocks(factor_data)

# Backtest factor
backtest_result = factor_backtest.run_factor_backtest(factor_data, price_data)
```

## Components

### 1. FactorCalculator

Calculates various quantitative factors from market data.

#### Supported Factor Categories

- **Momentum Factors**
  - Price momentum (20d, 60d, 252d)
  - Volume momentum
  - Relative strength vs market

- **Value Factors**
  - P/E ratio
  - P/B ratio
  - P/S ratio
  - Dividend yield
  - EV/EBITDA

- **Quality Factors**
  - ROE (Return on Equity)
  - ROA (Return on Assets)
  - Debt to Equity ratio
  - Current ratio
  - Gross margin
  - Operating margin

- **Size Factors**
  - Market cap
  - Enterprise value

- **Volatility Factors**
  - Price volatility
  - Beta
  - Sharpe ratio
  - Maximum drawdown
  - Value at Risk (VaR)

- **Technical Factors**
  - RSI
  - MACD
  - Moving averages
  - Bollinger Bands

#### Usage

```python
from data_service.factors import FactorCalculator

calculator = FactorCalculator()

# Calculate momentum factors
momentum_factors = calculator.calculate_price_momentum(prices, periods=[20, 60, 252])

# Calculate value factors
value_factors = calculator.calculate_value_factors(financial_data)

# Calculate all factors
all_factors = calculator.calculate_all_factors(
    symbol, prices, volumes, financial_data, market_data
)
```

### 2. FactorScreener

Screens and filters stocks based on factor criteria.

#### Pre-built Screeners

- **Value Screener**
  - Low P/E ratio
  - Low P/B ratio
  - High dividend yield

- **Momentum Screener**
  - High price momentum
  - High volume momentum
  - RSI in optimal range

- **Quality Screener**
  - High ROE
  - Low debt to equity
  - High current ratio

- **Multi-Factor Screener**
  - Combines multiple factors with weights

#### Usage

```python
from data_service.factors import FactorScreener

screener = FactorScreener()

# Create value screener
value_screener = screener.create_value_screener(
    max_pe=20.0, max_pb=3.0, min_dividend_yield=2.0
)

# Create momentum screener
momentum_screener = screener.create_momentum_screener(
    min_momentum=10.0, min_volume_momentum=5.0
)

# Screen stocks
results = screener.screen_stocks(factor_data)

# Add custom filters
screener.add_market_cap_filter(min_market_cap=1000000000)  # $1B
screener.add_volatility_filter(max_volatility=30.0)
```

### 3. FactorBacktest

Backtests factor performance and calculates metrics.

#### Performance Metrics

- **Return Metrics**
  - Total return
  - Annualized return
  - Sharpe ratio
  - Win rate
  - Maximum drawdown

- **Information Coefficient (IC)**
  - IC mean and standard deviation
  - IC Information Ratio
  - Rank IC metrics

#### Usage

```python
from data_service.factors import FactorBacktest

backtest = FactorBacktest()

# Run single factor backtest
result = backtest.run_factor_backtest(
    factor_data, price_data, rebalance_frequency='monthly'
)

# Run multi-factor backtest
factor_weights = {'momentum': 0.6, 'value': 0.4}
result = backtest.run_multi_factor_backtest(
    factor_data, price_data, factor_weights
)

# Generate performance report
report = backtest.generate_performance_report(result)
print(report)

# Plot performance
backtest.plot_factor_performance(result, "factor_performance.png")
```

### 4. StockSelector

Implements various stock selection strategies.

#### Selection Methods

- **Top N Selection**
  - Select top N stocks by factor value

- **Equal Weight Selection**
  - Equal weights for selected stocks

- **Factor Weighted Selection**
  - Weights proportional to factor values

- **Risk Parity Selection**
  - Equal risk contribution

#### Usage

```python
from data_service.factors import StockSelector

selector = StockSelector(max_positions=50)

# Select top N stocks
result = selector.select_stocks(
    factor_data, price_data,
    selection_method='top_n',
    n=20,
    factor_name='momentum_20d'
)

# Update portfolio
portfolio_update = selector.update_portfolio(result, current_prices)

# Get portfolio metrics
metrics = selector.calculate_portfolio_metrics(price_data)
```

### 5. FactorOptimizer

Optimizes factor weights and parameters.

#### Optimization Methods

- **Scipy Optimization**
  - SLSQP method for constrained optimization

- **Genetic Algorithm**
  - Differential evolution for global optimization

- **Grid Search**
  - Exhaustive search over parameter grid

- **Cross-Validation**
  - Time-series cross-validation

#### Usage

```python
from data_service.factors import FactorOptimizer

optimizer = FactorOptimizer()

# Optimize factor weights
result = optimizer.optimize_factor_weights(
    factor_data, price_data,
    objective_function='sharpe_ratio',
    method='scipy'
)

# Grid search optimization
result = optimizer.grid_search_optimization(
    factor_data, price_data, factor_names
)

# Generate optimization report
report = optimizer.generate_optimization_report(result)
```

## Example Workflow

```python
import pandas as pd
from data_service.factors import *

# 1. Calculate factors
calculator = FactorCalculator()
factor_data = []
for symbol in symbols:
    factors = calculator.calculate_all_factors(symbol, prices, volumes, financial_data)
    factor_data.append(factors)

# 2. Screen stocks
screener = FactorScreener()
momentum_screener = screener.create_momentum_screener()
screening_results = momentum_screener.screen_stocks(factor_data)

# 3. Backtest factor
backtest = FactorBacktest()
backtest_result = backtest.run_factor_backtest(factor_data, price_data)

# 4. Select stocks
selector = StockSelector()
selection_result = selector.select_stocks(
    factor_data, price_data, selection_method='top_n', n=20
)

# 5. Optimize weights
optimizer = FactorOptimizer()
optimization_result = optimizer.optimize_factor_weights(
    factor_data, price_data, objective_function='sharpe_ratio'
)

# 6. Generate reports
print(backtest.generate_performance_report(backtest_result))
print(optimizer.generate_optimization_report(optimization_result))
```

## Data Requirements

### Input Data Format

**Price Data:**
```python
price_data = pd.DataFrame({
    'symbol': ['AAPL', 'GOOGL', ...],
    'date': ['2023-01-01', '2023-01-01', ...],
    'close': [150.0, 2800.0, ...],
    'volume': [1000000, 500000, ...]
})
```

**Factor Data:**
```python
factor_data = pd.DataFrame({
    'symbol': ['AAPL', 'GOOGL', ...],
    'date': ['2023-01-01', '2023-01-01', ...],
    'factor_name': ['momentum_20d', 'pe_ratio', ...],
    'factor_value': [0.05, 25.0, ...]
})
```

**Financial Data:**
```python
financial_data = {
    'price': 150.0,
    'eps': 6.0,
    'book_value_per_share': 25.0,
    'revenue_per_share': 50.0,
    'dividend_per_share': 0.88,
    'net_income': 1000000000,
    'shareholders_equity': 5000000000,
    'total_assets': 10000000000,
    'total_debt': 2000000000,
    'current_assets': 3000000000,
    'current_liabilities': 1500000000
}
```

## Performance Considerations

- **Data Size**: The module can handle large datasets but performance may degrade with very large universes
- **Memory Usage**: Factor calculations can be memory-intensive for large datasets
- **Optimization**: Use vectorized operations where possible for better performance

## Dependencies

- pandas
- numpy
- scipy
- matplotlib
- seaborn

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

This project is licensed under the MIT License. 