"""
OptiTrade Research Lab — Decision Engine validation: trade reconstruction.

Turns an already-evaluated LIVE `learning.models.LearningSample` (a real
decision the live Decision Engine made, scored against its real,
forward-only realized outcome by `learning.evaluator.OutcomeEvaluator`)
into a cost-adjusted `SimulatedTrade`, reusing
`paper_trading.execution.ExecutionEngine`'s existing slippage/spread/
commission/tax math - never re-deriving it.

`LearningSample` stores percent returns only, never prices (see its own
docstring), so every trade here is priced on a normalized $100
reference basis: `ExecutionEngine.simulate_execution_price()` is purely
multiplicative (a proportional bps adjustment), so the actual reference
price cancels out of every percent-return calculation - $100 vs $180
vs $18,000 all produce byte-identical `net_return_pct`. Only the
absolute position size matters (for `compute_commission()`'s minimum-
commission floor and `compute_tax()`'s realized-gain-in-currency
input), which is why `config.validation_position_size_notional` (an
explicit, documented assumption - see item 15 of the task's checklist,
"position sizing assumptions") stands in for a real notional.

Only BUY decisions become trades. This codebase has no short-selling
mechanism anywhere (`paper_trading.models.OrderSide` is BUY/SELL-to-
close only) - a live SELL decision is a directional call, not a
position any part of this system can actually open. Simulating a
monetizable short P&L for it would be inventing an execution path that
does not exist, which is exactly what this validation layer must not
do.
"""
from __future__ import annotations

from typing import Optional

from decision_engine.models import Prediction
from learning.models import LearningSample
from paper_trading.execution import ExecutionEngine
from paper_trading.models import OrderSide
from research_lab.config import ResearchLabConfig
from research_lab.models import SimulatedTrade

_REFERENCE_PRICE = 100.0


def simulate_trade(
    sample: LearningSample, config: ResearchLabConfig, execution_engine: ExecutionEngine,
) -> Optional[SimulatedTrade]:
    """`None` for anything that isn't a realized BUY decision - HOLD (no
    position), SELL (no short-selling support, see module docstring),
    or a sample somehow missing its realized return (defensive; should
    not occur for `evaluated=True` rows, see `OutcomeEvaluator`)."""
    if sample.decision != Prediction.BUY or sample.actual_return is None:
        return None

    notional = config.validation_position_size_notional
    gross_return_pct = sample.actual_return

    entry_price = execution_engine.simulate_execution_price(OrderSide.BUY, _REFERENCE_PRICE)
    raw_exit_price = _REFERENCE_PRICE * (1.0 + gross_return_pct / 100.0)
    exit_price = execution_engine.simulate_execution_price(OrderSide.SELL, raw_exit_price)

    quantity = notional / entry_price
    entry_notional = entry_price * quantity
    exit_notional = exit_price * quantity

    commission = execution_engine.compute_commission(entry_notional) + execution_engine.compute_commission(
        exit_notional
    )
    realized_gain_before_tax = exit_notional - entry_notional
    tax = execution_engine.compute_tax(realized_gain_before_tax)

    net_pnl = realized_gain_before_tax - commission - tax
    net_return_pct = (net_pnl / notional) * 100.0

    price_only_return_pct = ((exit_price - entry_price) / entry_price) * 100.0
    slippage_spread_pct = gross_return_pct - price_only_return_pct

    return SimulatedTrade(
        symbol=sample.symbol,
        decided_at=sample.decided_at,
        evaluation_horizon_days=sample.evaluation_horizon_days,
        confidence=sample.confidence,
        gross_return_pct=gross_return_pct,
        commission_pct=(commission / notional) * 100.0,
        slippage_spread_pct=abs(slippage_spread_pct),
        tax_pct=(tax / notional) * 100.0,
        net_return_pct=net_return_pct,
        net_pnl=net_pnl,
    )
