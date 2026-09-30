"""
Proves `core.market_anomaly_detector` is a pure re-export shim over the
canonical `intelligence.anomaly` implementation, introduced when
`MarketAnomalyDetector`/`MarketAlert` were extracted out of the legacy
`core.hybrid_engine` path. There must be exactly ONE real
implementation; this test fails if the two ever diverge into separate
classes (e.g. a future edit accidentally re-adds a duplicate body to
the legacy module).

`core.hybrid_engine`'s own tests (tests/test_hybrid_engine.py,
tests/unit/test_hybrid_engine.py) and `api/v1/endpoints/signals.py`'s
own tests continue to import `core.market_anomaly_detector` directly
and are unaffected - this file only adds the missing "same class"
guarantee.
"""
import core.market_anomaly_detector as legacy
import intelligence.anomaly as canonical


def test_legacy_module_reexports_the_exact_canonical_classes():
    assert legacy.MarketAnomalyDetector is canonical.MarketAnomalyDetector
    assert legacy.MarketAlert is canonical.MarketAlert


def test_hybrid_engine_still_constructs_a_working_detector_by_default():
    from core.hybrid_engine import HybridTradingEngine

    engine = HybridTradingEngine()
    assert isinstance(engine.anomaly_detector, canonical.MarketAnomalyDetector)
