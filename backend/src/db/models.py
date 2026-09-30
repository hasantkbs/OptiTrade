"""
SQLAlchemy 2.x ORM models.

Tables
------
analysis_predictions
    Stores every /analyze result.  Tracks prediction, confidence,
    indicator snapshot, and (once updated by a background job) the
    actual outcome and accuracy.

ohlcv_data
    OHLCV candlestick cache.  Declared as a TimescaleDB hypertable in
    the Alembic migration; falls back to a plain table if the extension
    is not present.
"""
import uuid
from sqlalchemy import Column, DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class AnalysisPrediction(Base):
    __tablename__ = "analysis_predictions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol         = Column(String(20),  nullable=False)
    asset_type     = Column(String(20),  nullable=False)
    score          = Column(Integer,     nullable=False)
    decision_code  = Column(String(20),  nullable=False)
    confidence_pct = Column(Float,       nullable=True)

    indicators_json        = Column(JSONB, nullable=True)
    scoring_breakdown_json = Column(JSONB, nullable=True)
    long_signals           = Column(JSONB, nullable=True)
    short_signals          = Column(JSONB, nullable=True)

    predicted_at               = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    actual_price_at_prediction = Column(Float, nullable=True)
    actual_price_1d            = Column(Float, nullable=True)
    actual_price_7d            = Column(Float, nullable=True)
    actual_price_30d           = Column(Float, nullable=True)

    # Updated by a background reconciliation job
    actual_outcome      = Column(String(20), nullable=True)  # CORRECT|INCORRECT|PARTIAL
    prediction_accuracy = Column(Float,      nullable=True)  # 0.0 – 1.0

    __table_args__ = (
        Index("ix_ap_symbol",       "symbol"),
        Index("ix_ap_predicted_at", "predicted_at"),
        Index("ix_ap_symbol_time",  "symbol", "predicted_at"),
    )


class OHLCVData(Base):
    """
    OHLCV candlestick cache.

    Converted to a TimescaleDB hypertable (partitioned on `time`) by the
    initial Alembic migration.  Falls back to a plain composite-PK table
    when TimescaleDB is not installed.
    """
    __tablename__ = "ohlcv_data"

    time   = Column(DateTime(timezone=True), primary_key=True)
    symbol = Column(String(20),              primary_key=True)
    open   = Column(Float, nullable=False)
    high   = Column(Float, nullable=False)
    low    = Column(Float, nullable=False)
    close  = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
