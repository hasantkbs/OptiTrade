"""
Deterministic (no network, no DB) unit tests for
research_lab/validation/trade_builder.py's cost simulation.
"""
from datetime import datetime, timezone

import pytest

from decision_engine.models import EngineVote, Prediction
from learning.models import LearningSample, SampleSource
from paper_trading.config import PaperTradingConfig
from paper_trading.execution import ExecutionEngine
from research_lab.config import ResearchLabConfig
from research_lab.validation.trade_builder import simulate_trade

_SYMBOL = "TESTBUY"


def _sample(decision=Prediction.BUY, actual_return=10.0, confidence=0.7, horizon=5) -> LearningSample:
    vote = EngineVote(
        engine_name="TechnicalEngine", engine_version="v1", prediction=decision,
        confidence=confidence, expected_return=actual_return, volatility=15.0, evidence=["e"],
    )
    return LearningSample(
        symbol=_SYMBOL, source=SampleSource.LIVE, decision=decision, confidence=confidence,
        expected_return=actual_return, expected_volatility=15.0, engine_results=[vote], evidence=["e"],
        decided_at=datetime(2026, 1, 1, tzinfo=timezone.utc), evaluation_horizon_days=horizon,
        evaluated=True, evaluated_at=datetime(2026, 1, 6, tzinfo=timezone.utc),
        actual_return=actual_return, actual_volatility=15.0, correct=True,
    )


def _zero_cost_engine() -> ExecutionEngine:
    return ExecutionEngine(config=PaperTradingConfig(
        slippage_bps=0.0, spread_bps=0.0, commission_rate=0.0, commission_min=0.0, tax_rate=0.0,
    ))


def _config(notional=10_000.0) -> ResearchLabConfig:
    return ResearchLabConfig(validation_position_size_notional=notional)


def test_simulate_trade_returns_none_for_hold_decision():
    assert simulate_trade(_sample(decision=Prediction.HOLD), _config(), _zero_cost_engine()) is None


def test_simulate_trade_returns_none_for_sell_decision():
    """No short-selling mechanism exists anywhere in this codebase -
    a SELL decision must never produce a fabricated short P&L."""
    assert simulate_trade(_sample(decision=Prediction.SELL), _config(), _zero_cost_engine()) is None


def test_simulate_trade_returns_none_when_actual_return_missing():
    sample = _sample()
    sample.actual_return = None
    assert simulate_trade(sample, _config(), _zero_cost_engine()) is None


def test_simulate_trade_with_zero_costs_preserves_gross_return():
    trade = simulate_trade(_sample(actual_return=10.0), _config(), _zero_cost_engine())
    assert trade is not None
    assert trade.net_return_pct == pytest.approx(10.0, abs=1e-9)
    assert trade.commission_pct == pytest.approx(0.0, abs=1e-9)
    assert trade.slippage_spread_pct == pytest.approx(0.0, abs=1e-9)
    assert trade.tax_pct == pytest.approx(0.0, abs=1e-9)
    assert trade.net_pnl == pytest.approx(1000.0, abs=1e-6)  # 10% of $10,000 notional


def test_simulate_trade_commission_reduces_net_return():
    engine = ExecutionEngine(config=PaperTradingConfig(
        slippage_bps=0.0, spread_bps=0.0, commission_rate=0.001, commission_min=0.0, tax_rate=0.0,
    ))
    trade = simulate_trade(_sample(actual_return=10.0), _config(notional=10_000.0), engine)
    # 0.1% commission on entry notional + 0.1% on exit notional (~$10,000 and ~$11,000)
    # -> total commission ~= 10 + 11 = $21, i.e. ~0.21% of the $10,000 base notional.
    assert trade.commission_pct == pytest.approx(0.21, abs=0.01)
    assert trade.net_return_pct < trade.gross_return_pct


def test_simulate_trade_commission_minimum_floor_applies():
    engine = ExecutionEngine(config=PaperTradingConfig(
        slippage_bps=0.0, spread_bps=0.0, commission_rate=0.0, commission_min=50.0, tax_rate=0.0,
    ))
    trade = simulate_trade(_sample(actual_return=1.0), _config(notional=10_000.0), engine)
    # $50 minimum commission per fill x 2 fills = $100 = 1% of $10,000 notional.
    assert trade.commission_pct == pytest.approx(1.0, abs=1e-6)


def test_simulate_trade_slippage_and_spread_reduce_net_return():
    engine = ExecutionEngine(config=PaperTradingConfig(
        slippage_bps=5.0, spread_bps=10.0, commission_rate=0.0, commission_min=0.0, tax_rate=0.0,
    ))
    trade = simulate_trade(_sample(actual_return=10.0), _config(), engine)
    assert trade.slippage_spread_pct > 0.0
    assert trade.net_return_pct < 10.0


def test_simulate_trade_tax_applies_only_to_positive_gains():
    engine = ExecutionEngine(config=PaperTradingConfig(
        slippage_bps=0.0, spread_bps=0.0, commission_rate=0.0, commission_min=0.0, tax_rate=0.2,
    ))
    losing_trade = simulate_trade(_sample(actual_return=-10.0), _config(), engine)
    assert losing_trade.tax_pct == pytest.approx(0.0, abs=1e-9)
    assert losing_trade.net_return_pct == pytest.approx(-10.0, abs=1e-9)


def test_simulate_trade_tax_reduces_net_return_on_a_winning_trade():
    engine = ExecutionEngine(config=PaperTradingConfig(
        slippage_bps=0.0, spread_bps=0.0, commission_rate=0.0, commission_min=0.0, tax_rate=0.2,
    ))
    winning_trade = simulate_trade(_sample(actual_return=10.0), _config(), engine)
    # 20% tax on a 10% gain -> net return = 10% * (1 - 0.2) = 8%.
    assert winning_trade.net_return_pct == pytest.approx(8.0, abs=1e-6)


def test_simulate_trade_preserves_sample_metadata():
    sample = _sample(confidence=0.55, horizon=7)
    trade = simulate_trade(sample, _config(), _zero_cost_engine())
    assert trade.symbol == _SYMBOL
    assert trade.decided_at == sample.decided_at
    assert trade.evaluation_horizon_days == 7
    assert trade.confidence == pytest.approx(0.55)
