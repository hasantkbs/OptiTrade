"""
Tests for intelligence/watchlist_intelligence.py.

`WatchlistIntelligenceService` is tested against fakes satisfying
`WatchlistItemsProviderProtocol` (a `list_items` stand-in for
`watchlist.watchlist_service.WatchlistService`) and
`decision_engine.interfaces.ExecutionRepositoryProtocol` - no live
PostgreSQL, Redis, market data, or network access anywhere in this file.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import pytest

from decision_engine.models import DecisionOutput, Prediction
from intelligence.config import IntelligenceConfig
from intelligence.decision_diff import diff_decisions
from intelligence.models import ChangeSignificance, OpportunityLabel, WatchlistFindingType
from intelligence.opportunity import classify_opportunity
from intelligence.watchlist_intelligence import WatchlistIntelligenceService
from watchlist.models import WatchlistItem

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
_EARLIER = _NOW - timedelta(days=1)
_CONFIG = IntelligenceConfig()


def _decision(symbol: str = "AAPL", **overrides) -> DecisionOutput:
    defaults = dict(
        symbol=symbol,
        decision=Prediction.BUY,
        confidence=0.8,
        expected_return=5.0,
        expected_volatility=8.0,  # LOW risk bucket
        aggregation_strategy_version="test_v1",
        data_sufficiency=1.0,
        evidence=["evidence"],
        engine_results=[],
        timestamp=_NOW,
    )
    defaults.update(overrides)
    return DecisionOutput(**defaults)


def _item(symbol: str = "AAPL", watchlist_id: int = 1) -> WatchlistItem:
    return WatchlistItem(watchlist_id=watchlist_id, symbol=symbol)


class _FakeWatchlistService:
    """Satisfies `WatchlistItemsProviderProtocol`. Items are keyed by
    watchlist_id, enforcing isolation the same way `watchlist.repository`'s
    `WHERE watchlist_id = %s` enforces it in production - by only ever
    storing/returning the requested id's own rows."""

    def __init__(self) -> None:
        self._items: Dict[int, List[WatchlistItem]] = {}
        self.calls: List[int] = []

    def set_items(self, watchlist_id: int, items: List[WatchlistItem]) -> None:
        self._items[watchlist_id] = items

    def list_items(self, watchlist_id: int) -> List[WatchlistItem]:
        self.calls.append(watchlist_id)
        return list(self._items.get(watchlist_id, []))


class _FakeExecutionRepository:
    """Satisfies `ExecutionRepositoryProtocol`. `save` is implemented
    only to prove it is never called by Watchlist Intelligence (a
    read-only consumer of decision history)."""

    def __init__(self) -> None:
        self._history: Dict[str, List[DecisionOutput]] = {}
        self._exceptions: Dict[str, Exception] = {}
        self.get_recent_calls: List[str] = []
        self.save_calls: List[DecisionOutput] = []

    def set_history(self, symbol: str, history: List[DecisionOutput]) -> None:
        self._history[symbol] = history

    def fail(self, symbol: str, exc: Exception) -> None:
        self._exceptions[symbol] = exc

    def save(self, output: DecisionOutput) -> None:
        self.save_calls.append(output)

    def get_recent(self, symbol: str, limit: int = 10) -> List[DecisionOutput]:
        self.get_recent_calls.append(symbol)
        if symbol in self._exceptions:
            raise self._exceptions[symbol]
        return list(self._history.get(symbol, []))[:limit]


def _service(
    watchlist_service: Optional[_FakeWatchlistService] = None,
    repository: Optional[_FakeExecutionRepository] = None,
) -> WatchlistIntelligenceService:
    return WatchlistIntelligenceService(
        watchlist_service=watchlist_service or _FakeWatchlistService(),
        execution_repository=repository or _FakeExecutionRepository(),
        config=_CONFIG,
    )


def _finding_types(result, symbol: Optional[str] = None) -> List[WatchlistFindingType]:
    findings = result.findings
    if symbol is not None:
        findings = [f for f in findings if f.symbol == symbol]
    return [f.finding_type for f in findings]


