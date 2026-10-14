"""Unit tests for scripts/backfill_news_features.py's pure logic - day
windowing, idempotency, and the article-count cap. A fake in-memory
store stands in for PostgresOfflineStore. The actual end-to-end run
against Finnhub's live API is exercised manually, matching
test_train_ml_candidate.py's own precedent."""
import sys
sys.path.insert(0, ".")

from datetime import datetime, timedelta, timezone

from engines.news.config import ALL_FEATURE_NAMES, NewsEngineConfig
from engines.news.models import RawArticle
from feature_store.models import FeatureRecord
from scripts.backfill_news_features import already_backfilled, backfill_symbol


class _FakeOfflineStore:
    def __init__(self) -> None:
        self.records: list[FeatureRecord] = []

    def get_as_of(self, symbol, feature_name, as_of, respect_ingestion_time=False):
        matches = [
            r for r in self.records
            if r.symbol == symbol and r.feature_name == feature_name and r.event_timestamp <= as_of
        ]
        return max(matches, key=lambda r: r.event_timestamp) if matches else None

    def insert(self, record: FeatureRecord) -> None:
        self.records.append(record)


def _article(title: str, published_at: datetime) -> RawArticle:
    return RawArticle(title=title, summary="", published_at=published_at, source="Finnhub")


def test_already_backfilled_is_false_when_nothing_written():
    store = _FakeOfflineStore()
    day = datetime(2026, 1, 5, 23, 59, 59, tzinfo=timezone.utc)
    assert already_backfilled(store, "AAPL", day) is False


def test_already_backfilled_requires_all_five_features_for_that_exact_day():
    store = _FakeOfflineStore()
    day = datetime(2026, 1, 5, 23, 59, 59, tzinfo=timezone.utc)
    for name in ALL_FEATURE_NAMES[:4]:  # only 4 of 5
        store.insert(FeatureRecord(symbol="AAPL", feature_name=name, value=0.0, event_timestamp=day, ingestion_timestamp=day))
    assert already_backfilled(store, "AAPL", day) is False

    store.insert(FeatureRecord(
        symbol="AAPL", feature_name=ALL_FEATURE_NAMES[4], value=0.0, event_timestamp=day, ingestion_timestamp=day,
    ))
    assert already_backfilled(store, "AAPL", day) is True


def test_backfill_symbol_writes_one_row_per_feature_per_trading_day():
    store = _FakeOfflineStore()
    config = NewsEngineConfig()
    start = datetime(2026, 1, 5, tzinfo=timezone.utc)  # a Monday
    end = datetime(2026, 1, 6, tzinfo=timezone.utc)  # a Tuesday
    articles = [_article("Apple (AAPL) surges on record earnings beat", start)]

    written = backfill_symbol(store, config, "AAPL", articles, start, end)

    assert written == 2  # Monday + Tuesday, both trading days
    assert len(store.records) == 2 * len(ALL_FEATURE_NAMES)


def test_backfill_symbol_skips_weekends():
    store = _FakeOfflineStore()
    config = NewsEngineConfig()
    start = datetime(2026, 1, 3, tzinfo=timezone.utc)  # a Saturday
    end = datetime(2026, 1, 4, tzinfo=timezone.utc)  # a Sunday
    written = backfill_symbol(store, config, "AAPL", [], start, end)
    assert written == 0


def test_backfill_symbol_is_idempotent_on_rerun():
    store = _FakeOfflineStore()
    config = NewsEngineConfig()
    day = datetime(2026, 1, 5, tzinfo=timezone.utc)
    articles = [_article("Apple (AAPL) surges on record earnings beat", day)]

    first = backfill_symbol(store, config, "AAPL", articles, day, day)
    second = backfill_symbol(store, config, "AAPL", articles, day, day)

    assert first == 1
    assert second == 0
    assert len(store.records) == len(ALL_FEATURE_NAMES)


def test_backfill_symbol_only_uses_articles_within_the_trailing_window():
    store = _FakeOfflineStore()
    config = NewsEngineConfig(max_age_days=7)
    day = datetime(2026, 1, 15, tzinfo=timezone.utc)
    recent = _article("Apple (AAPL) surges on record earnings beat", day - timedelta(days=2))
    stale = _article("Apple (AAPL) old news from a month ago", day - timedelta(days=30))

    backfill_symbol(store, config, "AAPL", [recent, stale], day, day)

    article_count_record = next(r for r in store.records if r.feature_name == ALL_FEATURE_NAMES[4])
    assert article_count_record.value == 1.0  # only the recent one counted


def test_backfill_symbol_caps_at_fifteen_most_recent_articles_in_the_window():
    store = _FakeOfflineStore()
    config = NewsEngineConfig()
    day = datetime(2026, 1, 15, tzinfo=timezone.utc)
    articles = [
        _article(f"Apple (AAPL) earnings update number {i}", day - timedelta(hours=i))
        for i in range(20)
    ]

    backfill_symbol(store, config, "AAPL", articles, day, day)

    article_count_record = next(r for r in store.records if r.feature_name == ALL_FEATURE_NAMES[4])
    assert article_count_record.value <= 15.0
