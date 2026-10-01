"""Tests for research_lab/service.py (ResearchLabService facade)."""
from research_lab import ResearchLabService
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


def test_facade_wires_up_every_subpackage():
    svc = ResearchLabService()
    assert isinstance(svc.experiments, ExperimentService)
    assert isinstance(svc.hypothesis, HypothesisRegistry)
    assert isinstance(svc.backtesting, BacktestService)
    assert isinstance(svc.benchmarking, BenchmarkService)
    assert isinstance(svc.feature_analysis, FeatureAnalysisService)
    assert isinstance(svc.model_analysis, ModelAnalysisService)
    assert isinstance(svc.datasets, DatasetService)
    assert isinstance(svc.shadow, ShadowEvaluationService)
    assert isinstance(svc.promotion, PromotionService)
    assert isinstance(svc.reports, ReportService)
    assert isinstance(svc.config, ResearchLabConfig)


def test_facade_accepts_injected_dependencies():
    experiments = ExperimentService()
    svc = ResearchLabService(experiments=experiments)
    assert svc.experiments is experiments


def test_facade_shares_hypothesis_registry_with_experiments_by_default():
    svc = ResearchLabService()
    assert svc.experiments.hypothesis_registry is svc.hypothesis
