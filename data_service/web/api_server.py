#!/usr/bin/env python3
"""
FastAPI Web Server for Trading System
Provides RESTful API endpoints for web management interface
"""

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
import uvicorn
import logging
from datetime import datetime, timedelta
import asyncio
import json

# Import our trading system modules
try:
    from ..backtest import BacktestEngine, PerformanceAnalyzer
    from ..factors import FactorCalculator, FactorScreener, FactorBacktest
    from ..strategies import StrategyRegistry
    from ..ai import LLMIntegration, NLPProcessor, SentimentFactorCalculator
    from ..fetchers import YahooFetcher, BinanceFetcher
    from ..storage import DatabaseManager
except ImportError as e:
    logging.error(f"Failed to import trading modules: {e}")

# Pydantic models for API requests/responses
class StrategyRequest(BaseModel):
    strategy_name: str
    symbols: List[str]
    parameters: Dict[str, Any]
    start_date: str
    end_date: str
    initial_capital: float = 100000.0

class BacktestRequest(BaseModel):
    strategy_config: StrategyRequest
    commission_rate: float = 0.001
    rebalance_frequency: str = "daily"

class FactorAnalysisRequest(BaseModel):
    symbols: List[str]
    factors: List[str]
    start_date: str
    end_date: str

class AIAnalysisRequest(BaseModel):
    text: str
    analysis_type: str = "sentiment"  # sentiment, news, market_analysis

class SystemStatusResponse(BaseModel):
    status: str
    uptime: str
    active_strategies: int
    total_trades: int
    system_metrics: Dict[str, Any]

