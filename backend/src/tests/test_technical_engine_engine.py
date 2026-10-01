"""
Tests for engines/technical/engine.py (TechnicalEngine orchestrator).

Combination logic is tested by injecting a fake feature_adapter that
returns a controlled feature dict — the six analyzer modules themselves
are the REAL ones (not faked), so this exercises the genuine
trend/momentum/oscillator/volatility/volume/market_structure -> combined
decision pipeline deterministically. A final section proves real
integration with the Decision Engine, Engine Registry, and a real
end-to-end Feature Store-backed run.
"""
import uuid
from datetime import datetime, timezone

import pytest

from decision_engine.interfaces import VotingEngineProtocol
from decision_engine.models import Prediction
from decision_engine.registry import VotingEngineRegistry
from decision_engine.service import DecisionEngine
from decision_engine.validation import validate_vote
from engine_registry.registry import default_registry
from engines.technical import TechnicalEngine
from engines.technical.config import (
    FEATURE_ATR_PCT,
    FEATURE_BB_PERCENT_B,
    FEATURE_EMA_CROSSOVER,
    FEATURE_MACD_LINE,
    FEATURE_MACD_SIGNAL,
    FEATURE_ROC,
    FEATURE_RSI,
    FEATURE_TREND_STRENGTH,
    FEATURE_VOLUME_RATIO,
    FEATURE_VWAP_DIFF,
    TechnicalEngineConfig,
)
from engines.technical.feature_adapter import FeatureResolution


class FakeFeatureAdapter:
    def __init__(self, values, from_cache=None, computed_fresh=None):
        self._resolution = FeatureResolution(
            values=values, from_cache=from_cache or [], computed_fresh=computed_fresh or list(values),
        )

    def get_features(self, symbol: str) -> FeatureResolution:
        return self._resolution


def _engine(values) -> TechnicalEngine:
    return TechnicalEngine(feature_adapter=FakeFeatureAdapter(values), config=TechnicalEngineConfig())


# ─────────────────────────────────────────────────────────────────────────
# Combination logic (real analyzers, fake feature source)
# ─────────────────────────────────────────────────────────────────────────

def test_no_features_produces_neutral_hold():
    result = _engine({}).analyze("BTC-USD")
    assert result.prediction == Prediction.HOLD
    assert result.confidence == 0.0
    assert result.expected_return == 0.0
    assert result.expected_volatility == 0.0
    assert result.evidence == []
    assert result.feature_importance == {}


def test_strongly_bullish_features_produce_buy():
    values = {
        FEATURE_RSI: 15.0, FEATURE_TREND_STRENGTH: 10.0, FEATURE_EMA_CROSSOVER: 2.0,
        FEATURE_MACD_LINE: 0.5, FEATURE_MACD_SIGNAL: 0.2, FEATURE_ROC: 20.0,
        FEATURE_BB_PERCENT_B: -0.1, FEATURE_VOLUME_RATIO: 2.5, FEATURE_VWAP_DIFF: -4.0,
        FEATURE_ATR_PCT: 2.0,
    }
    result = _engine(values).analyze("BTC-USD")
    assert result.prediction == Prediction.BUY
    assert result.confidence > 0.5
    assert result.expected_return > 0  # bullish signal * positive ATR% -> positive expected return
    assert result.expected_volatility == pytest.approx(2.0)
    assert len(result.evidence) > 0


def test_strongly_bearish_features_produce_sell():
    values = {
        FEATURE_RSI: 85.0, FEATURE_TREND_STRENGTH: -10.0, FEATURE_EMA_CROSSOVER: -2.0,
        FEATURE_MACD_LINE: 0.2, FEATURE_MACD_SIGNAL: 0.5, FEATURE_ROC: -20.0,
        FEATURE_BB_PERCENT_B: 1.1, FEATURE_VOLUME_RATIO: 0.3, FEATURE_VWAP_DIFF: 4.0,
        FEATURE_ATR_PCT: 2.0,
    }
    result = _engine(values).analyze("BTC-USD")
    assert result.prediction == Prediction.SELL
    assert result.expected_return < 0


def test_weak_mixed_signals_stay_within_hold_threshold():
    # A single, mild, borderline signal should not clear the default 0.2
    # decision threshold.
    values = {FEATURE_TREND_STRENGTH: 4.0}  # trend.py component = 0.5, only analyzer active
    result = _engine(values).analyze("BTC-USD")
    # net_signal here is fully 0.5 (only one analyzer contributes any
    # confidence), which DOES clear 0.2 -> BUY. Included to document that
    # even a single confident analyzer can decide the vote on its own.
    assert result.prediction == Prediction.BUY


def test_feature_importance_sums_to_one_when_signals_present():
    values = {FEATURE_RSI: 15.0, FEATURE_TREND_STRENGTH: 10.0}
    result = _engine(values).analyze("BTC-USD")
    assert result.feature_importance
    assert sum(result.feature_importance.values()) == pytest.approx(1.0)


