"""
Unit tests for the News Intelligence Pipeline (backend/news/).

Tests verify each stage in isolation:
  - NewsNormalizer: HTML/whitespace cleanup, stable content hash
  - NewsDeduplicator: marks repeated content hashes as duplicates
  - DeterministicEntityExtractor: ticker/company/sector/macro recognition,
    case-sensitivity guard against false positives
  - SymbolAssetResolver: entities -> deduplicated symbol list
  - RelevanceScorer: target mention, matching sector, macro, unrelated
  - ImpactScorer: recency + specificity, independent of event classification
  - EventClassifier: taxonomy coverage + unclassified fallback
  - LexiconSentimentAnalyzer: thin pass-through to core.news_analyzer.analyze_sentiment
  - NewsPipeline: end-to-end wiring with a mocked provider (no network),
    duplicate filtering, correct stage order

No network calls; the provider is always mocked/faked.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from datetime import datetime, timedelta, timezone
from typing import List

from news.asset_resolver import SymbolAssetResolver
from news.deduplicator import NewsDeduplicator
from news.entity_extraction import DeterministicEntityExtractor
from news.event_classification import EventClassifier
from news.impact import ImpactScorer
from news.models import Entity, EntityType, EventType, NewsItemContext, RawNewsItem
from news.normalizer import NewsNormalizer
from news.pipeline import NewsPipeline
from news.relevance import RelevanceScorer
from news.sentiment import LexiconSentimentAnalyzer


def _raw(title: str, summary: str = "", hours_ago: float = 1.0, source: str = "Reuters") -> RawNewsItem:
    return RawNewsItem(
        title=title,
        summary=summary,
        published_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
        source=source,
    )


# ── Normalizer ────────────────────────────────────────────────────────────────

class TestNewsNormalizer:
    def test_cleans_html_and_whitespace(self):
        raw = _raw("Apple  <b>beats</b>   estimates", "Strong   quarter <i>overall</i>")
        ctx = NewsNormalizer().normalize(raw)
        assert "<b>" not in ctx.text
        assert "  " not in ctx.text
        assert ctx.text.startswith("Apple beats estimates.")

    def test_stable_hash_for_identical_titles(self):
        raw1 = _raw("Tesla Beats Estimates")
        raw2 = _raw("tesla   beats estimates!!")
        ctx1 = NewsNormalizer().normalize(raw1)
        ctx2 = NewsNormalizer().normalize(raw2)
        assert ctx1.content_hash == ctx2.content_hash

    def test_different_titles_hash_differently(self):
        ctx1 = NewsNormalizer().normalize(_raw("Tesla beats estimates"))
        ctx2 = NewsNormalizer().normalize(_raw("Tesla misses estimates"))
        assert ctx1.content_hash != ctx2.content_hash

    def test_no_summary_falls_back_to_title_only(self):
        ctx = NewsNormalizer().normalize(_raw("Just a title", ""))
        assert ctx.text == "Just a title"


# ── Deduplicator ──────────────────────────────────────────────────────────────

class TestNewsDeduplicator:
    def test_marks_second_occurrence_as_duplicate(self):
        normalizer = NewsNormalizer()
        items = [
            normalizer.normalize(_raw("Same Story", source="Reuters")),
            normalizer.normalize(_raw("same   story!", source="Bloomberg")),
            normalizer.normalize(_raw("Different Story", source="Reuters")),
        ]
        result = NewsDeduplicator().deduplicate(items)
        assert result[0].is_duplicate is False
        assert result[1].is_duplicate is True
        assert result[2].is_duplicate is False

    def test_empty_list(self):
        assert NewsDeduplicator().deduplicate([]) == []


# ── DeterministicEntityExtractor ──────────────────────────────────────────────

class TestDeterministicEntityExtractor:
    def setup_method(self):
        self.extractor = DeterministicEntityExtractor()

    def test_recognizes_ticker(self):
        entities = self.extractor.extract("TSLA shares rallied after hours.")
        symbols = {e.symbol for e in entities if e.entity_type == EntityType.TICKER}
        assert "TSLA" in symbols

    def test_recognizes_company_name_case_insensitively(self):
        entities = self.extractor.extract("apple unveiled a new product today.")
        symbols = {e.symbol for e in entities if e.entity_type == EntityType.COMPANY}
        assert "AAPL" in symbols

    def test_lowercase_ticker_text_does_not_match(self):
        # "ge" lowercase should not match the GE ticker (case-sensitive ticker match).
        entities = self.extractor.extract("we need to charge the phone before we ge going.")
        symbols = {e.symbol for e in entities if e.entity_type == EntityType.TICKER}
        assert "GE" not in symbols

    def test_recognizes_sector_keyword(self):
        entities = self.extractor.extract("OPEC production cut lifts oil price rise expectations.")
        sector_entities = [e for e in entities if e.entity_type == EntityType.SECTOR]
        assert any(e.sector == "ENERGY" for e in sector_entities)

    def test_recognizes_macro_keyword(self):
        entities = self.extractor.extract("Federal reserve hawkish stance spooks markets.")
        macro_entities = [e for e in entities if e.entity_type == EntityType.MACRO]
        assert any(e.sector == "MACRO" for e in macro_entities)

    def test_empty_text_returns_no_entities(self):
        assert self.extractor.extract("") == []

    def test_does_not_duplicate_symbol_entities(self):
        entities = self.extractor.extract("AAPL AAPL AAPL surges as Apple posts record profit.")
        symbols = [e.symbol for e in entities if e.symbol == "AAPL"]
        assert len(symbols) == 1


# ── SymbolAssetResolver ────────────────────────────────────────────────────────

class TestSymbolAssetResolver:
    def test_resolves_ticker_and_company_entities(self):
        entities = [
            Entity(text="AAPL", entity_type=EntityType.TICKER, symbol="AAPL"),
            Entity(text="apple", entity_type=EntityType.COMPANY, symbol="AAPL"),
            Entity(text="tesla", entity_type=EntityType.COMPANY, symbol="TSLA"),
            Entity(text="oil price rise", entity_type=EntityType.SECTOR, sector="ENERGY"),
        ]
        symbols = SymbolAssetResolver().resolve(entities, "AAPL")
        assert symbols == ["AAPL", "TSLA"]

    def test_no_symbol_entities_returns_empty(self):
        entities = [Entity(text="federal reserve hawkish", entity_type=EntityType.MACRO, sector="MACRO")]
        assert SymbolAssetResolver().resolve(entities, "AAPL") == []


# ── RelevanceScorer ────────────────────────────────────────────────────────────

def _ctx_with(entities: List[Entity], resolved_symbols=None, mentions_target=False) -> NewsItemContext:
    ctx = NewsItemContext(raw=_raw("headline"))
    ctx.entities = entities
    ctx.resolved_symbols = resolved_symbols or []
    ctx.mentions_target = mentions_target
    return ctx


class TestRelevanceScorer:
    def setup_method(self):
        self.scorer = RelevanceScorer()

    def test_target_mention_scores_max(self):
        ctx = _ctx_with([], resolved_symbols=["AAPL"], mentions_target=True)
        assert self.scorer.score(ctx, "AAPL") == 1.0

    def test_matching_sector_scores_moderate(self):
        ctx = _ctx_with([Entity(text="oil price rise", entity_type=EntityType.SECTOR, sector="ENERGY")])
        assert self.scorer.score(ctx, "XOM") == 0.7  # XOM is in ENERGY sector_symbols

    def test_macro_only_scores_low_moderate(self):
        ctx = _ctx_with([Entity(text="federal reserve hawkish", entity_type=EntityType.MACRO, sector="MACRO")])
        assert self.scorer.score(ctx, "AAPL") == 0.4

    def test_unrelated_symbol_scores_low(self):
        ctx = _ctx_with([], resolved_symbols=["TSLA"])
        assert self.scorer.score(ctx, "AAPL") == 0.15

    def test_completely_irrelevant_scores_minimal(self):
        ctx = _ctx_with([])
        assert self.scorer.score(ctx, "AAPL") == 0.05


# ── ImpactScorer ───────────────────────────────────────────────────────────────

class TestImpactScorer:
    def setup_method(self):
        self.scorer = ImpactScorer()

    def test_recent_target_mention_has_high_impact(self):
        ctx = NewsItemContext(raw=_raw("headline", hours_ago=1))
        ctx.mentions_target = True
        ctx.relevance_score = 1.0
        assert self.scorer.score(ctx) == 1.0

    def test_old_news_has_lower_impact(self):
        ctx = NewsItemContext(raw=_raw("headline", hours_ago=200))
        ctx.mentions_target = True
        ctx.relevance_score = 1.0
        assert self.scorer.score(ctx) == 0.1

    def test_unrelated_symbol_mentioned_reduces_specificity(self):
        ctx = NewsItemContext(raw=_raw("headline", hours_ago=1))
        ctx.mentions_target = False
        ctx.resolved_symbols = ["TSLA"]
        ctx.relevance_score = 0.15
        score = self.scorer.score(ctx)
        assert 0 < score < 0.15

    def test_score_bounded_between_zero_and_one(self):
        ctx = NewsItemContext(raw=_raw("headline", hours_ago=1))
        ctx.relevance_score = 1.0
        ctx.mentions_target = True
        assert 0.0 <= self.scorer.score(ctx) <= 1.0


# ── EventClassifier ────────────────────────────────────────────────────────────

class TestEventClassifier:
    def setup_method(self):
        self.classifier = EventClassifier()

    def test_earnings_beat(self):
        event = self.classifier.classify("Company beats expectations with blowout earnings")
        assert event.event_type == EventType.EARNINGS_BEAT

    def test_earnings_miss(self):
        event = self.classifier.classify("Company misses expectations this quarter")
        assert event.event_type == EventType.EARNINGS_MISS

    def test_merger(self):
        event = self.classifier.classify("Company A to merge with Company B")
        assert event.event_type == EventType.MERGER

    def test_acquisition(self):
        event = self.classifier.classify("Big Corp acquires small startup for $2B")
        assert event.event_type == EventType.ACQUISITION

    def test_bankruptcy(self):
        event = self.classifier.classify("Retailer files for bankruptcy amid mounting debt")
        assert event.event_type == EventType.BANKRUPTCY
        assert event.severity >= 0.9

    def test_dividend(self):
        event = self.classifier.classify("Company declares dividend increase for shareholders")
        assert event.event_type == EventType.DIVIDEND

    def test_rate_decision(self):
        event = self.classifier.classify("Federal Reserve announces rate hike")
        assert event.event_type == EventType.RATE_DECISION

    def test_product_release(self):
        event = self.classifier.classify("Company unveils new product line at expo")
        assert event.event_type == EventType.PRODUCT_RELEASE

    def test_regulation(self):
        event = self.classifier.classify("New regulation targets tech antitrust practices")
        assert event.event_type == EventType.REGULATION

    def test_sec_investigation(self):
        event = self.classifier.classify("Company faces SEC investigation over disclosures")
        assert event.event_type == EventType.SEC_INVESTIGATION

    def test_hack(self):
        event = self.classifier.classify("Crypto exchange hack drains millions from wallets")
        assert event.event_type == EventType.HACK

    def test_token_unlock(self):
        event = self.classifier.classify("Major token unlock scheduled for next week")
        assert event.event_type == EventType.TOKEN_UNLOCK

    def test_etf_approval(self):
        event = self.classifier.classify("SEC approves spot bitcoin ETF applications")
        assert event.event_type == EventType.ETF_APPROVAL

    def test_unclassified_fallback(self):
        event = self.classifier.classify("Local weather remains sunny this weekend")
        assert event.event_type == EventType.UNCLASSIFIED
        assert event.confidence == 0.0

    def test_empty_text(self):
        event = self.classifier.classify("")
        assert event.event_type == EventType.UNCLASSIFIED

    def test_confidence_scales_with_keyword_matches(self):
        single = self.classifier.classify("Company beats expectations")
        multi  = self.classifier.classify("Company beats expectations with blowout earnings beating estimates")
        assert multi.confidence >= single.confidence


# ── LexiconSentimentAnalyzer ──────────────────────────────────────────────────

class TestLexiconSentimentAnalyzer:
    def test_delegates_to_existing_lexicon_engine(self):
        score, keywords = LexiconSentimentAnalyzer().analyze("Stock surges to record high on strong earnings")
        assert score > 0
        assert len(keywords) > 0

    def test_negative_text(self):
        score, _ = LexiconSentimentAnalyzer().analyze("Stock plunges after bankruptcy fears and fraud allegations")
        assert score < 0


# ── NewsPipeline (integration) ────────────────────────────────────────────────

class _FakeProvider:
    def __init__(self, raw_items: List[RawNewsItem]):
        self._raw_items = raw_items

    def fetch(self, symbol: str, max_items: int = 15) -> List[RawNewsItem]:
        return self._raw_items[:max_items]


class TestNewsPipeline:
    def test_end_to_end_enriches_every_field(self):
        provider = _FakeProvider([
            _raw("Apple beats expectations with blowout earnings", "AAPL surges after hours", hours_ago=1),
        ])
        pipeline = NewsPipeline(provider=provider)
        results = pipeline.run("AAPL")

        assert len(results) == 1
        item = results[0]
        assert item.text
        assert item.content_hash
        assert item.is_duplicate is False
        assert any(e.symbol == "AAPL" for e in item.entities)
        assert "AAPL" in item.resolved_symbols
        assert item.mentions_target is True
        assert item.relevance_score == 1.0
        assert item.impact_score > 0
        assert item.event is not None
        assert item.event.event_type == EventType.EARNINGS_BEAT
        assert item.sentiment_score != 0.0

    def test_duplicates_are_filtered_out_of_results(self):
        provider = _FakeProvider([
            _raw("Same Headline", source="Reuters"),
            _raw("same headline", source="Bloomberg"),
        ])
        pipeline = NewsPipeline(provider=provider)
        results = pipeline.run("AAPL")
        assert len(results) == 1

    def test_no_news_returns_empty_list(self):
        pipeline = NewsPipeline(provider=_FakeProvider([]))
        assert pipeline.run("AAPL") == []

    def test_max_items_respected(self):
        provider = _FakeProvider([_raw(f"Headline {i}") for i in range(5)])
        pipeline = NewsPipeline(provider=provider)
        results = pipeline.run("AAPL", max_items=2)
        assert len(results) == 2
