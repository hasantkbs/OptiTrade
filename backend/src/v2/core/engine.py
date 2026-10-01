import asyncio
import json
import logging
import time
import pandas as pd
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from core.analysis_presentation import to_directional_score
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
    applicable) - kept local rather than imported from `core`.

    Note on the "no core dependency" invariant this comment used to
    describe: as of the gap-analysis.md section 1 superseded-note,
    `TradingEngineV2.analyze()` below now defers its headline decision
    to `decision_engine` (which itself imports `core.structured_logging`
    for its own logging) - so v2 does have a transitive dependency on
    `core` now, by design, specifically to stop being an independent
    decision authority. This particular helper stays local regardless:
    it is v2's own log shape, not something that needs to move just
    because the isolation it once helped illustrate no longer holds.
    Never pass free-text narrative through `extra_fields` - structured/
    numeric values only."""
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
    def __init__(self, indicators: List[BaseIndicator], decision_engine: Optional[Any] = None):
        self.indicators = indicators
        self.fusion = SignalFusion()
        self.risk_manager = RiskManager()
        # Only needs `.decide(symbol) -> DecisionOutput` - see
        # `core.hybrid_engine.HybridTradingEngine`'s own identical note
        # for why this stays untyped `Any` rather than a new Protocol.
        # Unlike that class, resolving the shared default here MUST stay
        # deferred to `analyze()` rather than happening in `__init__`:
        # `v2/api/router.py` constructs its module-level `TradingEngineV2`
        # singleton at import time (`main.py` imports that router before
        # its own `startup_event`/`schema_init_lock` ever run), so eagerly
        # calling `get_default_decision_engine()` here would try to wire
        # up the Feature Store/engine registry before the app has
        # finished its own startup sequence. `None` here just means "use
        # the default on first analyze() call", not "no engine".
        self.decision_engine = decision_engine

    async def analyze(self, symbol: str, data: pd.DataFrame) -> EngineResult:
        _started_at = time.perf_counter()
        tasks = [ind.calculate(data) for ind in self.indicators]
        indicator_results = await asyncio.gather(*tasks)

        risk_score = self.risk_manager.calculate_risk(data, indicator_results)

        # The Decision Engine is the single decision authority (see
        # gap-analysis.md section 1's superseded-note) - this engine's
        # own indicators still compute `signals` below (the detailed
        # per-indicator breakdown clients render), but the headline
        # aggregated_score/confidence that actually encode BUY/SELL/HOLD
        # now come from there, not from this engine's own SignalFusion.
        # A Decision Engine failure (infra down, zero valid votes) falls
        # back to this engine's own fusion so a hiccup there never turns
        # into a hard failure for this endpoint.
        try:
            decision_engine = self.decision_engine
            if decision_engine is None:
                from decision_engine.service import get_default_decision_engine

                decision_engine = get_default_decision_engine()
            decision_output = await asyncio.to_thread(decision_engine.decide, symbol, strict=True)
            aggregated_score, confidence = to_directional_score(decision_output)
        except Exception as exc:
            _log_structured_event(
                operation="canonical_decision", status="error", symbol=symbol,
                error_type=type(exc).__name__, level=logging.ERROR,
            )
            aggregation = self.fusion.aggregate(indicator_results)
            aggregated_score, confidence = aggregation["score"], aggregation["confidence"]

        _log_structured_event(
            operation="analyze",
            status="success",
            symbol=symbol,
            execution_time_ms=(time.perf_counter() - _started_at) * 1000,
            aggregated_score=aggregated_score,
            confidence=confidence,
            risk_score=risk_score,
        )
        return EngineResult(
            symbol=symbol,
            aggregated_score=aggregated_score,
            confidence=confidence,
            signals=indicator_results,
            risk_score=risk_score,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
