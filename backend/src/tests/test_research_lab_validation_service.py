"""
Integration tests for research_lab/validation/service.py against the
real PostgreSQL-backed LearningRepository - proves the full pipeline
(query -> filter -> cost-simulate -> aggregate) end-to-end, including
that only realized LIVE BUY decisions ever become trades."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from decision_engine.models import EngineVote, Prediction
from learning.models import LearningSample, SampleSource
from learning.persistence import LearningRepository
from paper_trading.config import PaperTradingConfig
from paper_trading.execution import ExecutionEngine
from research_lab.config import ResearchLabConfig
from research_lab.validation.service import ValidationService

_SYMBOL = "RLVALTEST"
_OTHER_SYMBOL = "RLVALTEST-OTHER"


def _flat_benchmark(symbol, start, end):
    dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
    return pd.DataFrame({"Close": [100.0] * len(dates)}, index=dates)


def _sample(symbol=_SYMBOL, decision=Prediction.BUY, source=SampleSource.LIVE, decided_at=None) -> LearningSample:
    decided_at = decided_at or (datetime.now(timezone.utc) - timedelta(days=10))
    vote = EngineVote(
        engine_name="TechnicalEngine", engine_version="v1", prediction=decision,
        confidence=0.7, expected_return=5.0, volatility=15.0, evidence=["e"],
    )
    return LearningSample(
        symbol=symbol, source=source, decision=decision, confidence=0.7,
        expected_return=5.0, expected_volatility=15.0, engine_results=[vote], evidence=["e"],
        decided_at=decided_at, evaluation_horizon_days=5,
    )


def _save_evaluated(repository, sample: LearningSample, actual_return: float = 5.0) -> int:
    """save_sample() only ever inserts a sample in its initial (pending,
    evaluated=FALSE) state - mark_sample_evaluated() is a separate write,
    exactly mirroring how the real evaluation pipeline works."""
    sample_id = repository.save_sample(sample)
    repository.mark_sample_evaluated(
        sample_id, actual_return=actual_return, actual_volatility=15.0,
        correct=actual_return > 0, evaluated_at=datetime.now(timezone.utc),
    )
    return sample_id


@pytest.fixture
def repository():
    repo = LearningRepository()
    yield repo
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM learning_samples WHERE symbol = ANY(%s)", ([_SYMBOL, _OTHER_SYMBOL],))
    finally:
        repo._pool.putconn(conn)


@pytest.fixture
def service(repository):
    execution_engine = ExecutionEngine(config=PaperTradingConfig(
        slippage_bps=0.0, spread_bps=0.0, commission_rate=0.0, commission_min=0.0, tax_rate=0.0,
    ))
    return ValidationService(
        learning_repository=repository,
        execution_engine=execution_engine,
        config=ResearchLabConfig(validation_position_size_notional=10_000.0, validation_min_samples_for_report=2),
        price_fetcher=_flat_benchmark,
    )


def test_validate_counts_only_live_evaluated_buy_decisions_as_trades(repository, service):
    _save_evaluated(repository, _sample(decision=Prediction.BUY), actual_return=5.0)
    _save_evaluated(repository, _sample(decision=Prediction.HOLD), actual_return=5.0)
    _save_evaluated(repository, _sample(decision=Prediction.SELL), actual_return=5.0)
    repository.save_sample(_sample(decision=Prediction.BUY))  # still pending, never evaluated
    _save_evaluated(repository, _sample(decision=Prediction.BUY, source=SampleSource.SHADOW), actual_return=5.0)

    report = service.validate(symbol=_SYMBOL, since=datetime.now(timezone.utc) - timedelta(days=30))

    assert report.trade_count == 1
    assert report.hold_count == 1
    assert report.sell_signal_count == 1


def test_validate_zero_cost_trade_reflects_exact_gross_return(repository, service):
    _save_evaluated(repository, _sample(decision=Prediction.BUY), actual_return=8.0)

    report = service.validate(symbol=_SYMBOL, since=datetime.now(timezone.utc) - timedelta(days=30))

    assert report.trade_count == 1
    assert report.win_rate == pytest.approx(1.0)
    assert report.expectancy_pct == pytest.approx(8.0)
    assert len(report.equity_curve) == 1
    assert report.equity_curve[0][1] == pytest.approx(108.0)


def test_validate_computes_win_rate_across_multiple_trades(repository, service):
    now = datetime.now(timezone.utc)
    _save_evaluated(repository, _sample(decided_at=now - timedelta(days=20)), actual_return=10.0)
    _save_evaluated(repository, _sample(decided_at=now - timedelta(days=15)), actual_return=-5.0)
    _save_evaluated(repository, _sample(decided_at=now - timedelta(days=10)), actual_return=3.0)

    report = service.validate(symbol=_SYMBOL, since=now - timedelta(days=30))

    assert report.trade_count == 3
    assert report.win_rate == pytest.approx(2.0 / 3.0)
    assert report.has_sufficient_samples is True  # >= config.validation_min_samples_for_report (2)


def test_validate_flags_insufficient_samples(repository, service):
    _save_evaluated(repository, _sample(), actual_return=1.0)

    report = service.validate(symbol=_SYMBOL, since=datetime.now(timezone.utc) - timedelta(days=30))

    assert report.trade_count == 1
    assert report.has_sufficient_samples is False  # < config.validation_min_samples_for_report (2)


def test_validate_respects_since_boundary(repository, service):
    now = datetime.now(timezone.utc)
    _save_evaluated(repository, _sample(decided_at=now - timedelta(days=60)), actual_return=99.0)  # too old
    _save_evaluated(repository, _sample(decided_at=now - timedelta(days=5)), actual_return=2.0)

    report = service.validate(symbol=_SYMBOL, since=now - timedelta(days=10))

    assert report.trade_count == 1


def test_validate_respects_until_boundary(repository, service):
    """No-future-leakage guard: a decision made after the report's own
    `until` boundary must never be counted, even though it's already
    evaluated and would otherwise pass every other filter."""
    now = datetime.now(timezone.utc)
    _save_evaluated(repository, _sample(decided_at=now - timedelta(days=5)), actual_return=2.0)
    _save_evaluated(repository, _sample(decided_at=now + timedelta(days=1)), actual_return=99.0)  # "in the future"

    report = service.validate(symbol=_SYMBOL, since=now - timedelta(days=30), until=now)

    assert report.trade_count == 1
    assert report.expectancy_pct == pytest.approx(2.0)


def test_validate_respects_symbol_filter(repository, service):
    _save_evaluated(repository, _sample(symbol=_SYMBOL), actual_return=5.0)
    _save_evaluated(repository, _sample(symbol=_OTHER_SYMBOL), actual_return=5.0)

    report = service.validate(symbol=_SYMBOL, since=datetime.now(timezone.utc) - timedelta(days=30))

    assert report.trade_count == 1


def test_validate_includes_all_symbols_when_symbol_is_none(repository, service):
    _save_evaluated(repository, _sample(symbol=_SYMBOL), actual_return=5.0)
    _save_evaluated(repository, _sample(symbol=_OTHER_SYMBOL), actual_return=5.0)

    report = service.validate(since=datetime.now(timezone.utc) - timedelta(days=30))

    assert report.trade_count == 2


def test_validate_includes_benchmark_comparison(repository, service):
    now = datetime.now(timezone.utc)
    # Two distinct decision dates -> a real (non-zero-length) window for
    # the benchmark to compute a return over.
    _save_evaluated(repository, _sample(decided_at=now - timedelta(days=20)), actual_return=5.0)
    _save_evaluated(repository, _sample(decided_at=now - timedelta(days=10)), actual_return=5.0)

    report = service.validate(symbol=_SYMBOL, since=now - timedelta(days=30))

    assert report.benchmark_symbol is not None
    assert report.benchmark_return_pct == pytest.approx(0.0)  # flat benchmark fixture


def test_validate_with_no_samples_returns_an_empty_report(repository, service):
    report = service.validate(symbol="RLVALTEST-NO-DATA", since=datetime.now(timezone.utc) - timedelta(days=30))

    assert report.trade_count == 0
    assert report.win_rate == 0.0
    assert report.profit_factor is None
    assert report.has_sufficient_samples is False


def test_validate_defaults_to_real_dependencies():
    service = ValidationService()
    assert isinstance(service.learning_repository, LearningRepository)
    assert isinstance(service.execution_engine, ExecutionEngine)
