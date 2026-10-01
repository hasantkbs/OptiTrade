"""
News Signal Engine — Phase B2
================================
Converts pipeline-enriched news items (news.pipeline.NewsPipeline output)
into structured Signal objects, consistent with TechnicalSignalEngine and
FundamentalSignalEngine.

This is the final pipeline stage:
    ... -> Event Classification -> Sentiment -> [NewsSignalEngine]

It is intentionally decoupled from core.news_analyzer / the iOS-facing
news_analysis response: this engine feeds SignalCollection for the future
DecisionEngine (Phase C), not the legacy score_delta path.
"""
from __future__ import annotations

from typing import List, Optional

from news.models import EventType, NewsItemContext
from signals.models import EngineResult, Signal

_CATEGORY  = "NEWS"
_TIMEFRAME = "SHORT"

# Items less relevant to the target symbol than this are treated as noise.
_MIN_RELEVANCE = 0.15

# Sentiment magnitude below this, with no notable event, is not signal-worthy.
_MIN_SENTIMENT = 0.05


class NewsSignalEngine:
    """Converts one symbol's enriched news items into an EngineResult."""

    def generate(self, items: List[NewsItemContext]) -> EngineResult:
        signals: List[Signal] = []
        for idx, item in enumerate(items):
            if item.relevance_score < _MIN_RELEVANCE:
                continue
            signal = self._to_signal(item, idx)
            if signal is not None:
                signals.append(signal)
        return EngineResult.from_signals("NEWS", signals)

    def _to_signal(self, item: NewsItemContext, idx: int) -> Optional[Signal]:
        has_event = item.event is not None and item.event.event_type != EventType.UNCLASSIFIED
        if abs(item.sentiment_score) < _MIN_SENTIMENT and not has_event:
            return None

        direction = (
            "BULLISH" if item.sentiment_score > _MIN_SENTIMENT else
            "BEARISH" if item.sentiment_score < -_MIN_SENTIMENT else
            "NEUTRAL"
        )
        normalized_value = round((item.sentiment_score + 1) / 2, 4)
        contribution = round(item.sentiment_score * item.impact_score * 15, 2)

        confidence = round(
            min(1.0, 0.4 + 0.3 * item.relevance_score + 0.3 * item.impact_score), 3
        )

        strength = (
            "STRONG"   if abs(contribution) >= 8 else
            "MODERATE" if abs(contribution) >= 3 else
            "WEAK"
        )

        event_type = item.event.event_type.value if item.event else EventType.UNCLASSIFIED.value
        reason = f'{event_type}: "{item.raw.title[:80]}" (sentiment {item.sentiment_score:+.2f})'

        return Signal(
            signal_id        = f"news_{idx}_{event_type.lower()}_{direction.lower()}",
            indicator         = "News Sentiment",
            value             = item.sentiment_score,
            normalized_value  = normalized_value,
            direction         = direction,
            strength          = strength,
            confidence        = confidence,
            contribution      = contribution,
            reason            = reason,
            timeframe         = _TIMEFRAME,
            category          = _CATEGORY,
        )
