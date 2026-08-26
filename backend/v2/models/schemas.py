from pydantic import BaseModel, Field
from typing import Dict, Optional, Any, List
from enum import Enum

class SignalSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"

class IndicatorOutput(BaseModel):
    indicator_name: str
    score: float = Field(..., ge=-1.0, le=1.0, description="Normalized score between -1 and +1")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the signal")
    side: SignalSide
    metadata: Dict[str, Any] = {}

class EngineResult(BaseModel):
    symbol: str
    aggregated_score: float
    confidence: float
    signals: List[IndicatorOutput]
    ml_prediction: Optional[Dict[str, Any]] = None
    risk_score: float
    timestamp: str

class BacktestPoint(BaseModel):
    """One point of `v2.core.backtest_engine.run_v2_backtest_history`'s
    signal timeline - was previously typed as a bare `Dict[str, Any]` in
    the `/v2/backtest/{symbol}` response_model, which gave OpenAPI (and
    any generated mobile client) no field-level schema at all. Field
    names/values are unchanged; this only makes the existing shape
    explicit."""
    timestamp: str
    price: float
    score: float
    signal: SignalSide
    equity: float
