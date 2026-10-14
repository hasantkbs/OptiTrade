"""OptiTrade — News feature backfill via Finnhub (free tier).

Usage (from backend/src):
  python scripts/backfill_news_features.py [--days-back 350]

Prerequisite: FINNHUB_API_KEY in backend/.env (free tier: 60 calls/min,
~1 year of historical company news - confirmed live: queries into
2025-10 return real articles, 2025-10-01..07 returns none).

Reuses the EXISTING News engine pipeline (engines/news/normalizer,
deduplicator, aggregator - the exact same scoring/decay/aggregation
code the live NewsFeatureAdapter uses) rather than reimplementing
sentiment/relevance/impact scoring - only the raw-fetch step differs
(Finnhub's historical company-news endpoint instead of
engines.news.providers.fetch_raw_articles' live yfinance call).

aggregator.aggregate() previously hardcoded `datetime.now()` for its
article-age cutoff/decay - harmless for live scoring, but it would
have treated every backfilled historical article as however old it
is relative to TODAY, not the historical snapshot date being
backfilled, silently filtering out everything. Added an optional
`as_of` parameter there (defaults to real "now", zero behavior change
for the live caller) so this script can score each historical day's
7-day trailing article window exactly as the live engine would have
scored it on that day - the same point-in-time discipline as the
Technical and SEC Fundamentals backfills.

Finnhub's company-news endpoint silently truncates to roughly the
most recent ~245 articles when a date range is too wide (verified
live: AAPL's 2026-09-01..2026-10-14 range returned only 245 articles,
all from the last 5 days) - fetched in weekly chunks per symbol to
avoid this, matching max_age_days=7's own window size.

Idempotent: a day already fully backfilled (all 5 News feature names
present) is skipped on a rerun.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
sys.path.insert(0, ".")

from datetime import datetime, timedelta, timezone
from typing import List

import httpx
from dotenv import load_dotenv

load_dotenv()
import os

from core.market_config import US_SYMBOLS
from engines.news import aggregator, deduplicator, normalizer
from engines.news.config import ALL_FEATURE_NAMES, NewsEngineConfig
from engines.news.models import RawArticle
from feature_store.models import FeatureRecord
from feature_store.offline_store import PostgresOfflineStore

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

_FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
_REQUEST_PACE_SECONDS = 1.1  # ~55 req/min, comfortably under Finnhub's 60/min free-tier limit
_MAX_ARTICLES_PER_SNAPSHOT = 15  # matches NewsEngineConfig.max_articles (the live engine's own cap)


def _fetch_week(symbol: str, start: datetime, end: datetime) -> List[RawArticle]:
    try:
        resp = httpx.get(
            "https://finnhub.io/api/v1/company-news",
            params={
                "symbol": symbol, "from": start.strftime("%Y-%m-%d"), "to": end.strftime("%Y-%m-%d"),
                "token": _FINNHUB_API_KEY,
            },
            timeout=20.0,
        )
        if resp.status_code != 200:
            return []
        articles = []
        for item in resp.json():
            headline = item.get("headline")
            ts = item.get("datetime")
            if not headline or not ts:
                continue
            articles.append(RawArticle(
                title=headline, summary=item.get("summary", ""),
                published_at=datetime.fromtimestamp(ts, tz=timezone.utc),
                source=item.get("source", "Finnhub"),
            ))
        return articles
    except Exception as exc:
        logger.warning("%s: news fetch failed for %s..%s: %s", symbol, start.date(), end.date(), exc)
        return []
    finally:
        time.sleep(_REQUEST_PACE_SECONDS)


def fetch_symbol_history(symbol: str, start: datetime, end: datetime) -> List[RawArticle]:
    """Fetches `symbol`'s full article history over [start, end] in
    weekly chunks (see module docstring for why), deduplicated by
    (title, published_at) across chunk boundaries."""
    all_articles: List[RawArticle] = []
    seen = set()
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=7), end)
        for article in _fetch_week(symbol, cursor, chunk_end):
            key = (article.title, article.published_at)
            if key not in seen:
                seen.add(key)
                all_articles.append(article)
        cursor = chunk_end + timedelta(days=1)
    return all_articles


def already_backfilled(store: PostgresOfflineStore, symbol: str, day_end_utc: datetime) -> bool:
    for feature_name in ALL_FEATURE_NAMES:
        record = store.get_as_of(symbol, feature_name, day_end_utc, respect_ingestion_time=False)
        if record is None or record.event_timestamp.astimezone(timezone.utc).date() != day_end_utc.date():
            return False
    return True


def backfill_symbol(
    store: PostgresOfflineStore, config: NewsEngineConfig, symbol: str, articles: List[RawArticle],
    start: datetime, end: datetime,
) -> int:
    written = 0
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:  # trading days only, matching the Technical backfill's own convention
            day_end_utc = datetime(cursor.year, cursor.month, cursor.day, 23, 59, 59, tzinfo=timezone.utc)
            if not already_backfilled(store, symbol, day_end_utc):
                window_start = day_end_utc - timedelta(days=config.max_age_days)
                window_articles = sorted(
                    (a for a in articles if window_start <= a.published_at <= day_end_utc),
                    key=lambda a: a.published_at, reverse=True,
                )[:_MAX_ARTICLES_PER_SNAPSHOT]

                normalized = normalizer.normalize_all(window_articles)
                deduped = deduplicator.deduplicate(normalized, config.dedup_similarity_threshold)
                result = aggregator.aggregate(
                    symbol, deduped, config, raw_article_count=len(window_articles),
                    articles_after_dedup=len(deduped), as_of=day_end_utc,
                )
                values = {
                    ALL_FEATURE_NAMES[0]: result.signal, ALL_FEATURE_NAMES[1]: result.relevance,
                    ALL_FEATURE_NAMES[2]: result.impact, ALL_FEATURE_NAMES[3]: result.confidence,
                    ALL_FEATURE_NAMES[4]: float(result.article_count),
                }
                for feature_name, value in values.items():
                    store.insert(FeatureRecord(
                        symbol=symbol, feature_name=feature_name, value=float(value), version="v1",
                        event_timestamp=day_end_utc, ingestion_timestamp=day_end_utc,
                    ))
                written += 1
        cursor += timedelta(days=1)
    return written


def main() -> None:
    if not _FINNHUB_API_KEY:
        print("FINNHUB_API_KEY not set in backend/.env")
        raise SystemExit(1)

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days-back", type=int, default=350)
    args = parser.parse_args()

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days_back)
    symbols = list(US_SYMBOLS.keys())

    print("=" * 65)
    print("OptiTrade - News Feature Backfill (Finnhub free tier)")
    print(f"Range: {start.date().isoformat()} .. {end.date().isoformat()} | Symbols: {len(symbols)}")
    print("=" * 65)

    store = PostgresOfflineStore()
    config = NewsEngineConfig.from_env()

    total_written = 0
    for symbol in symbols:
        print(f"  {symbol}: fetching article history...", end=" ", flush=True)
        articles = fetch_symbol_history(symbol, start, end)
        print(f"{len(articles)} articles, backfilling days...", end=" ", flush=True)
        try:
            written = backfill_symbol(store, config, symbol, articles, start, end)
        except Exception as exc:
            logger.warning("%s: backfill_symbol raised %s: %s, skipping entirely", symbol, type(exc).__name__, exc)
            written = 0
        total_written += written
        print(f"{written} days written")

    print(f"\nToplam: {total_written} sembol-gün yazıldı.")
    print("=" * 65)


if __name__ == "__main__":
    main()
