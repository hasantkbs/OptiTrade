"""Tests for pipeline/service.py's engine-resolution error handling,
using a fake registry so a missing engine can be simulated without
touching the real default_registry."""
from engine_registry.exceptions import EngineNotFoundError
from pipeline.config import PipelineConfig
from pipeline.pipeline import Pipeline
from pipeline.service import PipelineService


class _PartiallyMissingRegistry:
    def get(self, name, version):
        if name == "NewsEngine":
            raise EngineNotFoundError(name, version)
        return _FakeEngine(name, version)


class _FakeEngine:
    def __init__(self, name, version):
        self.engine_name = name
        self.engine_version = version

    def vote(self, symbol):
        raise NotImplementedError


def test_resolve_engines_skips_a_missing_engine_without_raising():
    service = PipelineService.__new__(PipelineService)
    service.config = PipelineConfig()
    service.feature_store = None
    service.engine_registry = _PartiallyMissingRegistry()

    resolved = service._resolve_engines()
    resolved_names = {engine.engine_name for engine in resolved}
    assert resolved_names == {"TechnicalEngine", "FundamentalEngine"}
    assert "NewsEngine" not in resolved_names
