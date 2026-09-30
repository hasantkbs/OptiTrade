"""OptiTrade Research Lab — report generation service."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from learning.models import RollingWindow
from learning.persistence import LearningRepository
from research_lab.benchmarking.repository import BenchmarkRepository
from research_lab.backtesting.repository import BacktestRepository
from research_lab.config import ResearchLabConfig
from research_lab.experiments.service import ExperimentService
from research_lab.hypothesis.service import HypothesisRegistry
from research_lab.model_analysis.service import ModelAnalysisService
from research_lab.models import BenchmarkResult, Report, ReportType
from research_lab.reports import generator
from research_lab.reports.repository import ReportRepository

logger = logging.getLogger(__name__)


class ReportService:
    """Automatically generates weekly, monthly, benchmark, and
    experiment-summary reports by reading already-computed data from
    the other Research Lab subpackages (and Continuous Learning) -
    never computes anything new itself."""

    def __init__(
        self,
        repository: Optional[ReportRepository] = None,
        model_analysis_service: Optional[ModelAnalysisService] = None,
        backtest_repository: Optional[BacktestRepository] = None,
        benchmark_repository: Optional[BenchmarkRepository] = None,
        experiment_service: Optional[ExperimentService] = None,
        hypothesis_registry: Optional[HypothesisRegistry] = None,
        learning_repository: Optional[LearningRepository] = None,
        config: Optional[ResearchLabConfig] = None,
    ) -> None:
        self.repository = repository or ReportRepository()
        self.model_analysis_service = model_analysis_service or ModelAnalysisService()
        self.backtest_repository = backtest_repository or BacktestRepository()
        self.benchmark_repository = benchmark_repository or BenchmarkRepository()
        self.experiment_service = experiment_service or ExperimentService()
        self.hypothesis_registry = hypothesis_registry or HypothesisRegistry()
        self.learning_repository = learning_repository or LearningRepository()
        self.config = config or ResearchLabConfig.from_env()

    def generate_weekly(self, now: Optional[datetime] = None) -> Report:
        return self._generate_periodic(ReportType.WEEKLY, RollingWindow.SEVEN_DAY, self.config.weekly_report_lookback_days, now)

    def generate_monthly(self, now: Optional[datetime] = None) -> Report:
        return self._generate_periodic(ReportType.MONTHLY, RollingWindow.THIRTY_DAY, self.config.monthly_report_lookback_days, now)

    def _generate_periodic(self, report_type: ReportType, window: RollingWindow, lookback_days: int, now: Optional[datetime]) -> Report:
        now = now or datetime.now(timezone.utc)
        period_start = now - timedelta(days=lookback_days)

        engines = self.learning_repository.distinct_engines()
        analyses = [
            self.model_analysis_service.analyze(engine_name, engine_version, window, now)
            for engine_name, engine_version in engines
        ]

        content = generator.generate_periodic_report(period_start, now, window, analyses)
        report = Report(
            report_type=report_type, title=f"{report_type.value.capitalize()} Report {now.date().isoformat()}",
            period_start=period_start, period_end=now, content=content, generated_at=now,
        )
        report.id = self.repository.save(report)

        log_event(
            logger, component="research_lab", module="research_lab.reports.service", operation="generate_periodic",
            status=STATUS_SUCCESS, report_type=report_type.value, engine_count=len(engines),
        )
        return report

    def generate_benchmark_report(self, benchmark: BenchmarkResult) -> Report:
        content = generator.generate_benchmark_report(benchmark)
        report = Report(
            report_type=ReportType.BENCHMARK,
            title=f"Benchmark: {benchmark.subject_a} vs {benchmark.subject_b}",
            content=content,
        )
        report.id = self.repository.save(report)
        return report

    def generate_experiment_summary(self, experiment_id: int) -> Report:
        experiment = self.experiment_service.get(experiment_id)
        if experiment is None:
            raise ValueError(f"no experiment with id {experiment_id}")

        hypothesis = self.hypothesis_registry.get(experiment.hypothesis_id) if experiment.hypothesis_id else None
        backtests = self.backtest_repository.list_for_experiment(experiment_id)
        benchmarks = self.benchmark_repository.list_for_experiment(experiment_id)

        content = generator.generate_experiment_summary(experiment, hypothesis, backtests, benchmarks)
        report = Report(
            report_type=ReportType.EXPERIMENT_SUMMARY, title=f"Experiment Summary: {experiment.name}", content=content,
        )
        report.id = self.repository.save(report)

        log_event(
            logger, component="research_lab", module="research_lab.reports.service",
            operation="generate_experiment_summary", status=STATUS_SUCCESS, experiment_id=experiment_id,
        )
        return report

    def list_reports(self, report_type: Optional[ReportType] = None, limit: int = 20):
        return self.repository.list_by_type(report_type, limit)
