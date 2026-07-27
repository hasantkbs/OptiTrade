"""
OptiTrade Research Lab — top-level facade.

Ties every subpackage (experiments, hypothesis, backtesting,
benchmarking, feature_analysis, model_analysis, datasets, shadow,
promotion, reports) together behind one dependency-injectable object,
mirroring the facade pattern established by
`feature_store.service.FeatureStoreService`,
`decision_engine.service.DecisionEngine`, and
`learning.service.LearningService`.

This is a fully isolated, offline research environment - see
`tests/test_research_isolation.py`. Nothing reachable from this facade
ever executes against or mutates production inference; every write
goes to this package's own `research_*` tables (or, for engine
weights, the Feature Store via Continuous Learning's already-existing
write path - never directly).
"""
from __future__ import annotations

from typing import Optional

from research_lab.backtesting.service import BacktestService
from research_lab.benchmarking.service import BenchmarkService
from research_lab.config import ResearchLabConfig
from research_lab.datasets.service import DatasetService
from research_lab.experiments.service import ExperimentService
from research_lab.feature_analysis.service import FeatureAnalysisService
from research_lab.hypothesis.service import HypothesisRegistry
from research_lab.model_analysis.service import ModelAnalysisService
from research_lab.promotion.service import PromotionService
from research_lab.reports.service import ReportService
from research_lab.shadow.service import ShadowEvaluationService


class ResearchLabService:
    """Dependency-injectable facade over the whole Research Lab. Every
    constructor parameter is optional and falls back to the real,
    config-driven implementation - matching the pattern established by
    every other package's top-level service."""

    def __init__(
        self,
        experiments: Optional[ExperimentService] = None,
        hypothesis: Optional[HypothesisRegistry] = None,
        backtesting: Optional[BacktestService] = None,
        benchmarking: Optional[BenchmarkService] = None,
        feature_analysis: Optional[FeatureAnalysisService] = None,
        model_analysis: Optional[ModelAnalysisService] = None,
        datasets: Optional[DatasetService] = None,
        shadow: Optional[ShadowEvaluationService] = None,
        promotion: Optional[PromotionService] = None,
        reports: Optional[ReportService] = None,
        config: Optional[ResearchLabConfig] = None,
    ) -> None:
        self.config = config or ResearchLabConfig.from_env()
        self.hypothesis = hypothesis or HypothesisRegistry()
        self.experiments = experiments or ExperimentService(hypothesis_registry=self.hypothesis)
        self.backtesting = backtesting or BacktestService(config=self.config)
        self.benchmarking = benchmarking or BenchmarkService(config=self.config)
        self.feature_analysis = feature_analysis or FeatureAnalysisService(config=self.config)
        self.model_analysis = model_analysis or ModelAnalysisService(config=self.config)
        self.datasets = datasets or DatasetService()
        self.shadow = shadow or ShadowEvaluationService()
        self.promotion = promotion or PromotionService(config=self.config)
        self.reports = reports or ReportService(config=self.config)
