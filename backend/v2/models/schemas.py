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
