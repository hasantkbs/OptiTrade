import asyncio
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import List
from v2.core.engine import TradingEngineV2
from v2.indicators.volume.vwap import VWAPIndicator
from v2.indicators.trend.ema import EMAIndicator
from v2.indicators.ict.killzones import KillzoneIndicator
from v2.indicators.ict.fvg import FVGIndicator
from v2.indicators.ict.market_structure import MarketStructureIndicator
from v2.indicators.levels.pivots import PivotPointsIndicator
from v2.models.schemas import BacktestPoint

async def run_v2_backtest_history(symbol: str, days: int = 60) -> List[BacktestPoint]:
    """
    Runs V2 engine analysis on historical data to generate a signal timeline.
    Returns: List of points with price, signal, score, and equity.
    """
    # Initialize V2 Engine
    engine = TradingEngineV2([
        VWAPIndicator(weight=1.2),
        EMAIndicator(fast=20, slow=50, weight=1.0),
        KillzoneIndicator(weight=1.3),
        FVGIndicator(weight=1.4),
        MarketStructureIndicator(weight=1.5),
        PivotPointsIndicator(weight=1.0)
    ])

    # Fetch 1h data for backtest - yfinance does synchronous HTTP under
    # the hood, so this must be dispatched off the event-loop thread
    # (asyncio.to_thread), same as v2/api/router.py's own fetches.
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days + 15) # Buffer for indicators

    data = await asyncio.to_thread(
        lambda: yf.Ticker(symbol).history(start=start_date, end=end_date, interval="1h")
    )
    if data.empty:
        return []

    results = []
    equity = 1000.0 # Virtual starting capital
    position = 0 # 0: None, 1: Long, -1: Short
    entry_price = 0.0

    # We skip the first few rows to let indicators stabilize
    lookback = 40 
    
    for i in range(lookback, len(data)):
        window = data.iloc[:i+1]
        ts = window.index[-1]
        current_p = float(window["Close"].iloc[-1])
        
        # Run analysis
        analysis = await engine.analyze(symbol, window)
        score = analysis.aggregated_score
        
        # Signal logic
        signal = "NEUTRAL"
        if score >= 0.25: signal = "BUY"
        elif score <= -0.25: signal = "SELL"
        
        # P&L calculation for equity curve
        if position == 1:
            equity += (current_p - entry_price) * (equity / entry_price) * 0.1 # 10% risk
            entry_price = current_p
        elif position == -1:
            equity += (entry_price - current_p) * (equity / entry_price) * 0.1
            entry_price = current_p

        # Execution (simple)
        if signal == "BUY" and position <= 0:
            position = 1
            entry_price = current_p
        elif signal == "SELL" and position >= 0:
            position = -1
            entry_price = current_p
            
        results.append(BacktestPoint(
            timestamp=ts.isoformat(),
            price=round(current_p, 4),
            score=round(score, 3),
            signal=signal,
            equity=round(equity, 2),
        ))

    return results
