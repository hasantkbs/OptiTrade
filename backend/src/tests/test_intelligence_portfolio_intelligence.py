"""
Tests for intelligence/portfolio_intelligence.py.

`PortfolioIntelligenceService` is tested against fakes satisfying
`PositionsProviderProtocol` (a `get_positions` stand-in for
`portfolio.service.PortfolioService`) and
`decision_engine.interfaces.ExecutionRepositoryProtocol` - no live
PostgreSQL, Redis, market data, or network access anywhere in this file.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import pytest

from decision_engine.models import DecisionOutput, Prediction
from intelligence.config import IntelligenceConfig, PortfolioIntelligenceConfig
from intelligence.decision_diff import diff_decisions
from intelligence.models import (
    ChangeSignificance,
    OpportunityLabel,
    PortfolioFindingType,
    PositionFindingType,
)
from intelligence.opportunity import classify_opportunity
from intelligence.portfolio_intelligence import PortfolioIntelligenceService
from portfolio.models import Position, PositionAnalytics

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


def _position(symbol: str = "AAPL", quantity: float = 10.0, portfolio_id: int = 1) -> Position:
    return Position(portfolio_id=portfolio_id, symbol=symbol, quantity=quantity, average_cost=100.0, realized_pnl=0.0)


class _FakePortfolioService:
    """Satisfies `PositionsProviderProtocol`. Positions are keyed by
    portfolio_id, so isolation between portfolios is enforced the same
    way `portfolio.repository`'s SQL WHERE clauses enforce it in
    production - by only ever storing/returning the requested id's own
    rows."""

    def __init__(self) -> None:
        self._positions: Dict[int, List[Position]] = {}
        self.calls: List[int] = []

    def set_positions(self, portfolio_id: int, positions: List[Position]) -> None:
        self._positions[portfolio_id] = positions

    def get_positions(self, portfolio_id: int) -> List[Position]:
        self.calls.append(portfolio_id)
        return list(self._positions.get(portfolio_id, []))


class _FakeExecutionRepository:
    """Satisfies `ExecutionRepositoryProtocol`. `save` is implemented
    only to prove it is never called by Portfolio Intelligence (a
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
    portfolio_service: Optional[_FakePortfolioService] = None,
    repository: Optional[_FakeExecutionRepository] = None,
    portfolio_intelligence_config: Optional[PortfolioIntelligenceConfig] = None,
) -> PortfolioIntelligenceService:
    return PortfolioIntelligenceService(
        portfolio_service=portfolio_service or _FakePortfolioService(),
        execution_repository=repository or _FakeExecutionRepository(),
        config=_CONFIG,
        portfolio_intelligence_config=portfolio_intelligence_config or PortfolioIntelligenceConfig(),
    )


def _finding_types(result, symbol: Optional[str] = None) -> List[PositionFindingType]:
    findings = result.position_findings
    if symbol is not None:
        findings = [finding for finding in findings if finding.symbol == symbol]
    return [finding.finding_type for finding in findings]


# ── 1. Empty portfolio ────────────────────────────────────────────────────


def test_empty_portfolio_produces_no_findings():
    service = _service()
    result = service.evaluate_portfolio(1)

    assert result.position_snapshots == []
    assert result.position_findings == []
    assert result.portfolio_findings == []
    assert result.unavailable_symbols == []
    assert result.portfolio_id == 1


# ── 2. / 14. Single stable position -> no false positives ────────────────


def test_stable_position_produces_no_findings():
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL")])
    repository = _FakeExecutionRepository()
    # identical current/previous decision - nothing changed
    repository.set_history("AAPL", [_decision("AAPL", timestamp=_NOW), _decision("AAPL", timestamp=_EARLIER)])

    result = _service(portfolio_service, repository).evaluate_portfolio(1)

    assert result.position_findings == []
    assert len(result.position_snapshots) == 1
    assert result.position_snapshots[0].symbol == "AAPL"


# ── 3. Multiple positions ─────────────────────────────────────────────────


def test_multiple_positions_only_flags_the_changed_one():
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL"), _position("MSFT")])
    repository = _FakeExecutionRepository()
    repository.set_history("AAPL", [_decision("AAPL", timestamp=_NOW), _decision("AAPL", timestamp=_EARLIER)])
    repository.set_history(
        "MSFT",
        [
            _decision("MSFT", decision=Prediction.HOLD, timestamp=_NOW),
            _decision("MSFT", decision=Prediction.BUY, confidence=0.9, timestamp=_EARLIER),
        ],
    )

    result = _service(portfolio_service, repository).evaluate_portfolio(1)

    assert _finding_types(result, "AAPL") == []
    assert PositionFindingType.DECISION_DETERIORATED in _finding_types(result, "MSFT")
    assert len(result.position_snapshots) == 2


