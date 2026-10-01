"""
Integration tests for Phase B2.1 — NewsPipeline wired into core.analyzer.analyze().

Tests verify:
  - A successful news pipeline populates signal_details["news"]
  - The legacy news_analysis response is always built from
    core.news_analyzer.analyze_news() and is byte-for-byte identical
    regardless of whether the new pipeline succeeds or fails
  - Any failure inside the new pipeline (provider, entity extraction,
    sentiment) is swallowed: analyze() still returns a full AnalysisResult,
    Technical/Fundamental signals still run, legacy news_analysis still runs
  - Empty provider response -> "news" present with signal_count 0
  - Duplicate / multi-source articles are deduplicated before scoring
  - Irrelevant-only articles -> "news" present but with signal_count 0

core.analyzer.fetch_history is patched with a synthetic OHLCV series so no
network call is made; core.analyzer.analyze_news (the legacy engine) is
patched with a canned result for the same reason. asset_type="crypto" is
used throughout so the Fundamental engine (which calls yfinance) is
skipped, keeping these tests fully offline.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from datetime import datetime, timezone
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from core import analyzer
from core.news_analyzer import NewsAnalysisResult
from news.models import RawNewsItem
from news.pipeline import NewsPipeline


# ── Shared fixtures ────────────────────────────────────────────────────────────

def _make_hist(n: int = 90) -> pd.DataFrame:
    idx = pd.bdate_range(end=pd.Timestamp.now(tz="UTC").normalize(), periods=n)
    rng = np.random.default_rng(42)
    base   = 100 + np.cumsum(rng.normal(0.1, 1.0, n))
    close  = pd.Series(base, index=idx)
    high   = close + rng.uniform(0.1, 1.0, n)
    low    = close - rng.uniform(0.1, 1.0, n)
    open_  = close + rng.normal(0, 0.5, n)
    volume = pd.Series(rng.uniform(1_000_000, 5_000_000, n), index=idx)
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume})


_HIST = _make_hist()


def _legacy_news_result() -> NewsAnalysisResult:
    return NewsAnalysisResult(
        symbol="AAPL", sector="TECH", total_news=3, analyzed_news=3,
        sentiment_score=0.2, sentiment_label="SLIGHTLY_POSITIVE", score_delta=3,
        signals=["legacy signal: positive tech news"],
        positive_count=2, negative_count=1, neutral_count=0,
        top_positive_title="Legacy positive headline",
    )


class _FakeProvider:
    """Injectable NewsProvider returning a fixed list of RawNewsItem, or raising."""

    def __init__(self, items=None, exc: Exception = None):
        self._items = items or []
        self._exc = exc

    def fetch(self, symbol: str, max_items: int = 15):
        if self._exc:
            raise self._exc
        return self._items[:max_items]


class _FailingEntityExtractor:
    def extract(self, text: str):
        raise ValueError("entity extraction exploded")


def _raw(title: str, summary: str = "", source: str = "Reuters") -> RawNewsItem:
    return RawNewsItem(title=title, summary=summary, published_at=datetime.now(timezone.utc), source=source)


def _run_analyze(**kwargs):
    with patch("core.analyzer.fetch_history", return_value=_HIST), \
         patch("core.analyzer.analyze_news", return_value=_legacy_news_result()):
        return analyzer.analyze("AAPL", asset_type="crypto", **kwargs)


# ── Successful pipeline ────────────────────────────────────────────────────────

class TestSuccessfulNewsPipeline:
    def test_populates_signal_details_news(self):
        provider = _FakeProvider([
            _raw("Apple beats expectations with blowout earnings", "AAPL surges after hours"),
        ])
        result = _run_analyze(news_pipeline=NewsPipeline(provider=provider))

        assert result is not None
        assert result.signal_details is not None
        assert "news" in result.signal_details
        assert result.signal_details["news"]["signal_count"] >= 1
        assert result.signal_details["news"]["direction"] in ("BULLISH", "BEARISH", "NEUTRAL")

    def test_technical_signals_still_present_alongside_news(self):
        provider = _FakeProvider([_raw("Apple beats expectations with blowout earnings")])
        result = _run_analyze(news_pipeline=NewsPipeline(provider=provider))
        assert "technical" in result.signal_details

    def test_legacy_news_analysis_unchanged_shape(self):
        provider = _FakeProvider([_raw("Apple beats expectations with blowout earnings")])
        result = _run_analyze(news_pipeline=NewsPipeline(provider=provider))
        assert result.news_analysis["sentiment_score"] == 0.2
        assert result.news_analysis["sentiment_label"] == "SLIGHTLY_POSITIVE"
        assert result.news_analysis["top_positive_title"] == "Legacy positive headline"
        assert set(result.news_analysis.keys()) == {
            "sentiment_score", "sentiment_label", "score_delta", "positive_count",
            "negative_count", "total_news", "sector", "top_positive_title",
            "top_negative_title", "headlines",
        }


# ── Failure modes — must never break analyze() ────────────────────────────────

class TestNewsPipelineFailureModes:
    def test_provider_failure_is_swallowed(self):
        failing_pipeline = NewsPipeline(provider=_FakeProvider(exc=ConnectionError("provider down")))

        # Confirm the failure really does propagate out of the pipeline itself...
        with pytest.raises(ConnectionError):
            failing_pipeline.run("AAPL")

        # ...but analyze() must swallow it and continue normally.
        result = _run_analyze(news_pipeline=failing_pipeline)
        assert result is not None
        assert result.signal_details is not None
        assert "news" not in result.signal_details
        assert "technical" in result.signal_details

    def test_entity_extraction_failure_is_swallowed(self):
        provider = _FakeProvider([_raw("Apple beats expectations")])
        failing_pipeline = NewsPipeline(provider=provider, entity_extractor=_FailingEntityExtractor())

        with pytest.raises(ValueError):
            failing_pipeline.run("AAPL")

        result = _run_analyze(news_pipeline=failing_pipeline)
        assert result is not None
        assert "news" not in result.signal_details
        assert "technical" in result.signal_details

    def test_sentiment_failure_is_swallowed(self):
        provider = _FakeProvider([_raw("Apple beats expectations")])
        pipeline = NewsPipeline(provider=provider)

        with patch("news.sentiment.analyze_sentiment", side_effect=RuntimeError("sentiment engine down")):
            with pytest.raises(RuntimeError):
                pipeline.run("AAPL")

            result = _run_analyze(news_pipeline=pipeline)

        assert result is not None
        assert "news" not in result.signal_details
        assert "technical" in result.signal_details

    def test_news_signal_engine_failure_is_swallowed(self):
        provider = _FakeProvider([_raw("Apple beats expectations")])

        class _FailingSignalEngine:
            def generate(self, items):
                raise RuntimeError("signal engine exploded")

        result = _run_analyze(
            news_pipeline=NewsPipeline(provider=provider),
            news_signal_engine=_FailingSignalEngine(),
        )
        assert result is not None
        assert "news" not in result.signal_details
        assert "technical" in result.signal_details

    def test_legacy_news_analysis_unaffected_by_pipeline_failure(self):
        """news_analysis must be byte-for-byte identical whether the new
        pipeline succeeds or fails — it is built independently."""
        working_pipeline = NewsPipeline(provider=_FakeProvider([_raw("Apple beats expectations")]))
        failing_pipeline = NewsPipeline(provider=_FakeProvider(exc=ConnectionError("down")))

        result_ok   = _run_analyze(news_pipeline=working_pipeline)
        result_fail = _run_analyze(news_pipeline=failing_pipeline)

        assert result_ok.news_analysis == result_fail.news_analysis

    def test_analyze_never_raises_when_news_pipeline_is_none_of_the_above_but_still_broken(self):
        class _BrokenPipeline:
            def run(self, symbol, max_items=15):
                raise KeyError("unexpected")

        result = _run_analyze(news_pipeline=_BrokenPipeline())
        assert result is not None


# ── Empty / no-signal scenarios ────────────────────────────────────────────────

class TestNewsEdgeCases:
    def test_empty_provider_response(self):
        result = _run_analyze(news_pipeline=NewsPipeline(provider=_FakeProvider([])))
        assert result is not None
        assert result.signal_details is not None
        assert "news" in result.signal_details
        assert result.signal_details["news"]["signal_count"] == 0
        assert result.signal_details["news"]["direction"] == "NEUTRAL"

    def test_duplicate_articles_collapse_to_one_signal(self):
        provider = _FakeProvider([
            _raw("Apple beats expectations with blowout earnings", source="Reuters"),
            _raw("apple   beats expectations with blowout earnings!!", source="Bloomberg"),
        ])
        result = _run_analyze(news_pipeline=NewsPipeline(provider=provider))
        assert result.signal_details["news"]["signal_count"] == 1

    def test_multiple_sources_reporting_same_article_dedupes(self):
        provider = _FakeProvider([
            _raw("Fed announces rate hike", source="Reuters"),
            _raw("fed announces rate hike", source="Bloomberg"),
            _raw("fed announces rate hike", source="AP"),
            _raw("Company X unveils new product", source="Reuters"),
        ])
        result = _run_analyze(news_pipeline=NewsPipeline(provider=provider))
        # 3 copies of the same story + 1 distinct story -> at most 2 distinct signals
        assert result.signal_details["news"]["signal_count"] <= 2

    def test_no_relevant_articles_yields_zero_signals(self):
        # Uses the real extractor/relevance scorer: a headline with no
        # recognizable ticker/company/sector/macro keyword is irrelevant to AAPL.
        provider = _FakeProvider([_raw("Local bakery wins regional pastry competition")])
        result = _run_analyze(news_pipeline=NewsPipeline(provider=provider))
        assert result.signal_details is not None
        assert "news" in result.signal_details
        assert result.signal_details["news"]["signal_count"] == 0

    def test_default_pipeline_constructed_when_none_injected(self):
        """When no news_pipeline/news_signal_engine is passed, analyze()
        must construct its own (no shared singleton state) and must not
        raise even though this hits the real (mocked-away) yfinance path
        indirectly via YFinanceNewsProvider — verified by not crashing."""
        with patch("core.news_analyzer._fetch_yfinance_news", return_value=[]):
            result = _run_analyze()
        assert result is not None
