"""
OptiTrade — Market Anomaly Detector (legacy re-export shim).

The real implementation moved to `intelligence.anomaly` - the canonical
home for production intelligence/alert primitives, with no dependency
on this module or on `core.hybrid_engine`. This module re-exports it
unchanged so every existing import (`core.hybrid_engine`,
`api/v1/endpoints/signals.py`, and their tests) keeps working without
modification. There is exactly ONE real implementation, in
`intelligence.anomaly` - this file contains no logic of its own.
"""
from __future__ import annotations

from intelligence.anomaly import MarketAlert, MarketAnomalyDetector

__all__ = ["MarketAlert", "MarketAnomalyDetector"]