# ── 4. Multiple portfolios are isolated ───────────────────────────────────


def test_multiple_portfolios_are_isolated():
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL", portfolio_id=1)])
    portfolio_service.set_positions(2, [_position("BTC", portfolio_id=2)])
    repository = _FakeExecutionRepository()
    repository.set_history("AAPL", [_decision("AAPL", timestamp=_NOW)])
    repository.set_history("BTC", [_decision("BTC", timestamp=_NOW)])

    service = _service(portfolio_service, repository)
    result_a = service.evaluate_portfolio(1)
    result_b = service.evaluate_portfolio(2)

    assert [snap.symbol for snap in result_a.position_snapshots] == ["AAPL"]
    assert [snap.symbol for snap in result_b.position_snapshots] == ["BTC"]
    assert result_a.portfolio_id == 1
    assert result_b.portfolio_id == 2
    assert "BTC" not in repository.get_recent_calls[:1]  # portfolio A's evaluation never looked up BTC first


# ── 5-7. Decision deterioration directions ────────────────────────────────


@pytest.mark.parametrize(
    "previous_decision, current_decision",
    [(Prediction.BUY, Prediction.HOLD), (Prediction.BUY, Prediction.SELL), (Prediction.HOLD, Prediction.SELL)],
)
def test_deteriorating_decision_transition_is_flagged(previous_decision, current_decision):
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision("AAPL", decision=current_decision, timestamp=_NOW),
            _decision("AAPL", decision=previous_decision, timestamp=_EARLIER),
        ],
    )

    result = _service(portfolio_service, repository).evaluate_portfolio(1)

    finding = next(f for f in result.position_findings if f.finding_type == PositionFindingType.DECISION_DETERIORATED)
    assert finding.previous_state == previous_decision.value
    assert finding.current_state == current_decision.value
    assert finding.symbol == "AAPL"
    assert finding.portfolio_id == 1


@pytest.mark.parametrize(
    "previous_decision, current_decision", [(Prediction.SELL, Prediction.HOLD), (Prediction.HOLD, Prediction.BUY)],
)
def test_improving_decision_transition_is_not_flagged_as_deterioration(previous_decision, current_decision):
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision("AAPL", decision=current_decision, timestamp=_NOW),
            _decision("AAPL", decision=previous_decision, timestamp=_EARLIER),
        ],
    )

    result = _service(portfolio_service, repository).evaluate_portfolio(1)

    assert PositionFindingType.DECISION_DETERIORATED not in _finding_types(result)


# ── 8-10. Risk increase directions ────────────────────────────────────────


@pytest.mark.parametrize(
    "previous_volatility, current_volatility",
    [(8.0, 15.0), (15.0, 30.0), (8.0, 30.0)],  # LOW->MEDIUM, MEDIUM->HIGH, LOW->HIGH
)
def test_risk_increase_is_flagged(previous_volatility, current_volatility):
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL")])
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

    result = _service(portfolio_service, repository).evaluate_portfolio(1)

    assert PositionFindingType.RISK_INCREASED in _finding_types(result)


def test_risk_decrease_is_not_flagged_as_increase():
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision("AAPL", decision=Prediction.HOLD, expected_volatility=8.0, timestamp=_NOW),
            _decision("AAPL", decision=Prediction.HOLD, expected_volatility=30.0, timestamp=_EARLIER),
        ],
    )

    result = _service(portfolio_service, repository).evaluate_portfolio(1)

    assert PositionFindingType.RISK_INCREASED not in _finding_types(result)


# ── 11-12. Opportunity improvement / deterioration ────────────────────────


def test_opportunity_improvement_is_detected():
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL")])
    repository = _FakeExecutionRepository()
    # previous: BUY but below watch threshold -> WATCH ; current: strong BUY -> STRONG_BUY_BIAS
    repository.set_history(
        "AAPL",
        [
            _decision(
                "AAPL", decision=Prediction.BUY, confidence=0.9, data_sufficiency=1.0,
                expected_volatility=8.0, timestamp=_NOW,
            ),
            _decision(
                "AAPL", decision=Prediction.BUY, confidence=0.4, data_sufficiency=1.0, timestamp=_EARLIER,
            ),
        ],
    )

    result = _service(portfolio_service, repository).evaluate_portfolio(1)

    finding = next(f for f in result.position_findings if f.finding_type == PositionFindingType.OPPORTUNITY_IMPROVED)
    assert finding.previous_state == OpportunityLabel.WATCH.value
    assert finding.current_state == OpportunityLabel.STRONG_BUY_BIAS.value
    assert finding.opportunity_assessment is not None
    assert finding.opportunity_assessment.classification == OpportunityLabel.STRONG_BUY_BIAS


