"""Tests for paper_trading/execution.py. Pure simulation math - no infra."""
from datetime import datetime, timezone

import pytest

from paper_trading.config import PaperTradingConfig
from paper_trading.exceptions import MarketClosedError
from paper_trading.execution import ExecutionEngine
from paper_trading.models import OrderSide, OrderType


@pytest.fixture
def engine():
    config = PaperTradingConfig(slippage_bps=10.0, spread_bps=20.0, commission_rate=0.001, commission_min=1.0, tax_rate=0.1)
    return ExecutionEngine(config=config)


def test_crypto_symbol_is_always_open(engine):
    assert engine.is_market_open("BTC-USD") is True
    night = datetime(2026, 1, 1, 3, 0, tzinfo=timezone.utc)
    assert engine.is_market_open("BTC-USD", now=night) is True


def test_stock_symbol_respects_market_hours(engine):
    weekday_open = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)  # Wed ~15:00 Istanbul
    assert engine.is_market_open("AAPL", now=weekday_open) is True

    weekday_closed = datetime(2026, 7, 29, 22, 0, tzinfo=timezone.utc)  # ~01:00 Istanbul next day
    assert engine.is_market_open("AAPL", now=weekday_closed) is False


def test_stock_symbol_closed_on_weekend(engine):
    saturday = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)  # Saturday
    assert engine.is_market_open("AAPL", now=saturday) is False


def test_validate_market_hours_allows_market_order_when_open(engine):
    weekday_open = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    engine.validate_market_hours("AAPL", OrderType.MARKET, now=weekday_open)  # must not raise


def test_validate_market_hours_rejects_market_order_when_closed(engine):
    weekday_closed = datetime(2026, 7, 29, 22, 0, tzinfo=timezone.utc)
    with pytest.raises(MarketClosedError):
        engine.validate_market_hours("AAPL", OrderType.MARKET, now=weekday_closed)


def test_validate_market_hours_allows_resting_orders_when_closed(engine):
    weekday_closed = datetime(2026, 7, 29, 22, 0, tzinfo=timezone.utc)
    engine.validate_market_hours("AAPL", OrderType.LIMIT, now=weekday_closed)  # must not raise
    engine.validate_market_hours("AAPL", OrderType.STOP, now=weekday_closed)
    engine.validate_market_hours("AAPL", OrderType.TAKE_PROFIT, now=weekday_closed)


def test_buy_execution_price_is_above_reference(engine):
    price = engine.simulate_execution_price(OrderSide.BUY, 100.0)
    assert price > 100.0
    expected = 100.0 * (1 + (10.0 + 20.0 / 2) / 10_000.0)
    assert price == pytest.approx(expected)


def test_sell_execution_price_is_below_reference(engine):
    price = engine.simulate_execution_price(OrderSide.SELL, 100.0)
    assert price < 100.0
    expected = 100.0 * (1 - (10.0 + 20.0 / 2) / 10_000.0)
    assert price == pytest.approx(expected)


def test_compute_commission_uses_minimum_when_notional_is_small(engine):
    assert engine.compute_commission(10.0) == 1.0  # commission_min


def test_compute_commission_uses_rate_when_notional_is_large(engine):
    assert engine.compute_commission(100_000.0) == pytest.approx(100.0)


def test_compute_tax_only_applies_to_gains(engine):
    assert engine.compute_tax(1000.0) == pytest.approx(100.0)
    assert engine.compute_tax(-1000.0) == 0.0


def test_simulate_latency_within_configured_bounds(engine):
    for _ in range(20):
        latency = engine.simulate_latency_ms()
        assert engine.config.latency_ms_min <= latency <= engine.config.latency_ms_max


def test_is_triggered_limit_buy():
    engine = ExecutionEngine()
    assert engine.is_triggered(OrderType.LIMIT, OrderSide.BUY, current_price=99.0, limit_price=100.0, stop_price=None) is True
    assert engine.is_triggered(OrderType.LIMIT, OrderSide.BUY, current_price=101.0, limit_price=100.0, stop_price=None) is False


def test_is_triggered_limit_sell():
    engine = ExecutionEngine()
    assert engine.is_triggered(OrderType.LIMIT, OrderSide.SELL, current_price=101.0, limit_price=100.0, stop_price=None) is True
    assert engine.is_triggered(OrderType.LIMIT, OrderSide.SELL, current_price=99.0, limit_price=100.0, stop_price=None) is False


def test_is_triggered_stop_buy():
    engine = ExecutionEngine()
    assert engine.is_triggered(OrderType.STOP, OrderSide.BUY, current_price=101.0, limit_price=None, stop_price=100.0) is True
    assert engine.is_triggered(OrderType.STOP, OrderSide.BUY, current_price=99.0, limit_price=None, stop_price=100.0) is False


def test_is_triggered_stop_sell():
    engine = ExecutionEngine()
    assert engine.is_triggered(OrderType.STOP, OrderSide.SELL, current_price=99.0, limit_price=None, stop_price=100.0) is True
    assert engine.is_triggered(OrderType.STOP, OrderSide.SELL, current_price=101.0, limit_price=None, stop_price=100.0) is False


def test_is_triggered_take_profit_sell():
    engine = ExecutionEngine()
    assert engine.is_triggered(OrderType.TAKE_PROFIT, OrderSide.SELL, current_price=101.0, limit_price=None, stop_price=100.0) is True
    assert engine.is_triggered(OrderType.TAKE_PROFIT, OrderSide.SELL, current_price=99.0, limit_price=None, stop_price=100.0) is False


def test_is_triggered_take_profit_buy():
    engine = ExecutionEngine()
    assert engine.is_triggered(OrderType.TAKE_PROFIT, OrderSide.BUY, current_price=99.0, limit_price=None, stop_price=100.0) is True
    assert engine.is_triggered(OrderType.TAKE_PROFIT, OrderSide.BUY, current_price=101.0, limit_price=None, stop_price=100.0) is False


def test_is_triggered_market_order_always_false():
    engine = ExecutionEngine()
    assert engine.is_triggered(OrderType.MARKET, OrderSide.BUY, current_price=100.0, limit_price=None, stop_price=None) is False
