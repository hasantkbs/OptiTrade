"""
Event Classification stage — deterministic keyword classifier producing a
FinancialEvent from a news item's normalized text.

Runs after Impact and before Sentiment:
    Impact -> [Event Classification] -> Sentiment

Kept as a plain keyword matcher (no ML) so it works with zero external
dependencies. The FinancialEvent output shape is what future sources (SEC
filings, Reddit, X, earnings/economic calendars) should also produce, so
the Event abstraction stays reusable beyond this news pipeline.
"""
from __future__ import annotations

from typing import List, Tuple

from news.models import EventType, FinancialEvent

# Checked in order — first match wins. Ordered roughly by how
# unambiguous/high-severity the phrase is.
_EVENT_KEYWORDS: List[Tuple[EventType, float, List[str]]] = [
    (EventType.BANKRUPTCY, 0.95, [
        "files for bankruptcy", "chapter 11", "chapter 7", "insolvency",
        "bankruptcy filing", "went bankrupt",
    ]),
    (EventType.SEC_INVESTIGATION, 0.9, [
        "sec investigation", "sec probe", "securities and exchange commission investigat",
        "subpoena", "sec charges", "sec lawsuit",
    ]),
    (EventType.HACK, 0.9, [
        "exchange hack", "hacked", "security breach", "data breach",
        "exploit drains", "wallet compromised", "51% attack",
    ]),
    (EventType.MERGER, 0.85, [
        "merger", "to merge with", "merge with", "all-stock merger",
    ]),
    (EventType.ACQUISITION, 0.85, [
        "to acquire", "acquires", "acquisition of", "buyout", "takeover bid",
    ]),
    (EventType.ETF_APPROVAL, 0.85, [
        "etf approval", "etf approved", "spot bitcoin etf", "sec approves etf",
    ]),
    (EventType.TOKEN_UNLOCK, 0.75, [
        "token unlock", "tokens unlocked", "vesting unlock", "unlock schedule",
    ]),
    (EventType.RATE_DECISION, 0.8, [
        "rate hike", "rate cut", "federal reserve", "fed decision",
        "interest rate decision", "fomc",
    ]),
    (EventType.REGULATION, 0.7, [
        "regulation", "regulatory crackdown", "new regulation",
        "banned by regulators", "compliance rule", "antitrust",
    ]),
    (EventType.EARNINGS_BEAT, 0.75, [
        "beat expectations", "earnings beat", "beats estimates",
        "revenue beat", "blowout earnings",
    ]),
    (EventType.EARNINGS_MISS, 0.75, [
        "missed estimates", "earnings miss", "misses expectations", "revenue miss",
    ]),
    (EventType.DIVIDEND, 0.6, [
        "dividend increase", "declares dividend", "dividend cut", "special dividend",
    ]),
    (EventType.PRODUCT_RELEASE, 0.5, [
        "unveils", "launches", "product launch", "new product release",
    ]),
]


class EventClassifier:
    def classify(self, text: str) -> FinancialEvent:
        if not text:
            return FinancialEvent(event_type=EventType.UNCLASSIFIED, confidence=0.0)

        lower = text.lower()
        for event_type, severity, phrases in _EVENT_KEYWORDS:
            matched = [p for p in phrases if p in lower]
            if matched:
                confidence = round(min(1.0, 0.5 + 0.15 * len(matched)), 2)
                return FinancialEvent(
                    event_type=event_type,
                    confidence=confidence,
                    matched_keywords=matched,
                    severity=severity,
                )

        return FinancialEvent(event_type=EventType.UNCLASSIFIED, confidence=0.0, severity=0.3)
