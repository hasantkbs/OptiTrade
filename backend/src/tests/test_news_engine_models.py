"""Tests for engines/news/models.py."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from decision_engine.models import Prediction
from engines.news.models import (
    AggregatedNewsSignal,
    AssetResolution,
    NewsAnalysisResult,
    NewsEvidence,
    NewsExecutionMetadata,
    NormalizedArticle,
    RawArticle,
)


def test_raw_article_defaults():
    article = RawArticle(title="Title", published_at=datetime.now(timezone.utc))
    assert article.summary == ""
    assert article.source == "Unknown"


def test_normalized_article_rejects_blank_title():
    with pytest.raises(ValidationError):
        NormalizedArticle(title="   ", published_at=datetime.now(timezone.utc), source="X", text="X")


def test_asset_resolution_confidence_bounds():
    with pytest.raises(ValidationError):
        AssetResolution(symbol="AAPL", is_relevant=True, confidence=1.5)


def test_news_evidence_requires_all_fields():
    evidence = NewsEvidence(
        source="Reuters", timestamp=datetime.now(timezone.utc), title="T", summary="S",
        sentiment=0.5, relevance=0.8, impact=0.6, confidence=0.7,
    )
    assert evidence.source == "Reuters"
    assert evidence.sentiment == 0.5


def test_news_evidence_sentiment_out_of_range_rejected():
    with pytest.raises(ValidationError):
        NewsEvidence(
            source="Reuters", timestamp=datetime.now(timezone.utc), title="T", summary="S",
            sentiment=2.0, relevance=0.8, impact=0.6, confidence=0.7,
        )


def test_aggregated_news_signal_defaults_to_empty_evidence():
    signal = AggregatedNewsSignal(
        signal=0.0, confidence=0.0, relevance=0.0, impact=0.0,
        article_count=0, raw_article_count=0, articles_after_dedup=0,
    )
    assert signal.evidence == []


def test_news_analysis_result_requires_execution_metadata():
    metadata = NewsExecutionMetadata(
        total_duration_ms=1.0, raw_article_count=1, articles_after_dedup=1, articles_in_aggregation=1,
    )
    result = NewsAnalysisResult(
        symbol="AAPL", prediction=Prediction.HOLD, confidence=0.0, expected_return=0.0,
        expected_volatility=20.0, relevance=0.0, impact=0.0, article_count=0,
        execution_metadata=metadata,
    )
    assert result.prediction == Prediction.HOLD
    assert result.structured_evidence == []