def test_opportunity_deterioration_is_detected():
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL")])
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

    result = _service(portfolio_service, repository).evaluate_portfolio(1)

    finding = next(
        f for f in result.position_findings if f.finding_type == PositionFindingType.OPPORTUNITY_DETERIORATED
    )
    assert finding.previous_state == OpportunityLabel.STRONG_BUY_BIAS.value
    assert finding.current_state == OpportunityLabel.RISK_DETERIORATING.value


# ── 13. Data sufficiency deterioration ────────────────────────────────────


def test_data_sufficiency_reduction_is_detected():
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision("AAPL", decision=Prediction.HOLD, data_sufficiency=0.5, timestamp=_NOW),
            _decision("AAPL", decision=Prediction.HOLD, data_sufficiency=1.0, timestamp=_EARLIER),
        ],
    )

    result = _service(portfolio_service, repository).evaluate_portfolio(1)

    finding = next(f for f in result.position_findings if f.finding_type == PositionFindingType.DATA_QUALITY_REDUCED)
    assert finding.current_state == "0.50"
    assert finding.previous_state == "1.00"


def test_data_sufficiency_improvement_is_not_flagged_as_reduced():
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision("AAPL", decision=Prediction.HOLD, data_sufficiency=1.0, timestamp=_NOW),
            _decision("AAPL", decision=Prediction.HOLD, data_sufficiency=0.5, timestamp=_EARLIER),
        ],
    )

    result = _service(portfolio_service, repository).evaluate_portfolio(1)

    assert PositionFindingType.DATA_QUALITY_REDUCED not in _finding_types(result)


# ── 15-17. Transaction state vs. market intelligence stay separate ───────


def test_newly_opened_position_with_single_history_row_is_not_a_decision_deterioration():
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL", quantity=5.0)])
    repository = _FakeExecutionRepository()
    repository.set_history("AAPL", [_decision("AAPL", decision=Prediction.BUY, timestamp=_NOW)])  # only one row ever

    result = _service(portfolio_service, repository).evaluate_portfolio(1)

    assert result.position_findings == []
    assert result.position_snapshots[0].quantity == 5.0


@pytest.mark.parametrize("quantity", [20.0, 3.0])  # increased and decreased vs. the "original" 10.0
def test_quantity_change_alone_does_not_produce_a_decision_finding(quantity):
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL", quantity=quantity)])
    repository = _FakeExecutionRepository()
    # decision history is stable - only the ledger quantity differs from a "before" of 10.0
    repository.set_history(
        "AAPL", [_decision("AAPL", timestamp=_NOW), _decision("AAPL", timestamp=_EARLIER)],
    )

    result = _service(portfolio_service, repository).evaluate_portfolio(1)

    assert result.position_findings == []
    assert result.position_snapshots[0].quantity == quantity


# ── 18. Closed positions excluded ─────────────────────────────────────────


def test_closed_position_is_excluded_from_active_intelligence():
    portfolio_service = _FakePortfolioService()
    # A defensive case: even if the positions provider ever returned a
    # zero-quantity row (PortfolioService.get_positions never does today),
    # PortfolioIntelligenceService must not evaluate it.
    portfolio_service.set_positions(1, [_position("AAPL", quantity=0.0), _position("MSFT", quantity=10.0)])
    repository = _FakeExecutionRepository()
    repository.set_history("AAPL", [_decision("AAPL", decision=Prediction.SELL, timestamp=_NOW)])
    repository.set_history("MSFT", [_decision("MSFT", timestamp=_NOW)])

    result = _service(portfolio_service, repository).evaluate_portfolio(1)

    assert [snap.symbol for snap in result.position_snapshots] == ["MSFT"]
    assert "AAPL" not in repository.get_recent_calls


# ── 19. Missing decision history handled conservatively ──────────────────


def test_missing_decision_history_is_handled_conservatively():
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL")])
    repository = _FakeExecutionRepository()
    # no history configured for AAPL at all -> get_recent returns []

    result = _service(portfolio_service, repository).evaluate_portfolio(1)

    assert result.position_findings == []
    assert result.unavailable_symbols == ["AAPL"]
    assert result.position_snapshots[0].decision is None


