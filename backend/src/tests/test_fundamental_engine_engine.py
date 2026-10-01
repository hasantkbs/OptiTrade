"""
Tests for engines/fundamental/engine.py (FundamentalEngine orchestrator).
"""
import pytest

from decision_engine.interfaces import VotingEngineProtocol
from decision_engine.models import Prediction
from decision_engine.registry import VotingEngineRegistry
from decision_engine.validation import validate_vote
from engine_registry.registry import default_registry
from engines.fundamental import FundamentalEngine
from engines.fundamental.config import (
    FEATURE_ALTMAN_Z,
    FEATURE_DEBT_TO_EQUITY,
    FEATURE_MARGIN_STABILITY,
    FEATURE_PE,
    FEATURE_PEG,
    FEATURE_REVENUE_GROWTH,
    FEATURE_ROE,
    FundamentalEngineConfig,
)
from engines.fundamental.feature_adapter import FeatureResolution


class FakeFeatureAdapter:
    def __init__(self, values, from_cache=None, computed_fresh=None):
        self._resolution = FeatureResolution(
            values=values, from_cache=from_cache or [], computed_fresh=computed_fresh or list(values),
        )

    def get_features(self, symbol: str) -> FeatureResolution:
        return self._resolution


def _engine(values) -> FundamentalEngine:
    return FundamentalEngine(feature_adapter=FakeFeatureAdapter(values), config=FundamentalEngineConfig())


def test_no_features_produces_neutral_hold():
    result = _engine({}).analyze("AAPL")
    assert result.prediction == Prediction.HOLD
    assert result.confidence == 0.0
    assert result.expected_return == 0.0
    assert result.feature_importance == {}


def test_strongly_bullish_features_produce_buy():
    values = {
        FEATURE_PE: 10.0, FEATURE_PEG: 0.8, FEATURE_REVENUE_GROWTH: 20.0,
        FEATURE_ROE: 25.0, FEATURE_DEBT_TO_EQUITY: 30.0, FEATURE_ALTMAN_Z: 3.5,
    }
    result = _engine(values).analyze("AAPL")
    assert result.prediction == Prediction.BUY
    # Confidence is averaged across all 6 analyzers, including cashflow
    # and quality (which received no data here and so contribute 0), so
    # it's naturally diluted below what a "strongly bullish" label might
    # suggest - still meaningfully positive.
    assert 0.0 < result.confidence < 1.0
    assert result.expected_return > 0


def test_strongly_bearish_features_produce_sell():
    values = {
        FEATURE_PE: 50.0, FEATURE_REVENUE_GROWTH: -20.0,
        FEATURE_ROE: -5.0, FEATURE_DEBT_TO_EQUITY: 250.0, FEATURE_ALTMAN_Z: 1.0,
    }
    result = _engine(values).analyze("AAPL")
    assert result.prediction == Prediction.SELL
    assert result.expected_return < 0


def test_expected_volatility_uses_margin_stability_when_available():
    result = _engine({FEATURE_MARGIN_STABILITY: 0.9}).analyze("AAPL")
    assert result.expected_volatility == pytest.approx((1 - 0.9) * 20.0)


def test_expected_volatility_defaults_when_margin_stability_absent():
    result = _engine({FEATURE_PE: 10.0}).analyze("AAPL")
    assert result.expected_volatility == pytest.approx(15.0)


def test_feature_importance_excludes_a_zero_magnitude_analyzer():
    # Altman Z in the "grey zone" contributes features_used but a signal
    # of exactly 0.0 (see financial_health.py) - this analyzer's
    # zero-magnitude contribution must not appear in feature_importance.
    result = _engine({FEATURE_ALTMAN_Z: 2.5}).analyze("AAPL")
    assert result.feature_importance == {}


def test_feature_importance_sums_to_one_when_signals_present():
    result = _engine({FEATURE_PE: 10.0, FEATURE_ROE: 25.0}).analyze("AAPL")
    assert result.feature_importance
    assert sum(result.feature_importance.values()) == pytest.approx(1.0)


