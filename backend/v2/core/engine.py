import asyncio
import json
import logging
import time
import pandas as pd
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from v2.indicators.base import BaseIndicator
from v2.models.schemas import EngineResult, IndicatorOutput, SignalSide
from v2.ml.predictor import MLPredictorV2

logger = logging.getLogger(__name__)


def _log_structured_event(
    *,
    operation: str,
    status: str,
    symbol: Optional[str] = None,
    execution_time_ms: Optional[float] = None,
    error_type: Optional[str] = None,
    level: int = logging.INFO,
    **extra_fields: Any,
) -> None:
    """Emits one machine-readable, structured JSON log event for the v2
    engine. A local copy of the same field schema used by
    core.structured_logging.log_event (timestamp, component, module,
    operation, status, symbol/execution_time_ms/error_type where
    applicable) - kept local rather than imported from `core` so that
    `v2` does not gain a new dependency on `core` (v2 has never imported
    from core anywhere else; this preserves that existing independence
    between the two currently-separate engines, per
    docs/architecture/gap-analysis.md section 1). Never pass free-text
    narrative through `extra_fields` - structured/numeric values only."""
    record: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "component": "v2_engine",
        "module": "v2.core.engine",
        "operation": operation,
        "status": status,
    }
    if symbol is not None:
        record["symbol"] = symbol
    if execution_time_ms is not None:
        record["execution_time_ms"] = round(execution_time_ms, 3)
    if error_type is not None:
        record["error_type"] = error_type
    record.update(extra_fields)
    logger.log(level, json.dumps(record, default=str))

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
        _started_at = time.perf_counter()
        tasks = [ind.calculate(data) for ind in self.indicators]
        indicator_results = await asyncio.gather(*tasks)

        aggregation = self.fusion.aggregate(indicator_results)
        risk_score = self.risk_manager.calculate_risk(data, indicator_results)

        _log_structured_event(
            operation="analyze",
            status="success",
            symbol=symbol,
            execution_time_ms=(time.perf_counter() - _started_at) * 1000,
            aggregated_score=aggregation["score"],
            confidence=aggregation["confidence"],
            risk_score=risk_score,
        )
        return EngineResult(
            symbol=symbol,
            aggregated_score=aggregation["score"],
            confidence=aggregation["confidence"],
            signals=indicator_results,
            risk_score=risk_score,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