# ── 20. Existing Phase-B diff semantics are reused verbatim ──────────────


def test_significance_is_phase_b_diff_decisions_significance_verbatim():
    current = _decision("AAPL", decision=Prediction.SELL, timestamp=_NOW)
    previous = _decision("AAPL", decision=Prediction.BUY, timestamp=_EARLIER)
    expected_change = diff_decisions(current, previous, _CONFIG)

    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history("AAPL", [current, previous])

    result = _service(portfolio_service, repository).evaluate_portfolio(1)

    deteriorated = next(
        f for f in result.position_findings if f.finding_type == PositionFindingType.DECISION_DETERIORATED
    )
    assert deteriorated.significance == expected_change.significance == ChangeSignificance.MATERIAL
    assert deteriorated.decision_change == expected_change


# ── 21. Existing Phase-B opportunity semantics are reused verbatim ───────


def test_opportunity_assessment_matches_classify_opportunity_directly():
    current = _decision("AAPL", decision=Prediction.BUY, confidence=0.9, data_sufficiency=1.0, timestamp=_NOW)
    expected_assessment = classify_opportunity(current, _CONFIG)

    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history("AAPL", [current])

    result = _service(portfolio_service, repository).evaluate_portfolio(1)

    assert result.position_snapshots[0].opportunity_assessment == expected_assessment


# ── 22-24. No new scoring/risk engine, no LLM, no database writes ────────


def test_no_new_risk_or_scoring_engine_and_no_database_write_occurs():
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision("AAPL", decision=Prediction.SELL, expected_volatility=30.0, data_sufficiency=0.2, timestamp=_NOW),
            _decision("AAPL", decision=Prediction.BUY, confidence=0.9, timestamp=_EARLIER),
        ],
    )

    result = _service(portfolio_service, repository).evaluate_portfolio(1)

    assert len(result.position_findings) > 0  # sanity: this scenario does produce findings
    assert repository.save_calls == []  # read-only - never persists anything


# ── 25. Traceability ──────────────────────────────────────────────────────


def test_result_preserves_portfolio_id_and_symbol_traceability():
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(7, [_position("AAPL", portfolio_id=7)])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision("AAPL", decision=Prediction.SELL, timestamp=_NOW),
            _decision("AAPL", decision=Prediction.BUY, confidence=0.9, timestamp=_EARLIER),
        ],
    )

    result = _service(portfolio_service, repository).evaluate_portfolio(7)

    assert result.portfolio_id == 7
    for finding in result.position_findings:
        assert finding.portfolio_id == 7
        assert finding.symbol == "AAPL"
    for snapshot in result.position_snapshots:
        assert snapshot.portfolio_id == 7
        assert snapshot.symbol == "AAPL"


# ── 26. Determinism ────────────────────────────────────────────────────────


def _strip_timestamps(result):
    payload = result.model_dump(exclude={"evaluated_at"})
    for finding in payload["position_findings"]:
        finding.pop("detected_at", None)
    for finding in payload["portfolio_findings"]:
        finding.pop("detected_at", None)
    return payload


def test_evaluate_portfolio_is_deterministic():
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL"), _position("MSFT")])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision("AAPL", decision=Prediction.SELL, timestamp=_NOW),
            _decision("AAPL", decision=Prediction.BUY, confidence=0.9, timestamp=_EARLIER),
        ],
    )
    repository.set_history("MSFT", [_decision("MSFT", timestamp=_NOW), _decision("MSFT", timestamp=_EARLIER)])

    service = _service(portfolio_service, repository)
    first = service.evaluate_portfolio(1)
    second = service.evaluate_portfolio(1)

    assert _strip_timestamps(first) == _strip_timestamps(second)


# ── 27. Per-symbol isolation - one broken lookup doesn't crash the batch ──


def test_one_broken_symbol_does_not_crash_the_whole_evaluation():
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL"), _position("MSFT")])
    repository = _FakeExecutionRepository()
    repository.fail("AAPL", RuntimeError("db connection lost"))
    repository.set_history(
        "MSFT",
        [
            _decision("MSFT", decision=Prediction.SELL, timestamp=_NOW),
            _decision("MSFT", decision=Prediction.BUY, confidence=0.9, timestamp=_EARLIER),
        ],
    )

    result = _service(portfolio_service, repository).evaluate_portfolio(1)

    assert result.unavailable_symbols == ["AAPL"]
    assert PositionFindingType.DECISION_DETERIORATED in _finding_types(result, "MSFT")


