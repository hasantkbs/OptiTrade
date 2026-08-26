"""
OptiTrade News Engine — providers.

The ONLY module in this engine allowed to fetch raw news data. Reuses
`core.news_analyzer._fetch_yfinance_news` unchanged rather than
duplicating its yfinance-parsing logic (title/summary/pubDate/provider
extraction, malformed-timestamp fallback, network-error handling all
already exist there and are reused as-is).
"""
from __future__ import annotations

import logging
from typing import List

from core.news_analyzer import _fetch_yfinance_news
from core.structured_logging import STATUS_SUCCESS, log_event
from engines.news.models import RawArticle

logger = logging.getLogger(__name__)


def fetch_raw_articles(symbol: str, max_articles: int = 15) -> List[RawArticle]:
    """Fetches up to `max_articles` raw articles for `symbol`. Never
    raises - `_fetch_yfinance_news` already catches and logs its own
    network/parsing failures, returning `[]` on any error."""
    raw = _fetch_yfinance_news(symbol, max_news=max_articles)
    articles = [
        RawArticle(
            title=item["title"], summary=item.get("summary", ""),
            published_at=item["published_at"], source=item.get("source", "Unknown"),
        )
        for item in raw
    ]
    log_event(
        logger, component="news_engine", module="engines.news.providers",
        operation="fetch_raw_articles", status=STATUS_SUCCESS, symbol=symbol,
        articles_fetched=len(articles),
    )
    return articles