# ── 1. Service exists ─────────────────────────────────────────────────────


def test_service_can_be_constructed_with_fakes():
    service = _service()
    assert isinstance(service, WatchlistIntelligenceService)


# ── 2. Empty watchlist ────────────────────────────────────────────────────


def test_empty_watchlist_produces_a_valid_empty_result():
    watchlist_service = _FakeWatchlistService()
    repository = _FakeExecutionRepository()

    result = _service(watchlist_service, repository).evaluate_watchlist(1)

    assert result.watchlist_id == 1
    assert result.evaluated_symbols == []
    assert result.symbol_snapshots == []
    assert result.findings == []
    assert result.unavailable_symbols == []
    assert isinstance(result.summary, str) and result.summary


# ── 22. Empty watchlist does not query decision history ───────────────────


def test_empty_watchlist_does_not_query_decision_history():
    watchlist_service = _FakeWatchlistService()
    repository = _FakeExecutionRepository()

    _service(watchlist_service, repository).evaluate_watchlist(1)

    assert repository.get_recent_calls == []


# ── 3. One symbol, unchanged decision ─────────────────────────────────────


def test_one_symbol_with_unchanged_decision_produces_no_findings():
    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(1, [_item("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history("AAPL", [_decision("AAPL", timestamp=_NOW), _decision("AAPL", timestamp=_EARLIER)])

    result = _service(watchlist_service, repository).evaluate_watchlist(1)

    assert result.findings == []
    assert result.evaluated_symbols == ["AAPL"]
    assert len(result.symbol_snapshots) == 1
    assert result.symbol_snapshots[0].current_decision == Prediction.BUY


# ── 4-7. Decision deterioration directions ────────────────────────────────


@pytest.mark.parametrize(
    "previous_decision, current_decision",
    [(Prediction.BUY, Prediction.HOLD), (Prediction.BUY, Prediction.SELL), (Prediction.HOLD, Prediction.SELL)],
)
def test_deteriorating_decision_transition_is_flagged(previous_decision, current_decision):
    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(1, [_item("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision("AAPL", decision=current_decision, timestamp=_NOW),
            _decision("AAPL", decision=previous_decision, timestamp=_EARLIER),
        ],
    )

    result = _service(watchlist_service, repository).evaluate_watchlist(1)

    finding = next(f for f in result.findings if f.finding_type == WatchlistFindingType.DECISION_DETERIORATED)
    assert finding.previous_state == previous_decision.value
    assert finding.current_state == current_decision.value
    assert finding.symbol == "AAPL"
    assert finding.watchlist_id == 1


def test_sell_to_hold_is_not_a_decision_deterioration():
    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(1, [_item("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision("AAPL", decision=Prediction.HOLD, timestamp=_NOW),
            _decision("AAPL", decision=Prediction.SELL, timestamp=_EARLIER),
        ],
    )

    result = _service(watchlist_service, repository).evaluate_watchlist(1)

    assert WatchlistFindingType.DECISION_DETERIORATED not in _finding_types(result)


# ── 8-11. Risk direction ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "previous_volatility, current_volatility",
    [(8.0, 15.0), (15.0, 30.0), (8.0, 30.0)],  # LOW->MEDIUM, MEDIUM->HIGH, LOW->HIGH
)
def test_risk_increase_is_flagged(previous_volatility, current_volatility):
    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(1, [_item("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision("AAPL", decision=Prediction.HOLD, expected_volatility=current_volatility, timestamp=_NOW),
            _decision(
                "AAPL", decision=Prediction.HOLD, expected_volatility=previous_volatility, timestamp=_EARLIER,
            ),
        ],
    )

    result = _service(watchlist_service, repository).evaluate_watchlist(1)

    assert WatchlistFindingType.RISK_INCREASED in _finding_types(result)


def test_medium_to_low_risk_is_not_flagged_as_increase():
    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(1, [_item("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision("AAPL", decision=Prediction.HOLD, expected_volatility=8.0, timestamp=_NOW),
            _decision("AAPL", decision=Prediction.HOLD, expected_volatility=15.0, timestamp=_EARLIER),
        ],
    )

    result = _service(watchlist_service, repository).evaluate_watchlist(1)

    assert WatchlistFindingType.RISK_INCREASED not in _finding_types(result)


# ── 12-13. Opportunity improvement / deterioration ────────────────────────


def test_opportunity_improvement_is_detected():
    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(1, [_item("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision(
                "AAPL", decision=Prediction.BUY, confidence=0.9, data_sufficiency=1.0,
                expected_volatility=8.0, timestamp=_NOW,
            ),
            _decision("AAPL", decision=Prediction.BUY, confidence=0.4, data_sufficiency=1.0, timestamp=_EARLIER),
        ],
    )

    result = _service(watchlist_service, repository).evaluate_watchlist(1)

    finding = next(f for f in result.findings if f.finding_type == WatchlistFindingType.OPPORTUNITY_IMPROVED)
    assert finding.previous_state == OpportunityLabel.WATCH.value
    assert finding.current_state == OpportunityLabel.STRONG_BUY_BIAS.value
    assert finding.opportunity_assessment is not None
    assert finding.opportunity_assessment.classification == OpportunityLabel.STRONG_BUY_BIAS


def test_opportunity_deterioration_is_detected():
    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(1, [_item("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision("AAPL", decision=Prediction.SELL, expected_volatility=8.0, timestamp=_NOW),
            _decision(
                "AAPL", decision=Prediction.BUY, confidence=0.9, data_sufficiency=1.0,
                expected_volatility=8.0, timestamp=_EARLIER,
            ),
        ],
    )

    result = _service(watchlist_service, repository).evaluate_watchlist(1)

    finding = next(f for f in result.findings if f.finding_type == WatchlistFindingType.OPPORTUNITY_DETERIORATED)
    assert finding.previous_state == OpportunityLabel.STRONG_BUY_BIAS.value
    assert finding.current_state == OpportunityLabel.RISK_DETERIORATING.value


# ── 14. Data sufficiency reduction ────────────────────────────────────────


def test_data_sufficiency_reduction_is_detected():
    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(1, [_item("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision("AAPL", decision=Prediction.HOLD, data_sufficiency=0.5, timestamp=_NOW),
            _decision("AAPL", decision=Prediction.HOLD, data_sufficiency=1.0, timestamp=_EARLIER),
        ],
    )

    result = _service(watchlist_service, repository).evaluate_watchlist(1)

    finding = next(f for f in result.findings if f.finding_type == WatchlistFindingType.DATA_QUALITY_REDUCED)
    assert finding.current_state == "0.50"
    assert finding.previous_state == "1.00"


def test_data_sufficiency_improvement_is_not_flagged_as_reduced():
    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(1, [_item("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision("AAPL", decision=Prediction.HOLD, data_sufficiency=1.0, timestamp=_NOW),
            _decision("AAPL", decision=Prediction.HOLD, data_sufficiency=0.5, timestamp=_EARLIER),
        ],
    )

    result = _service(watchlist_service, repository).evaluate_watchlist(1)

    assert WatchlistFindingType.DATA_QUALITY_REDUCED not in _finding_types(result)


# ── 15. REVIEW_SYMBOL rollup ───────────────────────────────────────────────


def test_review_symbol_emitted_when_a_material_negative_finding_exists():
    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(1, [_item("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision("AAPL", decision=Prediction.SELL, timestamp=_NOW),
            _decision("AAPL", decision=Prediction.BUY, confidence=0.9, timestamp=_EARLIER),
        ],
    )

    result = _service(watchlist_service, repository).evaluate_watchlist(1)

    assert WatchlistFindingType.REVIEW_SYMBOL in _finding_types(result)


def test_review_symbol_not_emitted_for_opportunity_improvement_alone():
    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(1, [_item("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision(
                "AAPL", decision=Prediction.BUY, confidence=0.9, data_sufficiency=1.0,
                expected_volatility=8.0, timestamp=_NOW,
            ),
            _decision("AAPL", decision=Prediction.BUY, confidence=0.4, data_sufficiency=1.0, timestamp=_EARLIER),
        ],
    )

    result = _service(watchlist_service, repository).evaluate_watchlist(1)

    assert WatchlistFindingType.OPPORTUNITY_IMPROVED in _finding_types(result)
    assert WatchlistFindingType.REVIEW_SYMBOL not in _finding_types(result)


def test_no_finding_is_produced_merely_because_a_symbol_is_watched():
    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(1, [_item("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision(
                "AAPL", decision=Prediction.BUY, confidence=0.9, data_sufficiency=1.0,
                expected_volatility=8.0, timestamp=_NOW,
            ),
        ],
    )

    result = _service(watchlist_service, repository).evaluate_watchlist(1)

    assert result.findings == []


# ── 16-17. No history / single history item handled conservatively ───────


def test_symbol_with_no_history_is_handled_conservatively():
    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(1, [_item("AAPL")])
    repository = _FakeExecutionRepository()
    # no history configured for AAPL -> get_recent returns []

    result = _service(watchlist_service, repository).evaluate_watchlist(1)

    assert result.findings == []
    assert result.unavailable_symbols == ["AAPL"]
    assert result.symbol_snapshots[0].current_decision is None


def test_symbol_with_only_one_history_item_is_not_unavailable_and_produces_no_finding():
    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(1, [_item("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history("AAPL", [_decision("AAPL", decision=Prediction.BUY, timestamp=_NOW)])

    result = _service(watchlist_service, repository).evaluate_watchlist(1)

    assert result.findings == []
    assert result.unavailable_symbols == []
    snapshot = result.symbol_snapshots[0]
    assert snapshot.current_decision == Prediction.BUY
    assert snapshot.previous_decision is None
    assert snapshot.decision_change is not None
    assert snapshot.decision_change.significance == ChangeSignificance.NONE


# ── 18-19. Per-symbol isolation ────────────────────────────────────────────


def test_one_broken_symbol_does_not_crash_the_whole_evaluation():
    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(1, [_item("AAPL"), _item("MSFT")])
    repository = _FakeExecutionRepository()
    repository.fail("AAPL", RuntimeError("db connection lost"))
    repository.set_history(
        "MSFT",
        [
            _decision("MSFT", decision=Prediction.SELL, timestamp=_NOW),
            _decision("MSFT", decision=Prediction.BUY, confidence=0.9, timestamp=_EARLIER),
        ],
    )

    result = _service(watchlist_service, repository).evaluate_watchlist(1)

    assert result.unavailable_symbols == ["AAPL"]
    assert WatchlistFindingType.DECISION_DETERIORATED in _finding_types(result, "MSFT")


def test_unavailable_symbol_never_produces_a_finding_or_raw_exception_text():
    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(1, [_item("AAPL")])
    repository = _FakeExecutionRepository()
    repository.fail("AAPL", RuntimeError("super secret internal db connection string"))

    result = _service(watchlist_service, repository).evaluate_watchlist(1)

    assert result.unavailable_symbols == ["AAPL"]
    assert result.findings == []
    assert "secret" not in result.summary
    assert "connection string" not in result.summary


# ── 20-21. Multiple watchlists / multiple users are isolated ─────────────


def test_multiple_watchlists_are_isolated():
    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(1, [_item("AAPL", watchlist_id=1)])
    watchlist_service.set_items(2, [_item("BTC", watchlist_id=2)])
    repository = _FakeExecutionRepository()
    repository.set_history("AAPL", [_decision("AAPL", timestamp=_NOW)])
    repository.set_history("BTC", [_decision("BTC", timestamp=_NOW)])

    service = _service(watchlist_service, repository)
    result_a = service.evaluate_watchlist(1)
    result_b = service.evaluate_watchlist(2)

    assert result_a.evaluated_symbols == ["AAPL"]
    assert result_b.evaluated_symbols == ["BTC"]
    assert result_a.watchlist_id == 1
    assert result_b.watchlist_id == 2


def test_different_users_watchlists_are_isolated():
    # Watchlist ownership is enforced by watchlist.repository's own
    # WHERE owner = %s / WHERE watchlist_id = %s boundaries - this test
    # documents that evaluating one user's watchlist_id never touches
    # another user's watchlist's symbols, using two owners' watchlists
    # sharing no watchlist_id.
    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(10, [_item("AAPL", watchlist_id=10)])  # owner: alice
    watchlist_service.set_items(20, [_item("TSLA", watchlist_id=20)])  # owner: bob
    repository = _FakeExecutionRepository()
    repository.set_history("AAPL", [_decision("AAPL", timestamp=_NOW)])
    repository.set_history("TSLA", [_decision("TSLA", timestamp=_NOW)])

    service = _service(watchlist_service, repository)
    alice_result = service.evaluate_watchlist(10)
    bob_result = service.evaluate_watchlist(20)

    assert alice_result.evaluated_symbols == ["AAPL"]
    assert bob_result.evaluated_symbols == ["TSLA"]
    assert "TSLA" not in alice_result.evaluated_symbols
    assert "AAPL" not in bob_result.evaluated_symbols


# ── 23. Duplicate symbols handled deterministically ───────────────────────


def test_duplicate_symbols_are_deduplicated_deterministically():
    watchlist_service = _FakeWatchlistService()
    # The real repository enforces UNIQUE (watchlist_id, symbol) - this
    # proves the service is defensively correct even if a caller-supplied
    # list ever contained a duplicate (e.g. a fake/test double).
    watchlist_service.set_items(1, [_item("AAPL"), _item("AAPL"), _item("MSFT")])
    repository = _FakeExecutionRepository()
    repository.set_history("AAPL", [_decision("AAPL", timestamp=_NOW)])
    repository.set_history("MSFT", [_decision("MSFT", timestamp=_NOW)])

    result = _service(watchlist_service, repository).evaluate_watchlist(1)

    assert result.evaluated_symbols == ["AAPL", "MSFT"]
    assert repository.get_recent_calls.count("AAPL") == 1
    assert len(result.symbol_snapshots) == 2


# ── 24. Deterministic output ordering ─────────────────────────────────────


def _strip_timestamps(result):
    payload = result.model_dump(exclude={"evaluated_at"})
    for finding in payload["findings"]:
        finding.pop("detected_at", None)
    return payload


def test_evaluate_watchlist_is_deterministic():
    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(1, [_item("AAPL"), _item("MSFT"), _item("GOOG")])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision("AAPL", decision=Prediction.SELL, timestamp=_NOW),
            _decision("AAPL", decision=Prediction.BUY, confidence=0.9, timestamp=_EARLIER),
        ],
    )
    repository.set_history("MSFT", [_decision("MSFT", timestamp=_NOW), _decision("MSFT", timestamp=_EARLIER)])
    repository.set_history("GOOG", [_decision("GOOG", timestamp=_NOW)])

    service = _service(watchlist_service, repository)
    first = service.evaluate_watchlist(1)
    second = service.evaluate_watchlist(1)

    assert _strip_timestamps(first) == _strip_timestamps(second)
    assert first.evaluated_symbols == ["AAPL", "MSFT", "GOOG"]  # matches watchlist add order


# ── 25. No database writes ─────────────────────────────────────────────────


def test_no_database_write_occurs():
    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(1, [_item("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision("AAPL", decision=Prediction.SELL, expected_volatility=30.0, data_sufficiency=0.2, timestamp=_NOW),
            _decision("AAPL", decision=Prediction.BUY, confidence=0.9, timestamp=_EARLIER),
        ],
    )

    result = _service(watchlist_service, repository).evaluate_watchlist(1)

    assert len(result.findings) > 0  # sanity: this scenario does produce findings
    assert repository.save_calls == []  # read-only - never persists anything


# ── 26. No alert creation ──────────────────────────────────────────────────


def test_evaluate_watchlist_never_creates_an_alert_object():
    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(1, [_item("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision("AAPL", decision=Prediction.SELL, timestamp=_NOW),
            _decision("AAPL", decision=Prediction.BUY, confidence=0.9, timestamp=_EARLIER),
        ],
    )

    result = _service(watchlist_service, repository).evaluate_watchlist(1)

    # The result carries only intelligence findings - never a
    # watchlist.models.Alert/AlertTriggerEvent, and no alert-creating
    # dependency (WatchlistService.create_alert) is even referenced.
    for finding in result.findings:
        assert not hasattr(finding, "alert_type")
        assert not hasattr(finding, "alert_id")


# ── 30. Canonical Phase B/D intelligence is actually reused ──────────────


def test_significance_is_phase_b_diff_decisions_significance_verbatim():
    current = _decision("AAPL", decision=Prediction.SELL, timestamp=_NOW)
    previous = _decision("AAPL", decision=Prediction.BUY, timestamp=_EARLIER)
    expected_change = diff_decisions(current, previous, _CONFIG)

    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(1, [_item("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history("AAPL", [current, previous])

    result = _service(watchlist_service, repository).evaluate_watchlist(1)

    deteriorated = next(f for f in result.findings if f.finding_type == WatchlistFindingType.DECISION_DETERIORATED)
    assert deteriorated.significance == expected_change.significance == ChangeSignificance.MATERIAL
    assert deteriorated.decision_change == expected_change


def test_opportunity_assessment_matches_classify_opportunity_directly():
    current = _decision("AAPL", decision=Prediction.BUY, confidence=0.9, data_sufficiency=1.0, timestamp=_NOW)
    expected_assessment = classify_opportunity(current, _CONFIG)

    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(1, [_item("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history("AAPL", [current])

    result = _service(watchlist_service, repository).evaluate_watchlist(1)

    assert result.symbol_snapshots[0].opportunity == expected_assessment


# ── Traceability / multi-symbol partitioning ──────────────────────────────


def test_result_preserves_watchlist_id_and_symbol_traceability():
    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(7, [_item("AAPL", watchlist_id=7)])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision("AAPL", decision=Prediction.SELL, timestamp=_NOW),
            _decision("AAPL", decision=Prediction.BUY, confidence=0.9, timestamp=_EARLIER),
        ],
    )

    result = _service(watchlist_service, repository).evaluate_watchlist(7)

    assert result.watchlist_id == 7
    for finding in result.findings:
        assert finding.watchlist_id == 7
        assert finding.symbol == "AAPL"
    for snapshot in result.symbol_snapshots:
        assert snapshot.watchlist_id == 7
        assert snapshot.symbol == "AAPL"


def test_multiple_symbols_only_flags_the_changed_one():
    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(1, [_item("AAPL"), _item("MSFT")])
    repository = _FakeExecutionRepository()
    repository.set_history("AAPL", [_decision("AAPL", timestamp=_NOW), _decision("AAPL", timestamp=_EARLIER)])
    repository.set_history(
        "MSFT",
        [
            _decision("MSFT", decision=Prediction.HOLD, timestamp=_NOW),
            _decision("MSFT", decision=Prediction.BUY, confidence=0.9, timestamp=_EARLIER),
        ],
    )

    result = _service(watchlist_service, repository).evaluate_watchlist(1)

    assert _finding_types(result, "AAPL") == []
    assert WatchlistFindingType.DECISION_DETERIORATED in _finding_types(result, "MSFT")
    assert len(result.symbol_snapshots) == 2


def test_summary_is_a_deterministic_non_empty_string():
    watchlist_service = _FakeWatchlistService()
    watchlist_service.set_items(1, [_item("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision("AAPL", decision=Prediction.SELL, timestamp=_NOW),
            _decision("AAPL", decision=Prediction.BUY, confidence=0.9, timestamp=_EARLIER),
        ],
    )

    result = _service(watchlist_service, repository).evaluate_watchlist(1)

    assert "1 symbol(s) evaluated" in result.summary
    assert "guarantee" not in result.summary.lower()
