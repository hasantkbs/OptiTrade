"""
Database repository — pure async CRUD functions.

Rules
-----
- No HTTP coupling: never import from fastapi, main, or router modules.
- Every function accepts Optional[AsyncSession] and returns a safe default
  (None / [] / False) when the session is None.
- Business logic never lives here.  This layer translates domain objects
  into SQL and vice versa.
"""
import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AnalysisPrediction, OHLCVData

logger = logging.getLogger(__name__)


async def store_prediction(
    db: Optional[AsyncSession],
    *,
    symbol: str,
    asset_type: str,
    score: int,
    decision_code: str,
    confidence_pct: Optional[float],
    indicators_json: Optional[dict],
    scoring_breakdown_json: Optional[list],
    long_signals: Optional[list],
    short_signals: Optional[list],
    actual_price_at_prediction: Optional[float],
) -> Optional[str]:
    """
    Persist an analysis prediction.  Returns the prediction UUID as a string,
    or None if the database is not available.
    """
    if db is None:
        return None
    pred = AnalysisPrediction(
        symbol=symbol.upper(),
        asset_type=asset_type,
        score=score,
        decision_code=decision_code,
        confidence_pct=confidence_pct,
        indicators_json=indicators_json,
        scoring_breakdown_json=scoring_breakdown_json,
        long_signals=long_signals,
        short_signals=short_signals,
        actual_price_at_prediction=actual_price_at_prediction,
    )
    db.add(pred)
    await db.commit()
    logger.debug("Stored prediction %s for %s (score=%d).", pred.id, symbol, score)
    return str(pred.id)


async def get_predictions(
    db: Optional[AsyncSession],
    *,
    symbol: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    Return recent predictions, optionally filtered by symbol.
    Returns [] when the database is not available.
    """
    if db is None:
        return []
    q = (
        select(AnalysisPrediction)
        .order_by(AnalysisPrediction.predicted_at.desc())
        .limit(limit)
    )
    if symbol:
        q = q.where(AnalysisPrediction.symbol == symbol.upper())
    result = await db.execute(q)
    rows = result.scalars().all()
    return [_prediction_to_dict(row) for row in rows]


async def update_prediction_outcome(
    db: Optional[AsyncSession],
    *,
    prediction_id: str,
    actual_price: float,
    actual_outcome: str,
    prediction_accuracy: float,
    price_period: str = "1d",
) -> bool:
    """
    Record the actual outcome for a stored prediction.
    `price_period` must be one of "1d", "7d", "30d".
    Returns False when the database is not available.
    """
    if db is None:
        return False
    price_col_map = {
        "1d":  "actual_price_1d",
        "7d":  "actual_price_7d",
        "30d": "actual_price_30d",
    }
    col = price_col_map.get(price_period, "actual_price_1d")

    stmt = (
        update(AnalysisPrediction)
        .where(AnalysisPrediction.id == uuid.UUID(prediction_id))
        .values(
            actual_outcome=actual_outcome.upper(),
            prediction_accuracy=float(prediction_accuracy),
            **{col: actual_price},
        )
    )
    await db.execute(stmt)
    await db.commit()
    logger.debug(
        "Updated outcome for prediction %s: %s (accuracy=%.2f).",
        prediction_id, actual_outcome, prediction_accuracy,
    )
    return True


async def get_prediction_by_id(
    db: Optional[AsyncSession],
    prediction_id: str,
) -> Optional[Dict[str, Any]]:
    """Return a single prediction dict by UUID, or None."""
    if db is None:
        return None
    result = await db.execute(
        select(AnalysisPrediction).where(
            AnalysisPrediction.id == uuid.UUID(prediction_id)
        )
    )
    row = result.scalar_one_or_none()
    return _prediction_to_dict(row) if row else None


async def store_ohlcv(
    db: Optional[AsyncSession],
    *,
    symbol: str,
    rows: List[Dict[str, Any]],
) -> int:
    """
    Bulk-insert OHLCV rows (upsert on conflict).  Returns the count inserted.
    Rows must have keys: time, open, high, low, close, volume.
    """
    if db is None or not rows:
        return 0
    stmt = pg_insert(OHLCVData).values(
        [{"symbol": symbol.upper(), **r} for r in rows]
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["time", "symbol"],
        set_={"open": stmt.excluded.open, "high": stmt.excluded.high,
              "low": stmt.excluded.low, "close": stmt.excluded.close,
              "volume": stmt.excluded.volume},
    )
    await db.execute(stmt)
    await db.commit()
    return len(rows)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _prediction_to_dict(row) -> Dict[str, Any]:
    return {
        "id":                         str(row.id),
        "symbol":                     row.symbol,
        "asset_type":                 row.asset_type,
        "score":                      row.score,
        "decision_code":              row.decision_code,
        "confidence_pct":             row.confidence_pct,
        "predicted_at":               row.predicted_at.isoformat() if row.predicted_at else None,
        "actual_price_at_prediction": row.actual_price_at_prediction,
        "actual_price_1d":            row.actual_price_1d,
        "actual_price_7d":            row.actual_price_7d,
        "actual_price_30d":           row.actual_price_30d,
        "actual_outcome":             row.actual_outcome,
        "prediction_accuracy":        row.prediction_accuracy,
        "long_signals":               row.long_signals,
        "short_signals":              row.short_signals,
    }
