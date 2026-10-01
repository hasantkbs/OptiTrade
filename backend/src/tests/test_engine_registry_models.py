"""Tests for engine_registry/models.py and engine_registry/exceptions.py."""
from decision_engine.models import EngineVote, Prediction
from engine_registry.exceptions import (
    DuplicateEngineError,
    EngineNotFoundError,
    EngineRegistryError,
    IncompatibleEngineError,
)
from engine_registry.models import ExecutionMetadata, ExecutionStatus


def test_execution_metadata_defaults():
    meta = ExecutionMetadata(
        engine_name="TechnicalEngine", engine_version="v1",
        status=ExecutionStatus.SUCCESS, duration_ms=12.3,
    )
    assert meta.error_type is None
    assert meta.vote is None
    assert meta.timestamp.tzinfo is not None


def test_execution_metadata_carries_a_vote_on_success():
    vote = EngineVote(
        engine_name="TechnicalEngine", engine_version="v1",
        prediction=Prediction.BUY, confidence=0.8,
        expected_return=1.0, volatility=1.0,
    )
    meta = ExecutionMetadata(
        engine_name="TechnicalEngine", engine_version="v1",
        status=ExecutionStatus.SUCCESS, duration_ms=5.0, vote=vote,
    )
    assert meta.vote.prediction == Prediction.BUY


def test_incompatible_engine_error_message():
    exc = IncompatibleEngineError("<NotAnEngine instance>")
    assert "<NotAnEngine instance>" in str(exc)
    assert isinstance(exc, EngineRegistryError)


def test_duplicate_engine_error_message():
    exc = DuplicateEngineError("TechnicalEngine", "v1")
    assert exc.engine_name == "TechnicalEngine"
    assert exc.engine_version == "v1"
    assert "TechnicalEngine" in str(exc) and "v1" in str(exc)


def test_engine_not_found_error_message():
    exc = EngineNotFoundError("TechnicalEngine", "v2")
    assert exc.engine_name == "TechnicalEngine"
    assert exc.engine_version == "v2"
    assert isinstance(exc, EngineRegistryError)