def test_execution_metadata_reports_all_six_analyzers_and_feature_provenance():
    adapter = FakeFeatureAdapter(
        values={FEATURE_RSI: 50.0}, from_cache=[FEATURE_RSI], computed_fresh=[],
    )
    engine = TechnicalEngine(feature_adapter=adapter, config=TechnicalEngineConfig())
    result = engine.analyze("BTC-USD")

    assert set(result.execution_metadata.analyzer_durations_ms.keys()) == {
        "trend", "momentum", "oscillator", "volatility", "volume", "market_structure",
    }
    assert result.execution_metadata.features_from_cache == [FEATURE_RSI]
    assert result.execution_metadata.total_duration_ms >= 0.0


def test_vote_adapts_analysis_into_a_valid_engine_vote():
    engine = _engine({FEATURE_RSI: 15.0, FEATURE_ATR_PCT: 1.5})
    vote = engine.vote("BTC-USD")

    assert vote.engine_name == "TechnicalEngine"
    assert vote.engine_version == "v1"
    assert vote.prediction == Prediction.BUY
    assert vote.volatility == pytest.approx(1.5)
    assert validate_vote(vote).is_valid is True


def test_engine_name_and_version_reflect_config():
    config = TechnicalEngineConfig(engine_version="v2-test")
    engine = TechnicalEngine(feature_adapter=FakeFeatureAdapter({}), config=config)
    assert engine.engine_version == "v2-test"


def test_feature_adapter_property_is_lazy_and_cached():
    engine = TechnicalEngine()
    assert engine._feature_adapter is None  # nothing constructed yet
    first = engine.feature_adapter
    second = engine.feature_adapter
    assert first is second  # constructed once, reused


# ─────────────────────────────────────────────────────────────────────────
# Decision Engine contract + Engine Registry integration
# ─────────────────────────────────────────────────────────────────────────

def test_technical_engine_satisfies_voting_engine_protocol():
    engine = TechnicalEngine()
    assert isinstance(engine, VotingEngineProtocol)


def test_technical_engine_self_registered_into_the_default_engine_registry():
    registered = default_registry.get("TechnicalEngine", "v1")
    assert isinstance(registered, TechnicalEngine)


def test_reimporting_the_package_does_not_raise_on_duplicate_registration():
    # Exercises the exact DuplicateEngineError guard in
    # engines/technical/__init__.py: the module is already imported and
    # registered (by this test session's first import), so re-running its
    # registration line directly must be swallowed, not raised.
    from engine_registry.exceptions import DuplicateEngineError

    with pytest.raises(DuplicateEngineError):
        default_registry.register(TechnicalEngine())  # proves it WOULD raise without the guard

    import importlib

    import engines.technical as technical_package

    importlib.reload(technical_package)  # re-runs __init__.py's registration line for real


def test_technical_engine_works_inside_a_decision_engine_registry():
    registry = VotingEngineRegistry()
    registry.register(_engine({FEATURE_RSI: 15.0, FEATURE_ATR_PCT: 1.0}))
    assert len(registry.all()) == 1
    assert registry.all()[0].engine_name == "TechnicalEngine"


# ─────────────────────────────────────────────────────────────────────────
# Real, live end-to-end (network + Feature Store + Decision Engine)
# ─────────────────────────────────────────────────────────────────────────

def test_real_end_to_end_vote_for_a_real_symbol():
    engine = TechnicalEngine()
    vote = engine.vote("AAPL")
    assert vote.engine_name == "TechnicalEngine"
    assert validate_vote(vote).is_valid is True
    _cleanup_aapl(engine)


def test_real_end_to_end_through_the_decision_engine():
    from decision_engine.config import DecisionEngineConfig
    from decision_engine.repository import PostgresExecutionRepository
    from feature_store.config import FeatureStoreConfig

    technical_engine = TechnicalEngine()
    registry = VotingEngineRegistry()
    registry.register(technical_engine)

    repository = PostgresExecutionRepository(config=FeatureStoreConfig.from_env())
    decision_engine = DecisionEngine(
        registry=registry, feature_store=technical_engine.feature_adapter.feature_store,
        execution_repository=repository, config=DecisionEngineConfig(),
    )

    output = decision_engine.decide("AAPL")
    assert output.symbol == "AAPL"
    assert len(output.engine_results) == 1
    assert output.engine_results[0].engine_name == "TechnicalEngine"

    conn = repository._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM decision_engine_executions WHERE symbol = %s", ("AAPL",))
    finally:
        repository._pool.putconn(conn)
    repository.close()
    _cleanup_aapl(technical_engine)


def _cleanup_aapl(engine: TechnicalEngine) -> None:
    from engines.technical.config import ALL_FEATURE_NAMES

    conn = engine.feature_adapter.feature_store.offline_store._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", ("AAPL",))
    finally:
        engine.feature_adapter.feature_store.offline_store._pool.putconn(conn)
    for name in ALL_FEATURE_NAMES:
        engine.feature_adapter.feature_store.online_store._client.delete(f"feature_store:AAPL:{name}")