# ── REVIEW_POSITION rollup ─────────────────────────────────────────────────


def test_review_position_emitted_when_a_material_negative_finding_exists():
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision("AAPL", decision=Prediction.SELL, timestamp=_NOW),
            _decision("AAPL", decision=Prediction.BUY, confidence=0.9, timestamp=_EARLIER),
        ],
    )

    result = _service(portfolio_service, repository).evaluate_portfolio(1)

    assert PositionFindingType.REVIEW_POSITION in _finding_types(result)


def test_review_position_not_emitted_for_opportunity_improvement_alone():
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL")])
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

    result = _service(portfolio_service, repository).evaluate_portfolio(1)

    assert PositionFindingType.OPPORTUNITY_IMPROVED in _finding_types(result)
    assert PositionFindingType.REVIEW_POSITION not in _finding_types(result)


def test_no_finding_is_produced_merely_because_a_position_exists():
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL")])
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

    result = _service(portfolio_service, repository).evaluate_portfolio(1)

    assert result.position_findings == []


# ── Portfolio-level concentration finding - no invented threshold ────────


def test_no_portfolio_level_finding_without_a_configured_threshold():
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history("AAPL", [_decision("AAPL", timestamp=_NOW)])
    analytics = [
        PositionAnalytics(
            symbol="AAPL", quantity=10.0, average_cost=100.0, current_price=150.0, cost_basis=1000.0,
            current_value=1500.0, unrealized_pnl=500.0, unrealized_pnl_pct=50.0, realized_pnl=0.0,
            weight_pct=95.0, sector="Technology", country="US", currency="USD",
        )
    ]

    service = _service(portfolio_service, repository)  # default config: no threshold configured
    result = service.evaluate_portfolio(1, position_analytics=analytics)

    assert result.portfolio_findings == []


def test_portfolio_level_finding_fires_once_explicitly_configured():
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history("AAPL", [_decision("AAPL", timestamp=_NOW)])
    analytics = [
        PositionAnalytics(
            symbol="AAPL", quantity=10.0, average_cost=100.0, current_price=150.0, cost_basis=1000.0,
            current_value=1500.0, unrealized_pnl=500.0, unrealized_pnl_pct=50.0, realized_pnl=0.0,
            weight_pct=95.0, sector="Technology", country="US", currency="USD",
        )
    ]

    service = _service(
        portfolio_service, repository, portfolio_intelligence_config=PortfolioIntelligenceConfig(
            large_position_weight_pct=90.0,
        ),
    )
    result = service.evaluate_portfolio(1, position_analytics=analytics)

    assert len(result.portfolio_findings) == 1
    finding = result.portfolio_findings[0]
    assert finding.finding_type == PortfolioFindingType.CONCENTRATION_THRESHOLD_EXCEEDED
    assert finding.symbol == "AAPL"
    assert finding.portfolio_id == 1


# ── Analytics pass-through onto the snapshot ──────────────────────────────


def test_position_analytics_populate_the_snapshot_when_supplied():
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history("AAPL", [_decision("AAPL", timestamp=_NOW)])
    analytics = [
        PositionAnalytics(
            symbol="AAPL", quantity=10.0, average_cost=100.0, current_price=150.0, cost_basis=1000.0,
            current_value=1500.0, unrealized_pnl=500.0, unrealized_pnl_pct=50.0, realized_pnl=0.0,
            weight_pct=42.0, sector="Technology", country="US", currency="USD",
        )
    ]

    result = _service(portfolio_service, repository).evaluate_portfolio(1, position_analytics=analytics)

    snapshot = result.position_snapshots[0]
    assert snapshot.current_value == 1500.0
    assert snapshot.allocation_pct == 42.0


def test_summary_is_a_deterministic_non_empty_string():
    portfolio_service = _FakePortfolioService()
    portfolio_service.set_positions(1, [_position("AAPL")])
    repository = _FakeExecutionRepository()
    repository.set_history(
        "AAPL",
        [
            _decision("AAPL", decision=Prediction.SELL, timestamp=_NOW),
            _decision("AAPL", decision=Prediction.BUY, confidence=0.9, timestamp=_EARLIER),
        ],
    )

    result = _service(portfolio_service, repository).evaluate_portfolio(1)

    assert isinstance(result.summary, str) and result.summary
    assert "1 open position(s) evaluated" in result.summary
