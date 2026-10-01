"""
Tests for decision_engine/service.py (DecisionEngine orchestrator).

Orchestration logic (engine execution, per-engine failure isolation,
validation-based filtering, data_sufficiency, persistence) is tested via
fakes satisfying `decision_engine.interfaces`' Protocols and
`feature_store.interfaces`' Protocols. A final section runs the same
behavior end-to-end against the real Feature Store (Postgres + Redis) and
the real execution repository.
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pytest

from decision_engine.config import DecisionEngineConfig
from decision_engine.exceptions import NoValidVotesError
from decision_engine.models import DecisionOutput, EngineVote, Prediction
from decision_engine.registry import VotingEngineRegistry
from decision_engine.repository import PostgresExecutionRepository
from decision_engine.service import DecisionEngine
from feature_store.config import FeatureStoreConfig
from feature_store.models import FeatureRecord, FeatureValue
from feature_store.service import FeatureStoreService


class FakeVotingEngine:
    def __init__(self, engine_name, prediction=Prediction.BUY, confidence=0.8,
                 expected_return=1.0, volatility=1.0, evidence=None,
                 engine_version="v1", raises=False):
        self.engine_name = engine_name
        self.engine_version = engine_version
        self._prediction = prediction
        self._confidence = confidence
        self._expected_return = expected_return
        self._volatility = volatility
        self._evidence = evidence or []
        self._raises = raises
        self.calls: List[str] = []

    def vote(self, symbol: str) -> EngineVote:
        self.calls.append(symbol)
        if self._raises:
            raise RuntimeError("simulated engine failure")
        return EngineVote(
            engine_name=self.engine_name, engine_version=self.engine_version,
            prediction=self._prediction, confidence=self._confidence,
            expected_return=self._expected_return, volatility=self._volatility,
            evidence=self._evidence,
        )


class FakeFeatureStoreService:
    def __init__(self) -> None:
        self._data: Dict[tuple, FeatureRecord] = {}

    def seed(self, engine_name: str, value: float) -> None:
        now = datetime.now(timezone.utc)
        self._data[(engine_name, "engine_accuracy_score")] = FeatureRecord(
            symbol=engine_name, feature_name="engine_accuracy_score", value=value,
            event_timestamp=now, ingestion_timestamp=now,
        )

    def get_latest_feature(self, symbol: str, feature_name: str) -> Optional[FeatureRecord]:
        return self._data.get((symbol, feature_name))


class FakeExecutionRepository:
    def __init__(self, raise_on_save: bool = False) -> None:
        self.saved: List[DecisionOutput] = []
        self.raise_on_save = raise_on_save

    def save(self, output: DecisionOutput) -> None:
        if self.raise_on_save:
            raise RuntimeError("simulated persistence failure")
        self.saved.append(output)

    def get_recent(self, symbol: str, limit: int = 10) -> List[DecisionOutput]:
        return [o for o in self.saved if o.symbol == symbol][:limit]


def _build_engine(registered_engines, feature_store=None, repo=None):
    registry = VotingEngineRegistry()
    for engine in registered_engines:
        registry.register(engine)
    return DecisionEngine(
        registry=registry,
        feature_store=feature_store or FakeFeatureStoreService(),
        execution_repository=repo or FakeExecutionRepository(),
        config=DecisionEngineConfig(),
    )


# ─────────────────────────────────────────────────────────────────────────
# Orchestration logic, via fakes
# ─────────────────────────────────────────────────────────────────────────

def test_decide_aggregates_votes_from_all_valid_engines():
    engines = [
        FakeVotingEngine("TechnicalEngine", Prediction.BUY, 0.8, 2.0, 1.0),
        FakeVotingEngine("FundamentalEngine", Prediction.BUY, 0.6, 1.0, 2.0),
    ]
    engine = _build_engine(engines)

    output = engine.decide("BTC-USD")

    assert output.symbol == "BTC-USD"
    assert output.decision == Prediction.BUY
    assert len(output.engine_results) == 2
    assert output.data_sufficiency == 1.0
    assert engines[0].calls == ["BTC-USD"]
    assert engines[1].calls == ["BTC-USD"]


def test_decide_ignores_an_engine_that_raises():
    engines = [
        FakeVotingEngine("TechnicalEngine", Prediction.BUY, 0.8, 2.0, 1.0),
        FakeVotingEngine("BrokenEngine", raises=True),
    ]
    engine = _build_engine(engines)

    output = engine.decide("BTC-USD")

    assert len(output.engine_results) == 1
    assert output.engine_results[0].engine_name == "TechnicalEngine"
    assert output.data_sufficiency == pytest.approx(0.5)  # 1 valid out of 2 registered


def test_decide_ignores_an_engine_that_produces_an_invalid_vote():
    import math
    engines = [
        FakeVotingEngine("TechnicalEngine", Prediction.BUY, 0.8, 2.0, 1.0),
        FakeVotingEngine("BadEngine", Prediction.SELL, 0.5, math.nan, 1.0),
    ]
    engine = _build_engine(engines)

    output = engine.decide("BTC-USD")

    assert len(output.engine_results) == 1
    assert output.engine_results[0].engine_name == "TechnicalEngine"


def test_decide_with_zero_registered_engines_returns_neutral_hold():
    engine = _build_engine([])
    output = engine.decide("BTC-USD")
    assert output.decision == Prediction.HOLD
    assert output.confidence == 0.0
    assert output.data_sufficiency == 0.0
    assert output.engine_results == []


def test_decide_strict_raises_when_no_valid_votes_exist():
    engine = _build_engine([FakeVotingEngine("BrokenEngine", raises=True)])
    with pytest.raises(NoValidVotesError):
        engine.decide("BTC-USD", strict=True)


def test_decide_non_strict_does_not_raise_when_no_valid_votes_exist():
    engine = _build_engine([FakeVotingEngine("BrokenEngine", raises=True)])
    output = engine.decide("BTC-USD", strict=False)
    assert output.decision == Prediction.HOLD


def test_decide_persists_the_output_via_the_execution_repository():
    repo = FakeExecutionRepository()
    engine = _build_engine([FakeVotingEngine("TechnicalEngine")], repo=repo)
    output = engine.decide("BTC-USD")
    assert repo.saved == [output]


def test_decide_still_returns_a_result_when_persistence_fails():
    repo = FakeExecutionRepository(raise_on_save=True)
    engine = _build_engine([FakeVotingEngine("TechnicalEngine")], repo=repo)
    output = engine.decide("BTC-USD")  # must not raise
    assert output.decision == Prediction.BUY
    assert repo.saved == []  # the simulated failure meant nothing was actually stored


def test_decide_uses_accuracy_weight_from_feature_store():
    # TechnicalEngine has a high historical accuracy (3.0) and votes BUY;
    # NewsEngine has the default weight (1.0, no history) and votes SELL
    # with equal self-reported confidence - the historically-accurate
    # engine's vote must dominate.
    feature_store = FakeFeatureStoreService()
    feature_store.seed("TechnicalEngine", 3.0)
    engines = [
        FakeVotingEngine("TechnicalEngine", Prediction.BUY, 0.5, 1.0, 1.0),
        FakeVotingEngine("NewsEngine", Prediction.SELL, 0.5, -1.0, 1.0),
    ]
    engine = _build_engine(engines, feature_store=feature_store)
    output = engine.decide("BTC-USD")
    assert output.decision == Prediction.BUY


def test_decide_defaults_to_weight_one_when_no_accuracy_history_exists():
    engines = [FakeVotingEngine("TechnicalEngine", Prediction.BUY, 1.0, 1.0, 1.0)]
    engine = _build_engine(engines, feature_store=FakeFeatureStoreService())
    output = engine.decide("BTC-USD")
    # confidence == 1.0 confirms the sole vote's full weight (accuracy
    # 1.0 default * confidence 1.0) backed the winning decision entirely.
    assert output.confidence == pytest.approx(1.0)


def test_registering_an_engine_after_construction_with_an_initially_empty_registry_is_seen():
    # Regression test: an empty VotingEngineRegistry (0 engines) is falsy
    # in Python because VotingEngineRegistry defines __len__ - passing one
    # to DecisionEngine(registry=...) must not silently be replaced by a
    # different, disconnected registry via a naive `registry or Default()`
    # fallback. This is exactly the "construct once, engines self-register
    # later" pattern real usage (and the engine registry) depends on.
    registry = VotingEngineRegistry()  # deliberately empty at construction time
    engine = DecisionEngine(
        registry=registry, feature_store=FakeFeatureStoreService(),
        execution_repository=FakeExecutionRepository(), config=DecisionEngineConfig(),
    )
    registry.register(FakeVotingEngine("TechnicalEngine", Prediction.BUY, 0.9, 2.0, 1.0))

    output = engine.decide("BTC-USD")
    assert output.decision == Prediction.BUY
    assert len(output.engine_results) == 1


def test_decide_result_reflects_aggregation_strategy_version_from_config():
    config = DecisionEngineConfig(aggregation_strategy_version="custom_v2")
    registry = VotingEngineRegistry()
    registry.register(FakeVotingEngine("TechnicalEngine"))
    engine = DecisionEngine(
        registry=registry, feature_store=FakeFeatureStoreService(),
        execution_repository=FakeExecutionRepository(), config=config,
    )
    output = engine.decide("BTC-USD")
    assert output.aggregation_strategy_version == "custom_v2"


# ─────────────────────────────────────────────────────────────────────────
# End-to-end, against the real Feature Store (Postgres + Redis) and the
# real execution repository (fake voting engines only, since no real
# voting engine exists yet at this stage).
# ─────────────────────────────────────────────────────────────────────────

@pytest.fixture
def real_engine_name():
    return f"TEST-ENGINE-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def real_symbol():
    return f"TEST-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def real_decision_engine():
    config = FeatureStoreConfig.from_env()
    feature_store = FeatureStoreService()
    repository = PostgresExecutionRepository(config=config)
    registry = VotingEngineRegistry()
    decision_engine = DecisionEngine(
        registry=registry, feature_store=feature_store,
        execution_repository=repository, config=DecisionEngineConfig(),
    )
    yield decision_engine, registry
    repository.close()


def test_real_end_to_end_decide_and_persist(real_decision_engine, real_engine_name, real_symbol):
    decision_engine, registry = real_decision_engine
    registry.register(FakeVotingEngine(real_engine_name, Prediction.BUY, 0.9, 2.5, 1.5))

    output = decision_engine.decide(real_symbol)

    assert output.decision == Prediction.BUY
    assert output.symbol == real_symbol

    recent = decision_engine.execution_repository.get_recent(real_symbol)
    try:
        assert len(recent) == 1
        assert recent[0].decision == Prediction.BUY
    finally:
        conn = decision_engine.execution_repository._pool.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("DELETE FROM decision_engine_executions WHERE symbol = %s", (real_symbol,))
        finally:
            decision_engine.execution_repository._pool.putconn(conn)


def test_real_end_to_end_uses_accuracy_weight_written_to_feature_store(
    real_decision_engine, real_engine_name, real_symbol
):
    decision_engine, registry = real_decision_engine
    registry.register(FakeVotingEngine(real_engine_name, Prediction.BUY, 0.5, 1.0, 1.0))

    decision_engine.feature_store.write_feature(
        FeatureValue(symbol=real_engine_name, feature_name="engine_accuracy_score", value=2.0)
    )
    try:
        weight = decision_engine.weight_provider.get_weight(real_engine_name)
        assert weight == 2.0
    finally:
        conn = decision_engine.feature_store.offline_store._pool.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", (real_engine_name,))
        finally:
            decision_engine.feature_store.offline_store._pool.putconn(conn)
        decision_engine.feature_store.online_store._client.delete(
            f"feature_store:{real_engine_name}:engine_accuracy_score"
        )
