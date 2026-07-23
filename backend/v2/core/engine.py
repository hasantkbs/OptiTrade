import asyncio
import pandas as pd
from typing import List, Dict
from datetime import datetime
from v2.indicators.base import BaseIndicator
from v2.models.schemas import EngineResult, IndicatorOutput, SignalSide
from v2.ml.predictor import MLPredictorV2

class SignalFusion:
    def __init__(self):
        pass

    def aggregate(self, results: List[IndicatorOutput]) -> Dict[str, float]:
        """Weighted aggregation of indicator scores."""
        total_score = 0.0
        total_confidence = 0.0
        
        for res in results:
            # We can also use pre-defined weights if needed
            # For now, we use the confidence provided by the indicator
            total_score += res.score * res.confidence
            total_confidence += res.confidence
            
        if total_confidence == 0:
            return {"score": 0.0, "confidence": 0.0}
            
        aggregated_score = total_score / total_confidence
        return {
            "score": float(aggregated_score),
            "confidence": float(total_confidence / len(results)) # Average confidence
        }

class RiskManager:
    def calculate_risk(self, data: pd.DataFrame, signals: List[IndicatorOutput]) -> float:
        """Calculate a risk score between 0 and 1."""
        # 1. Volatility check (ATR vs Price)
        high_low = (data['High'] - data['Low']).mean()
        price = data['Close'].iloc[-1]
        vol_risk = min(1.0, (high_low / price) * 50) # Normalized
        
        # 2. Disagreement risk
        sides = [s.side for s in signals if s.side != SignalSide.NEUTRAL]
        if not sides:
            agreement_risk = 0.0
        else:
            buy_count = sides.count(SignalSide.BUY)
            sell_count = sides.count(SignalSide.SELL)
            agreement_risk = 1.0 - (abs(buy_count - sell_count) / len(sides))
            
        # Combine
        return (vol_risk * 0.4) + (agreement_risk * 0.6)

class TradingEngineV2:
    def __init__(self, indicators: List[BaseIndicator]):
        self.indicators = indicators
        self.fusion = SignalFusion()
        self.risk_manager = RiskManager()

    async def analyze(self, symbol: str, data: pd.DataFrame) -> EngineResult:
        tasks = [ind.calculate(data) for ind in self.indicators]
        indicator_results = await asyncio.gather(*tasks)
        
        aggregation = self.fusion.aggregate(indicator_results)
        risk_score = self.risk_manager.calculate_risk(data, indicator_results)
        
        return EngineResult(
            symbol=symbol,
            aggregated_score=aggregation["score"],
            confidence=aggregation["confidence"],
            signals=indicator_results,
            risk_score=risk_score,
            timestamp=datetime.now().isoformat()
        )
