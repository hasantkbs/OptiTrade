"""Tests for research_lab/reports/. Uses real PostgreSQL-backed
repositories throughout."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from decision_engine.models import DecisionOutput, EngineVote, Prediction
from learning.config import LearningConfig
from learning.evaluator import OutcomeEvaluator
from learning.models import RollingWindow
from learning.persistence import LearningRepository
from learning.tracker import SampleTracker
from research_lab.backtesting.repository import BacktestRepository
from research_lab.benchmarking.repository import BenchmarkRepository
from research_lab.experiments.repository import ExperimentRepository
from research_lab.experiments.service import ExperimentService
from research_lab.hypothesis.repository import HypothesisRepository
from research_lab.hypothesis.service import HypothesisRegistry
from research_lab.model_analysis.repository import ModelAnalysisRepository
from research_lab.model_analysis.service import ModelAnalysisService
from research_lab.models import BacktestMethod, BacktestResult, ExperimentStatus, ReportType
from research_lab.reports import generator
from research_lab.reports.repository import ReportRepository
from research_lab.reports.service import ReportService

_ENGINE = "ReportsTestEngine"
_SYMBOL = "RPTSVCX"


@pytest.fixture
def learning_repo():
    repo = LearningRepository()
    config = LearningConfig(evaluation_horizon_days=5)
    tracker = SampleTracker(repository=repo, config=config)

    def fetcher(symbol, start, end):
        dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
        return pd.DataFrame({"Close": [100 + i * 0.3 for i in range(len(dates))]}, index=dates)

    evaluator = OutcomeEvaluator(repository=repo, config=config, price_fetcher=fetcher)
    decided_at = datetime.now(timezone.utc) - timedelta(days=10)
    vote = EngineVote(
        engine_name=_ENGINE, engine_version="v1", prediction=Prediction.BUY, confidence=0.7,
        expected_return=2.0, volatility=15.0, evidence=["e"], timestamp=decided_at,
    )
    output = DecisionOutput(
        symbol=_SYMBOL, decision=Prediction.BUY, confidence=0.7, expected_return=2.0,
        expected_volatility=15.0, aggregation_strategy_version="v1", data_sufficiency=1.0,
        evidence=["e"], engine_results=[vote], timestamp=decided_at,
    )
    tracker.track_decision(output)
    evaluator.evaluate_pending(now=datetime.now(timezone.utc))

    yield repo

    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM learning_samples WHERE symbol = %s", (_SYMBOL,))
    finally:
        repo._pool.putconn(conn)


@pytest.fixture
def report_service(learning_repo):
    report_repo = ReportRepository()
    ma_repo = ModelAnalysisRepository()
    ma_svc = ModelAnalysisService(learning_repository=learning_repo, repository=ma_repo, learning_config=LearningConfig())
    exp_repo = ExperimentRepository()
    hyp_repo = HypothesisRepository()
    exp_svc = ExperimentService(repository=exp_repo, hypothesis_registry=HypothesisRegistry(repository=hyp_repo))
    backtest_repo = BacktestRepository()
    benchmark_repo = BenchmarkRepository()

    svc = ReportService(
        repository=report_repo, model_analysis_service=ma_svc, backtest_repository=backtest_repo,
        benchmark_repository=benchmark_repo, experiment_service=exp_svc,
        hypothesis_registry=exp_svc.hypothesis_registry, learning_repository=learning_repo,
    )
    created = {"reports": [], "experiments": [], "hypotheses": [], "backtests": []}
    yield svc, created

    conn = report_repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            if created["reports"]:
                cur.execute("DELETE FROM research_reports WHERE id = ANY(%s)", (created["reports"],))
    finally:
        report_repo._pool.putconn(conn)
    conn2 = ma_repo._pool.getconn()
    try:
        with conn2, conn2.cursor() as cur:
            cur.execute("DELETE FROM research_model_analysis WHERE engine_name = %s", (_ENGINE,))
    finally:
        ma_repo._pool.putconn(conn2)
    conn3 = exp_repo._pool.getconn()
    try:
        with conn3, conn3.cursor() as cur:
            if created["experiments"]:
                cur.execute("DELETE FROM research_experiments WHERE id = ANY(%s)", (created["experiments"],))
    finally:
        exp_repo._pool.putconn(conn3)
    conn4 = hyp_repo._pool.getconn()
    try:
        with conn4, conn4.cursor() as cur:
            if created["hypotheses"]:
                cur.execute("DELETE FROM research_hypotheses WHERE id = ANY(%s)", (created["hypotheses"],))
    finally:
        hyp_repo._pool.putconn(conn4)
    conn5 = backtest_repo._pool.getconn()
    try:
        with conn5, conn5.cursor() as cur:
            if created["backtests"]:
                cur.execute("DELETE FROM research_backtest_results WHERE id = ANY(%s)", (created["backtests"],))
    finally:
        backtest_repo._pool.putconn(conn5)


def test_generate_weekly_includes_the_tracked_engine(report_service):
    svc, created = report_service
    report = svc.generate_weekly()
    created["reports"].append(report.id)
    assert report.report_type == ReportType.WEEKLY
    assert any(entry["engine_name"] == _ENGINE for entry in report.content["engines"])


def test_generate_monthly_uses_thirty_day_window(report_service):
    svc, created = report_service
    report = svc.generate_monthly()
    created["reports"].append(report.id)
    assert report.content["window"] == "30d"


def test_generate_experiment_summary_includes_hypothesis_and_backtests(report_service):
    svc, created = report_service
    experiment = svc.experiment_service.create(name="Report Test Experiment", author="claude", hypothesis_statement="Testable")
    created["experiments"].append(experiment.id)
    created["hypotheses"].append(experiment.hypothesis_id)

    backtest = BacktestResult(
        experiment_id=experiment.id, method=BacktestMethod.OUT_OF_SAMPLE, engine_name=_ENGINE, engine_version="v1",
        window_start=datetime.now(timezone.utc) - timedelta(days=10), window_end=datetime.now(timezone.utc),
        sample_count=5, aggregate_sharpe=1.0, aggregate_sortino=1.2, aggregate_max_drawdown=2.0, aggregate_win_rate=0.6,
        aggregate_expected_value=1.5,
    )
    backtest_id = svc.backtest_repository.save(backtest)
    created["backtests"].append(backtest_id)

    report = svc.generate_experiment_summary(experiment.id)
    created["reports"].append(report.id)
    assert report.content["hypothesis"]["statement"] == "Testable"
    assert len(report.content["backtests"]) == 1


def test_generate_experiment_summary_raises_for_unknown_experiment(report_service):
    svc, _ = report_service
    with pytest.raises(ValueError):
        svc.generate_experiment_summary(999999999)


def test_list_reports_returns_generated_reports(report_service):
    svc, created = report_service
    report = svc.generate_weekly()
    created["reports"].append(report.id)
    reports = svc.list_reports(ReportType.WEEKLY)
    assert any(r.id == report.id for r in reports)


def test_report_repository_get_round_trips(report_service):
    svc, created = report_service
    report = svc.generate_weekly()
    created["reports"].append(report.id)
    fetched = svc.repository.get(report.id)
    assert fetched is not None
    assert fetched.report_type == ReportType.WEEKLY


def test_report_repository_get_returns_none_for_unknown_id(report_service):
    svc, _ = report_service
    assert svc.repository.get(999999999) is None


def test_generator_periodic_report_is_pure():
    now = datetime.now(timezone.utc)
    content = generator.generate_periodic_report(now - timedelta(days=7), now, RollingWindow.SEVEN_DAY, [])
    assert content["engines"] == []
    assert content["window"] == "7d"
