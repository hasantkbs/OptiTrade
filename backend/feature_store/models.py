"""
OptiTrade Feature Store — Domain Models
==========================================
Pydantic models shared by every layer of the feature store (online store,
offline store, validation, service facade).

A single feature is uniquely identified by (symbol, feature_name,
version, event_timestamp). Each write produces one immutable,
timestamped `FeatureRecord` — the offline store is append-only, so a
point-in-time query made today returns the same answer it would have
returned on the day in question, regardless of what has been written
since.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class FeatureValue(BaseModel):
    """A single named feature value for one symbol, ready to be written."""

    symbol: str
    feature_name: str
    value: float
    version: str = "v1"
    event_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("symbol", "feature_name", "version")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value


class FeatureRecord(FeatureValue):
    """A `FeatureValue` as actually persisted — adds the server-assigned
    ingestion timestamp. Returned by both the online and offline stores."""

    ingestion_timestamp: datetime


class FeatureDefinition(BaseModel):
    """Registered schema for a feature name, used by `FeatureValidator` for
    optional range checks. A feature name with no registered definition is
    still writable (NaN/Inf/type checks always apply) — it just has no
    range check applied."""

    feature_name: str
    description: str = ""
    min_value: Optional[float] = None
    max_value: Optional[float] = None


class ValidationResult(BaseModel):
    """Outcome of validating a `FeatureValue` before it is written."""

    is_valid: bool
    errors: List[str] = Field(default_factory=list)
