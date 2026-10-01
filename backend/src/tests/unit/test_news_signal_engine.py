"""
Unit tests for signals/news.py (NewsSignalEngine).

Tests verify:
  - Items below the relevance floor are skipped
  - Items with near-zero sentiment and no classified event are skipped
  - A relevant, sentiment-bearing item produces a Signal with category=NEWS
  - Direction follows sentiment sign
  - contribution scales with sentiment * impact
  - Empty input -> empty EngineResult (NEUTRAL, 0 signals)
  - Aggregation delegates to EngineResult.from_signals() (shared with other engines)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from datetime import datetime, timezone

from news.models import EventType, FinancialEvent, NewsItemContext, RawNewsItem
from signals.news import NewsSignalEngine


def _item(
    sentiment_score: float = 0.0,
    relevance_score: float = 1.0,
    impact_score: float = 1.0,
    event_type: EventType = EventType.UNCLASSIFIED,
    title: str = "Some headline",
) -> NewsItemContext:
    raw = RawNewsItem(title=title, summary="", published_at=datetime.now(timezone.utc), source="Reuters")
    ctx = NewsItemContext(raw=raw)
    ctx.sentiment_score = sentiment_score
    ctx.relevance_score = relevance_score
    ctx.impact_score = impact_score
    ctx.event = FinancialEvent(event_type=event_type, confidence=0.8, severity=0.7)
    return ctx


class TestNewsSignalEngine:
    def setup_method(self):
        self.engine = NewsSignalEngine()

    def test_empty_input_returns_empty_engine_result(self):
        result = self.engine.generate([])
        assert result.engine == "NEWS"
        assert result.signals == []
        assert result.direction == "NEUTRAL"

    def test_low_relevance_item_is_skipped(self):
        item = _item(sentiment_score=0.8, relevance_score=0.05)
        result = self.engine.generate([item])
        assert result.signals == []

    def test_near_zero_sentiment_without_event_is_skipped(self):
        item = _item(sentiment_score=0.01, relevance_score=1.0, event_type=EventType.UNCLASSIFIED)
        result = self.engine.generate([item])
        assert result.signals == []

    def test_bullish_sentiment_produces_bullish_signal(self):
        item = _item(sentiment_score=0.6, relevance_score=1.0, impact_score=0.8, event_type=EventType.EARNINGS_BEAT)
        result = self.engine.generate([item])
        assert len(result.signals) == 1
        signal = result.signals[0]
        assert signal.direction == "BULLISH"
        assert signal.category == "NEWS"
        assert signal.contribution > 0

    def test_bearish_sentiment_produces_bearish_signal(self):
        item = _item(sentiment_score=-0.6, relevance_score=1.0, impact_score=0.8, event_type=EventType.EARNINGS_MISS)
        result = self.engine.generate([item])
        signal = result.signals[0]
        assert signal.direction == "BEARISH"
        assert signal.contribution < 0

    def test_event_with_negligible_sentiment_still_produces_signal(self):
        # A classified event with near-zero sentiment is still signal-worthy.
        item = _item(sentiment_score=0.0, relevance_score=1.0, impact_score=0.5, event_type=EventType.MERGER)
        result = self.engine.generate([item])
        assert len(result.signals) == 1

    def test_contribution_scales_with_impact(self):
        low_impact  = _item(sentiment_score=0.6, relevance_score=1.0, impact_score=0.2, event_type=EventType.EARNINGS_BEAT)
        high_impact = _item(sentiment_score=0.6, relevance_score=1.0, impact_score=1.0, event_type=EventType.EARNINGS_BEAT)
        low_signal  = self.engine.generate([low_impact]).signals[0]
        high_signal = self.engine.generate([high_impact]).signals[0]
        assert abs(high_signal.contribution) > abs(low_signal.contribution)

    def test_aggregate_uses_shared_engine_result_from_signals(self):
        bullish = _item(sentiment_score=0.8, relevance_score=1.0, impact_score=1.0, event_type=EventType.EARNINGS_BEAT)
        result = self.engine.generate([bullish])
        assert result.aggregate_score == sum(s.contribution for s in result.signals)
        assert result.direction == "BULLISH"

    def test_signal_ids_are_unique(self):
        items = [
            _item(sentiment_score=0.6, event_type=EventType.EARNINGS_BEAT, title="A"),
            _item(sentiment_score=-0.6, event_type=EventType.EARNINGS_MISS, title="B"),
        ]
        result = self.engine.generate(items)
        ids = [s.signal_id for s in result.signals]
        assert len(ids) == len(set(ids))