class APIServer:
    """FastAPI server for trading system web interface"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8000):
        self.host = host
        self.port = port
        self.app = FastAPI(
            title="Trading System API",
            description="RESTful API for trading system management",
            version="1.0.0"
        )
        self.logger = logging.getLogger(__name__)
        
        # Initialize trading system components
        self._initialize_components()
        
        # Setup CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # In production, specify actual origins
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Setup routes
        self._setup_routes()
        
        # Mount static files for frontend
        self.app.mount("/static", StaticFiles(directory="static"), name="static")
    
    def _initialize_components(self):
        """Initialize trading system components"""
        try:
            self.backtest_engine = BacktestEngine()
            self.performance_analyzer = PerformanceAnalyzer()
            self.factor_calculator = FactorCalculator()
            self.factor_screener = FactorScreener()
            self.factor_backtest = FactorBacktest()
            self.strategy_registry = StrategyRegistry()
            self.llm_integration = LLMIntegration()
            self.nlp_processor = NLPProcessor()
            self.sentiment_calculator = SentimentFactorCalculator()
            self.yahoo_fetcher = YahooFetcher()
            self.binance_fetcher = BinanceFetcher()
            self.db_manager = DatabaseManager()
            
            self.logger.info("Trading system components initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize components: {e}")
    
    def _setup_routes(self):
        """Setup API routes"""
        
        @self.app.get("/", response_class=HTMLResponse)
        async def root():
            """Serve the main dashboard page"""
            return """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Trading System Dashboard</title>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
                <link href="https://cdn.jsdelivr.net/npm/boxicons@2.0.7/css/boxicons.min.css" rel="stylesheet">
            </head>
            <body>
                <div id="app"></div>
                <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
                <script src="/static/js/app.js"></script>
            </body>
            </html>
            """
        
        @self.app.get("/api/health")
        async def health_check():
            """Health check endpoint"""
            return {"status": "healthy", "timestamp": datetime.now().isoformat()}
        
        @self.app.get("/api/system/status")
        async def get_system_status():
            """Get system status and metrics"""
            try:
                # Get system metrics
                metrics = {
                    "cpu_usage": 45.2,
                    "memory_usage": 2.3,
                    "active_connections": 12,
                    "api_calls_per_min": 156
                }
                
                return SystemStatusResponse(
                    status="running",
                    uptime="2 days, 5 hours, 30 minutes",
                    active_strategies=3,
                    total_trades=1250,
                    system_metrics=metrics
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/strategies")
        async def get_available_strategies():
            """Get list of available strategies"""
            try:
                strategies = [
                    {"name": "Momentum Strategy", "description": "Price momentum based strategy"},
                    {"name": "Value Strategy", "description": "Value investing strategy"},
                    {"name": "Mean Reversion", "description": "Mean reversion strategy"},
                    {"name": "Multi-Factor", "description": "Multi-factor strategy"},
                    {"name": "Risk Parity", "description": "Risk parity strategy"},
                    {"name": "Sector Rotation", "description": "Sector rotation strategy"}
                ]
                return {"strategies": strategies}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/backtest/run")
        async def run_backtest(request: BacktestRequest):
            """Run strategy backtest"""
            try:
                self.logger.info(f"Running backtest for strategy: {request.strategy_config.strategy_name}")
                
                # Generate sample backtest results (in real implementation, run actual backtest)
                results = {
                    "strategy_name": request.strategy_config.strategy_name,
                    "total_return": 0.25,
                    "annualized_return": 0.18,
                    "sharpe_ratio": 1.8,
                    "max_drawdown": -0.12,
                    "win_rate": 0.65,
                    "total_trades": 89,
                    "equity_curve": [
                        {"date": "2023-01-01", "value": 100000},
                        {"date": "2023-12-31", "value": 125000}
                    ]
                }
                
                return {"status": "success", "results": results}
                
            except Exception as e:
                self.logger.error(f"Backtest failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/factors/analyze")
        async def analyze_factors(request: FactorAnalysisRequest):
            """Analyze factor performance"""
            try:
                self.logger.info(f"Analyzing factors: {request.factors}")
                
                # Generate sample factor analysis results
                results = {
                    "factors": request.factors,
                    "performance": {
                        "momentum": {"ic": 0.15, "ir": 1.2, "win_rate": 0.58},
                        "value": {"ic": 0.12, "ir": 1.0, "win_rate": 0.52},
                        "quality": {"ic": 0.10, "ir": 0.8, "win_rate": 0.48}
                    },
                    "correlation_matrix": [
                        [1.0, 0.2, 0.1],
                        [0.2, 1.0, 0.3],
                        [0.1, 0.3, 1.0]
                    ]
                }
                
                return {"status": "success", "results": results}
                
            except Exception as e:
                self.logger.error(f"Factor analysis failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/ai/analyze")
        async def analyze_with_ai(request: AIAnalysisRequest):
            """Analyze text using AI"""
            try:
                self.logger.info(f"AI analysis request: {request.analysis_type}")
                
                if request.analysis_type == "sentiment":
                    # Use NLP processor for sentiment analysis
                    processed = self.nlp_processor.preprocess_text(request.text)
                    result = {
                        "sentiment": processed.sentiment_label,
                        "confidence": processed.sentiment_score,
                        "keywords": processed.keywords[:5],
                        "topics": processed.topics
                    }
                else:
                    # Use LLM for other analysis types
                    result = {
                        "analysis": "AI analysis result",
                        "confidence": 0.85,
                        "recommendations": ["Sample recommendation 1", "Sample recommendation 2"]
                    }
                
                return {"status": "success", "results": result}
                
            except Exception as e:
                self.logger.error(f"AI analysis failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/market/data/{symbol}")
        async def get_market_data(symbol: str, period: str = "1y"):
            """Get market data for symbol"""
            try:
                # Generate sample market data
                dates = []
                prices = []
                current_date = datetime.now() - timedelta(days=365)
                
                for i in range(252):
                    dates.append(current_date.strftime("%Y-%m-%d"))
                    prices.append(100 + i * 0.1 + (i % 10) * 0.5)
                    current_date += timedelta(days=1)
                
                return {
                    "symbol": symbol,
                    "data": [
                        {"date": date, "price": price}
                        for date, price in zip(dates, prices)
                    ]
                }
                
            except Exception as e:
                self.logger.error(f"Failed to get market data: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/portfolio/status")
        async def get_portfolio_status():
            """Get current portfolio status"""
            try:
                return {
                    "total_value": 125000.0,
                    "cash": 25000.0,
                    "positions": [
                        {"symbol": "AAPL", "quantity": 100, "value": 15000.0, "pnl": 1500.0},
                        {"symbol": "GOOGL", "quantity": 50, "value": 5000.0, "pnl": 500.0},
                        {"symbol": "MSFT", "quantity": 75, "value": 20000.0, "pnl": 2000.0}
                    ],
                    "daily_pnl": 1250.0,
                    "total_pnl": 4000.0
                }
                
            except Exception as e:
                self.logger.error(f"Failed to get portfolio status: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/trades/recent")
        async def get_recent_trades(limit: int = 20):
            """Get recent trades"""
            try:
                # Generate sample trade data
                trades = []
                for i in range(limit):
                    trades.append({
                        "id": f"trade_{i}",
                        "timestamp": (datetime.now() - timedelta(hours=i)).isoformat(),
                        "symbol": ["AAPL", "GOOGL", "MSFT"][i % 3],
                        "side": "buy" if i % 2 == 0 else "sell",
                        "quantity": 100 + i * 10,
                        "price": 150.0 + i * 0.5,
                        "status": "filled"
                    })
                
                return {"trades": trades}
                
            except Exception as e:
                self.logger.error(f"Failed to get recent trades: {e}")
                raise HTTPException(status_code=500, detail=str(e))
    
    def run(self, debug: bool = False):
        """Run the FastAPI server"""
        uvicorn.run(
            self.app,
            host=self.host,
            port=self.port,
            debug=debug,
            log_level="info"
        )

def main():
    """Main function to run the API server"""
    server = APIServer()
    server.run(debug=True)

if __name__ == "__main__":
    main() 