# 🚀 Quantitative Trading System

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-brightgreen.svg)](https://github.com/yourusername/tradingsystem)

> **A comprehensive quantitative trading system with AI-powered analysis, real-time data processing, and advanced risk management**

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Usage Examples](#usage-examples)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

## 🎯 Overview

This is a production-ready quantitative trading system that combines traditional financial analysis with cutting-edge AI/ML technologies. The system provides a complete pipeline from data collection to strategy execution, featuring real-time market data processing, advanced factor analysis, AI-powered sentiment analysis, and comprehensive risk management.

### 🌟 Key Highlights

- **🔬 Advanced Factor Analysis**: Multi-factor models with momentum, value, quality, and volatility factors
- **🤖 AI/LLM Integration**: OpenAI GPT integration for market analysis and strategy recommendations
- **📊 Real-time Data**: WebSocket-based real-time market data from multiple exchanges
- **🎯 Strategy Framework**: Extensible strategy system with 8+ built-in quantitative strategies
- **⚡ High Performance**: C++ core engine for low-latency order execution
- **📈 Visualization**: Interactive dashboards with Plotly and Streamlit
- **🛡️ Risk Management**: Comprehensive risk controls and portfolio management

## ✨ Features

### 📊 Data Management
- **Multi-source Data**: Binance, Yahoo Finance, Alpha Vantage
- **Real-time Streaming**: WebSocket connections for live market data
- **Data Processing**: Automated data cleaning and feature engineering
- **Storage**: SQLite, PostgreSQL, and Redis caching support

### 🧠 AI & Machine Learning
- **LLM Integration**: OpenAI GPT for market analysis and insights
- **NLP Processing**: Sentiment analysis of news and social media
- **ML Models**: XGBoost, Random Forest, Neural Networks
- **Feature Engineering**: Technical indicators and statistical features

### 📈 Quantitative Analysis
- **Factor Models**: Momentum, Value, Quality, Size, Volatility factors
- **Stock Screening**: Multi-factor stock selection and filtering
- **Portfolio Optimization**: Risk parity and mean-variance optimization
- **Performance Analysis**: Comprehensive backtesting and metrics

### 🎮 Strategy Framework
- **Extensible Design**: Easy to add custom strategies
- **Built-in Strategies**: 8+ proven quantitative strategies
- **Strategy Registry**: Centralized strategy management
- **Parameter Optimization**: Automated strategy optimization

### 🛡️ Risk Management
- **Position Sizing**: Dynamic position sizing algorithms
- **Risk Limits**: VaR, CVaR, drawdown, and leverage limits
- **Portfolio Management**: Real-time portfolio monitoring
- **Alert System**: Price and risk alerts

### 🖥️ User Interfaces
- **Web Dashboard**: FastAPI-based web interface
- **Streamlit App**: Interactive data science dashboard
- **Real-time Charts**: K-line charts with technical indicators
- **Mobile Friendly**: Responsive design for all devices

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Python Layer (data_service/)             │
├─────────────────────────────────────────────────────────────┤
│  • Data Fetchers     • Strategy Framework    • AI/ML       │
│  • Factor Analysis   • Backtesting Engine    • Visualization│
│  • Storage Layer     • Real-time Data        • Web UI      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    C++ Core Engine (backend/)               │
├─────────────────────────────────────────────────────────────┤
│  • Order Execution   • Risk Management       • Portfolio   │
│  • Data Loading      • Strategy Engine       • Performance │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/tradingsystem.git
cd tradingsystem
```

### 2. Install Dependencies
```bash
# Install all features
pip install -e .[ai,visualization,realtime,web]

# Or install specific features
pip install -e .[ai]           # AI/ML features
pip install -e .[visualization] # Charts and dashboards
pip install -e .[realtime]      # Real-time data
pip install -e .[web]          # Web interface
```

### 3. Run Basic Example
```bash
# Test data fetching (no API keys required)
python examples/fetch_public_data.py
```

### 4. Launch Dashboard
```bash
# Start Streamlit dashboard
python run_dashboard.py
# Visit: http://localhost:8501

# Or start web interface
python run_web_interface.py
# Visit: http://localhost:8000
```

## 📦 Installation

### Prerequisites
- Python 3.8+
- C++17 compatible compiler (for backend)
- CMake 3.12+ (for backend)

### Full Installation
```bash
# 1. Clone repository
git clone https://github.com/yourusername/tradingsystem.git
cd tradingsystem

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install Python dependencies
pip install -e .[ai,visualization,realtime,web]

# 4. Build C++ backend (optional)
cd backend
mkdir build && cd build
cmake ..
make -j4
cd ../..

# 5. Configure API keys (optional)
cp config.example.json config.json
# Edit config.json with your API keys
```

### API Keys (Optional)
For full functionality, you can add API keys to `config.json`:
```json
{
  "binance": {
    "api_key": "your_binance_api_key",
    "secret_key": "your_binance_secret"
  },
  "openai": {
    "api_key": "your_openai_api_key"
  },
  "alpha_vantage": {
    "api_key": "your_alpha_vantage_key"
  }
}
```

## 💡 Usage Examples

### Basic Data Fetching
```python
from data_service.fetchers import BinanceFetcher

# Get cryptocurrency data (no API key required)
fetcher = BinanceFetcher()
btc_price = fetcher.get_current_price("BTCUSD")
print(f"BTC Price: ${btc_price:,.2f}")
```

### Factor Analysis
```python
from data_service.factors import FactorCalculator, FactorScreener

# Calculate factors for a symbol (prices/volumes are pandas Series)
calculator = FactorCalculator()
factors = calculator.calculate_all_factors(symbol, prices, volumes)

# Screen a cross-sectional factor table (rows = symbols, cols = factors)
screener = FactorScreener().create_momentum_screener(min_momentum=10.0)
results = screener.screen_stocks(factor_data)
```

### Strategy Framework (cross-sectional stock selection)
```python
from data_service.strategies import StrategyRunner
from data_service.strategies.builtin_strategies import register_builtin_strategies

register_builtin_strategies()
runner = StrategyRunner()
# factor_data / price_data are cross-sectional DataFrames (rows = symbols)
result = runner.run_strategy(
    "MomentumStrategy", factor_data=factor_data, price_data=price_data,
    parameters={"top_n": 20, "min_momentum": 5.0},
)
print(result.selected_stocks, result.weights)
```

### Strategy Backtesting (time-series)
```python
from data_service.backtest import BacktestEngine

# The strategy is a callback invoked as strategy_func(data, engine, **params);
# inside it you iterate over `data` and call engine.place_order(...).
def sma_crossover(data, engine, fast=5, slow=20):
    ma_fast = data["close"].rolling(fast).mean()
    ma_slow = data["close"].rolling(slow).mean()
    holding = False
    for ts, row in data.iterrows():
        if ma_fast.loc[ts] > ma_slow.loc[ts] and not holding:
            qty = (engine.current_capital * 0.95) / row["close"]
            holding = engine.place_order("SYM", "buy", qty, row["close"], ts)
        elif ma_fast.loc[ts] < ma_slow.loc[ts] and holding:
            pos = engine.get_current_positions().get("SYM")
            if pos and engine.place_order("SYM", "sell", pos.quantity, row["close"], ts):
                holding = False

engine = BacktestEngine(initial_capital=100000)
results = engine.run_backtest(historical_data, sma_crossover, {"fast": 5, "slow": 20})
```

> The **strategy framework** (`StrategyRunner`) selects a basket of stocks from
> cross-sectional factor data; the **`BacktestEngine`** runs a time-series
> callback over OHLCV data. They are different abstractions — see `USAGE.md`
> §7–§8 for the full, verified guide.

### AI-Powered Analysis
```python
from data_service.ai import LLMIntegration

# Get AI insights (market_data is an OHLCV DataFrame)
llm = LLMIntegration(provider="openai")
analysis = llm.analyze_market_data(market_data, symbols=["AAPL"])
print(f"AI Recommendation: {analysis.content}")
```

## 📚 Documentation

> 📖 **[USAGE.md](USAGE.md)** is the single, verified, runnable guide to every
> module — every snippet there is checked against the real code signatures.

### Module Documentation
- [📊 Factor Analysis](README_Factor_Analysis.md) - Multi-factor models and stock screening
- [🤖 AI & LLM Integration](README_AI_Modules.md) - AI-powered market analysis
- [🎯 Quantitative Strategies](README_Quantitative_Strategies.md) - Trading strategies guide
- [🌐 Web Interface](README_Web_Interface.md) - Web dashboard usage
- [🔗 LangChain Integration](README_LangChain_LLM.md) - Advanced LLM features

### Examples
- `examples/fetch_public_data.py` - Basic data fetching
- `examples/quantitative_strategies.py` - Strategy examples
- `examples/factor_analysis_demo.py` - Factor analysis demo
- `examples/llm_nlp_complete_demo.py` - AI features demo

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test modules
pytest tests/test_data_processor.py -v
pytest tests/test_llm_integration.py -v
```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup
```bash
# Install development dependencies
pip install -e .[test,dev]

# Run tests
pytest tests/ -v

# Run linting
flake8 data_service/
black data_service/
```

### Code Style
- Follow PEP 8 for Python code
- Use type hints
- Add docstrings for all functions
- Write tests for new features

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

This software is for educational and research purposes only. Trading involves substantial risk of loss and is not suitable for all investors. Past performance does not guarantee future results. Please consult with a financial advisor before making any investment decisions.

## 🙏 Acknowledgments

- [Binance API](https://binance-docs.github.io/apidocs/) for cryptocurrency data
- [Yahoo Finance](https://finance.yahoo.com/) for stock market data
- [OpenAI](https://openai.com/) for AI capabilities
- [Streamlit](https://streamlit.io/) for dashboard framework
- [FastAPI](https://fastapi.tiangolo.com/) for web framework



<div align="center">
  <p>Made with ❤️ by the Quantitative Trading Community</p>
  <p>
    <a href="https://github.com/yourusername/tradingsystem/stargazers">
      <img src="https://img.shields.io/github/stars/yourusername/tradingsystem" alt="Stars">
    </a>
    <a href="https://github.com/yourusername/tradingsystem/network">
      <img src="https://img.shields.io/github/forks/yourusername/tradingsystem" alt="Forks">
    </a>
    <a href="https://github.com/yourusername/tradingsystem/issues">
      <img src="https://img.shields.io/github/issues/yourusername/tradingsystem" alt="Issues">
    </a>
  </p>
</div> 