def test_execution_metadata_reports_all_six_analyzers():
    result = _engine({FEATURE_PE: 18.0}).analyze("AAPL")
    assert set(result.execution_metadata.analyzer_durations_ms.keys()) == {
        "valuation", "growth", "profitability", "financial_health", "cashflow", "quality",
    }


def test_vote_adapts_analysis_into_a_valid_engine_vote():
    engine = _engine({FEATURE_PE: 10.0, FEATURE_PEG: 0.8})
    vote = engine.vote("AAPL")
    assert vote.engine_name == "FundamentalEngine"
    assert vote.engine_version == "v1"
    assert vote.prediction == Prediction.BUY
    assert validate_vote(vote).is_valid is True


def test_feature_adapter_property_is_lazy_and_cached():
    engine = FundamentalEngine()
    assert engine._feature_adapter is None
    first = engine.feature_adapter
    second = engine.feature_adapter
    assert first is second


# ─────────────────────────────────────────────────────────────────────────
# Decision Engine contract + Engine Registry integration
# ─────────────────────────────────────────────────────────────────────────

def test_fundamental_engine_satisfies_voting_engine_protocol():
    assert isinstance(FundamentalEngine(), VotingEngineProtocol)


def test_fundamental_engine_self_registered_into_the_default_engine_registry():
    registered = default_registry.get("FundamentalEngine", "v1")
    assert isinstance(registered, FundamentalEngine)


def test_reimporting_the_package_does_not_raise_on_duplicate_registration():
    from engine_registry.exceptions import DuplicateEngineError

    with pytest.raises(DuplicateEngineError):
        default_registry.register(FundamentalEngine())

    import importlib

    import engines.fundamental as fundamental_package

    importlib.reload(fundamental_package)


# ─────────────────────────────────────────────────────────────────────────
# Real, live end-to-end (network + Feature Store + Decision Engine)
# ─────────────────────────────────────────────────────────────────────────

def test_real_end_to_end_vote_for_a_real_company():
    engine = FundamentalEngine()
    vote = engine.vote("AAPL")
    assert vote.engine_name == "FundamentalEngine"
    assert validate_vote(vote).is_valid is True
    _cleanup_aapl(engine)


def test_real_end_to_end_through_the_decision_engine():
    from decision_engine.config import DecisionEngineConfig
    from decision_engine.repository import PostgresExecutionRepository
    from decision_engine.service import DecisionEngine
    from feature_store.config import FeatureStoreConfig

    fundamental_engine = FundamentalEngine()
    registry = VotingEngineRegistry()
    registry.register(fundamental_engine)

    repository = PostgresExecutionRepository(config=FeatureStoreConfig.from_env())
    decision_engine = DecisionEngine(
        registry=registry, feature_store=fundamental_engine.feature_adapter.feature_store,
        execution_repository=repository, config=DecisionEngineConfig(),
    )

    output = decision_engine.decide("AAPL")
    assert output.symbol == "AAPL"
    assert len(output.engine_results) == 1
    assert output.engine_results[0].engine_name == "FundamentalEngine"

    conn = repository._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM decision_engine_executions WHERE symbol = %s", ("AAPL",))
    finally:
        repository._pool.putconn(conn)
    repository.close()
    _cleanup_aapl(fundamental_engine)


def _cleanup_aapl(engine: FundamentalEngine) -> None:
    from engines.fundamental.config import ALL_FEATURE_NAMES

    conn = engine.feature_adapter.feature_store.offline_store._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", ("AAPL",))
    finally:
        engine.feature_adapter.feature_store.offline_store._pool.putconn(conn)
    for name in ALL_FEATURE_NAMES:
        engine.feature_adapter.feature_store.online_store._client.delete(f"feature_store:AAPL:{name}")
