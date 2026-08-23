import asyncio
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from typing import List
import yfinance as yf
import pandas as pd
from datetime import datetime

from v2.core.engine import TradingEngineV2
from v2.indicators.volume.vwap import VWAPIndicator
from v2.indicators.trend.ema import EMAIndicator
from v2.indicators.ict.killzones import KillzoneIndicator
from v2.indicators.ict.fvg import FVGIndicator
from v2.indicators.ict.market_structure import MarketStructureIndicator
from v2.indicators.levels.pivots import PivotPointsIndicator
from v2.models.schemas import BacktestPoint, EngineResult, SignalSide
from v2.ml.predictor import MLPredictorV2

router = APIRouter(prefix="/v2", tags=["v2 Engine"])

# Initialize ML Predictor
ml_predictor = MLPredictorV2()

# Initialize Engine with indicators
engine = TradingEngineV2([
    VWAPIndicator(weight=1.2),
    EMAIndicator(fast=20, slow=50, weight=1.0),
    KillzoneIndicator(weight=1.3),
    FVGIndicator(weight=1.4),
    MarketStructureIndicator(weight=1.5),
    PivotPointsIndicator(weight=1.0)
])

def resolve_symbol(symbol: str) -> str:
    """Intelligently add suffixes for common markets if missing."""
    s = symbol.upper().strip()
    if s.isdigit() and len(s) == 4:
        return f"{s}.T" # Japan
    # Basic check: if it contains a dot, assume it has a suffix
    if "." in s or "-" in s:
        return s
    # Check if likely crypto
    crypto_keywords = ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE"]
    if s in crypto_keywords:
        return f"{s}-USD"
    # Default to US if not BIST-like (BIST usually ends in .IS)
    # This is simple; better lookup can be added.
    return s

def _fetch_history(symbol: str, period: str, interval: str) -> pd.DataFrame:
    """The actual blocking network call (`yfinance` does synchronous
    HTTP under the hood) - always run via `asyncio.to_thread` from an
    `async def` route, never called directly on the event-loop thread,
    the same pattern `model_serving/inference.py` and `model_serving/
    service.py` already use for their own blocking calls."""
    return yf.Ticker(symbol).history(period=period, interval=interval)


@router.get("/analyze/{symbol}", response_model=EngineResult)
async def analyze_symbol(symbol: str, period: str = "60d", interval: str = "1h"):
    try:
        resolved = resolve_symbol(symbol)
        data = await asyncio.to_thread(_fetch_history, resolved, period, interval)

        if data.empty and resolved != symbol:
            # Try original if resolved failed
            data = await asyncio.to_thread(_fetch_history, symbol, period, interval)
            resolved = symbol
            
        if data.empty:
            raise HTTPException(status_code=404, detail="Symbol not found or no data available")
            
        result = await engine.analyze(resolved, data)
        
        # Add ML Prediction
        ml_res = ml_predictor.predict(data)
        if ml_res:
            result.ml_prediction = ml_res
            
        return result
    except HTTPException:
        # Otherwise the broad `except Exception` below would re-catch
        # this (HTTPException IS an Exception) and turn a deliberate
        # 404 "symbol not found" into a misleading 500.
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from v2.core.backtest_engine import run_v2_backtest_history

@router.get("/backtest/{symbol}", response_model=List[BacktestPoint])
async def get_backtest_history(symbol: str, days: int = 30):
    try:
        resolved = resolve_symbol(symbol)
        results = await run_v2_backtest_history(resolved, days=days)
        if not results:
            raise HTTPException(status_code=404, detail="No backtest data available")
        return results
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
async def scan_symbols(symbols: List[str], interval: str = "1h"):
    results = []
    
    async def process_symbol(symbol: str):
        try:
            data = await asyncio.to_thread(_fetch_history, symbol, "60d", interval)
            if not data.empty:
                return await engine.analyze(symbol, data)
        except:
            return None

    tasks = [process_symbol(s) for s in symbols]
    processed = await asyncio.gather(*tasks)
    
    return [r for r in processed if r is not None]

@router.websocket("/ws/analyze/{symbol}")
async def websocket_analyze(websocket: WebSocket, symbol: str):
    await websocket.accept()
    try:
        while True:
            data = await asyncio.to_thread(_fetch_history, symbol, "5d", "15m")

            if not data.empty:
                result = await engine.analyze(symbol, data)
                await websocket.send_json(result.dict())
            
            await asyncio.sleep(60) 
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"error": str(e)})
            await websocket.close()
        except:
            pass
