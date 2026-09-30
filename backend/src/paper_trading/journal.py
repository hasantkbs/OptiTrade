"""
OptiTrade Paper Trading & Trade Journal Platform — trade journal.

Captures the full decision context behind an order at the moment it is
placed: the decision, engine votes, and explanation come from a single
`pipeline.PipelineService.run(symbol)` call (which already, on its own,
records the decision into Continuous Learning - see `pipeline/pipeline.py`),
the feature snapshot from `feature_store.FeatureStoreService`, and the
market regime from a small, self-contained heuristic (no dedicated
"market regime" system exists elsewhere in this codebase).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from feature_store.service import FeatureStoreService
from paper_trading.exceptions import JournalEntryNotFoundError
from paper_trading.models import (
    EngineVoteSnapshot,
    MarketRegime,
    Order,
    ScreenshotMetadata,
    TradeJournalEntry,
)
from paper_trading.repository import PaperTradingRepository
from pipeline.models import EngineExecutionStatus
from pipeline.service import PipelineService

logger = logging.getLogger(__name__)
_MODULE = "paper_trading.journal"
_COMPONENT = "paper_trading"

_DEFAULT_FEATURE_NAMES = [
    "rsi", "macd_diff", "trend_strength", "bollinger_pb", "volume_ratio", "ema_signal_enc", "price_velocity",
]


def classify_market_regime(features: Dict[str, float]) -> MarketRegime:
    trend_strength = features.get("trend_strength")
    rsi = features.get("rsi")
    volume_ratio = features.get("volume_ratio")

    if volume_ratio is not None and volume_ratio > 2.0:
        return MarketRegime.HIGH_VOLATILITY
    if trend_strength is None and rsi is None:
        return MarketRegime.UNKNOWN
    if trend_strength is not None and trend_strength > 0.5:
        return MarketRegime.TRENDING_BEARISH if rsi is not None and rsi < 50 else MarketRegime.TRENDING_BULLISH
    if trend_strength is not None and trend_strength < -0.5:
        return MarketRegime.TRENDING_BEARISH
    return MarketRegime.RANGING


class JournalService:
    def __init__(
        self,
        repository: PaperTradingRepository,
        pipeline_service: PipelineService,
        feature_store_service: Optional[FeatureStoreService] = None,
        feature_names: Optional[List[str]] = None,
    ) -> None:
        self._repository = repository
        self._pipeline_service = pipeline_service
        self._feature_store_service = feature_store_service
        self._feature_names = feature_names or list(_DEFAULT_FEATURE_NAMES)

    def record_trade_decision(self, order: Order) -> Optional[TradeJournalEntry]:
        """Journaling must never block order placement - any failure
        fetching the decision/feature context is logged and swallowed,
        returning None rather than raising."""
        started_at = time.perf_counter()
        try:
            response = self._pipeline_service.run(order.symbol)
        except Exception as exc:
            log_event(
                logger, component=_COMPONENT, module=_MODULE, operation="record_trade_decision", status=STATUS_ERROR,
                error_type=type(exc).__name__, order_id=order.id, symbol=order.symbol, level=logging.WARNING,
            )
            return None

        engine_votes = [
            EngineVoteSnapshot(
                engine_name=item.engine_name, engine_version=item.engine_version, prediction=item.prediction,
                confidence=item.confidence, expected_return=item.expected_return, volatility=item.volatility,
                evidence=item.evidence,
            )
            for item in response.engine_breakdown
            if item.status == EngineExecutionStatus.SUCCESS and item.prediction is not None
        ]

        feature_snapshot: Dict[str, float] = {}
        if self._feature_store_service is not None:
            try:
                feature_snapshot = self._feature_store_service.get_latest_features(order.symbol, self._feature_names)
            except Exception as exc:
                log_event(
                    logger, component=_COMPONENT, module=_MODULE, operation="fetch_feature_snapshot",
                    status=STATUS_ERROR, error_type=type(exc).__name__, symbol=order.symbol, level=logging.WARNING,
                )

        entry = TradeJournalEntry(
            order_id=order.id, account_id=order.account_id, symbol=order.symbol, decision=response.decision,
            confidence=response.confidence, expected_return=response.expected_return,
            expected_volatility=response.expected_volatility, risk_level=response.risk.risk_level,
            data_sufficiency=response.risk.data_sufficiency, evidence=response.evidence, engine_votes=engine_votes,
            explanation_text=response.explanation, market_regime=classify_market_regime(feature_snapshot),
            feature_snapshot=feature_snapshot,
        )
        entry_id = self._repository.save_journal_entry(entry)
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="record_trade_decision", status=STATUS_SUCCESS,
            execution_time_ms=(time.perf_counter() - started_at) * 1000, order_id=order.id, entry_id=entry_id,
        )
        return self._repository.get_journal_entry(entry_id)

    def get_entry(self, entry_id: int) -> TradeJournalEntry:
        entry = self._repository.get_journal_entry(entry_id)
        if entry is None:
            raise JournalEntryNotFoundError(f"journal entry {entry_id} not found")
        return entry

    def get_entry_by_order(self, order_id: int) -> Optional[TradeJournalEntry]:
        return self._repository.get_journal_entry_by_order(order_id)

    def list_entries(self, account_id: int) -> List[TradeJournalEntry]:
        return self._repository.list_journal_entries(account_id)

    def update_notes(self, entry_id: int, notes: str) -> TradeJournalEntry:
        entry = self.get_entry(entry_id)
        entry.notes = notes
        entry.updated_at = datetime.now(timezone.utc)
        self._repository.update_journal_entry(entry)
        return self.get_entry(entry_id)

    def set_tags(self, entry_id: int, tags: List[str]) -> TradeJournalEntry:
        entry = self.get_entry(entry_id)
        entry.tags = sorted(set(tags))
        entry.updated_at = datetime.now(timezone.utc)
        self._repository.update_journal_entry(entry)
        return self.get_entry(entry_id)

    def add_tags(self, entry_id: int, tags: List[str]) -> TradeJournalEntry:
        entry = self.get_entry(entry_id)
        return self.set_tags(entry_id, list(entry.tags) + list(tags))

    def add_screenshot(self, entry_id: int, url: str, caption: str = "") -> ScreenshotMetadata:
        self.get_entry(entry_id)  # raises JournalEntryNotFoundError if missing
        screenshot_id = self._repository.save_screenshot(
            ScreenshotMetadata(journal_entry_id=entry_id, url=url, caption=caption)
        )
        return next(shot for shot in self._repository.list_screenshots(entry_id) if shot.id == screenshot_id)
