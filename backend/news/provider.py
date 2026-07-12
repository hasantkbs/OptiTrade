"""
Provider stage — fetches raw news items for a symbol.

Wraps the existing core.news_analyzer._fetch_yfinance_news() fetch logic
(reused, not reimplemented) so the legacy news_analyzer module and this
pipeline share one source of truth for the yfinance call.  NewsProvider is
a Protocol so future sources (SEC filings, Reddit, X, earnings calendar,
economic calendar) can be added as new implementations without touching
the pipeline.
"""
from __future__ import annotations

from typing import List, Protocol, runtime_checkable

from core.news_analyzer import _fetch_yfinance_news
from news.models import RawNewsItem


@runtime_checkable
class NewsProvider(Protocol):
    def fetch(self, symbol: str, max_items: int = 15) -> List[RawNewsItem]:
        ...


class YFinanceNewsProvider:
    """Adapts core.news_analyzer's yfinance fetch into RawNewsItem DTOs."""

    def fetch(self, symbol: str, max_items: int = 15) -> List[RawNewsItem]:
        raw_dicts = _fetch_yfinance_news(symbol, max_news=max_items)
        return [
            RawNewsItem(
                title=d["title"],
                summary=d["summary"],
                published_at=d["published_at"],
                source=d["source"],
            )
            for d in raw_dicts
        ]
