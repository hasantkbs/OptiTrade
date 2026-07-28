"""
OptiTrade Portfolio Intelligence Platform — Rebalancing Engine
(requirement 5).

Reuses `PositionAnalyticsService.analyze_positions` for current weights
and prices - never re-derives them. Supports three trigger modes:
`MANUAL`/`THRESHOLD` build a plan on demand (`THRESHOLD` additionally
skips any symbol whose drift is still within tolerance, avoiding
transaction costs for immaterial drift); `SCHEDULED` is a time-based
gate (`is_scheduled_rebalance_due`) an external caller checks before
building a plan - mirroring `learning.service.LearningService.
run_learning_cycle`'s "invoked periodically by an external caller,
never self-scheduled" convention.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from portfolio.analytics import PositionAnalyticsService
from portfolio.config import PortfolioConfig
from portfolio.models import PositionAnalytics, RebalanceAction, RebalancePlan, RebalanceTrade, RebalanceTrigger
from portfolio.prices import PriceService


class RebalancingService:
    def __init__(
        self,
        position_analytics_service: Optional[PositionAnalyticsService] = None,
        price_service: Optional[PriceService] = None,
        config: Optional[PortfolioConfig] = None,
    ) -> None:
        self.config = config or PortfolioConfig.from_env()
        self.position_analytics_service = position_analytics_service or PositionAnalyticsService(config=self.config)
        self.price_service = price_service or self.position_analytics_service.price_service

    def is_scheduled_rebalance_due(
        self, last_rebalanced_at: Optional[datetime], interval_days: Optional[int] = None,
    ) -> bool:
        interval_days = interval_days if interval_days is not None else self.config.default_rebalance_interval_days
        if last_rebalanced_at is None:
            return True
        return (datetime.now(timezone.utc) - last_rebalanced_at).days >= interval_days

    def build_plan(
        self,
        portfolio_id: int,
        target_weights_pct: Dict[str, float],
        trigger: RebalanceTrigger = RebalanceTrigger.MANUAL,
        threshold_pct: Optional[float] = None,
        fee_rate_pct: Optional[float] = None,
        position_analytics: Optional[List[PositionAnalytics]] = None,
    ) -> RebalancePlan:
        """`target_weights_pct` are percentages (0-100) of TOTAL
        portfolio value (positions + cash), keyed by symbol - a symbol
        targeted but not currently held is treated as a 0%-current,
        target%-desired BUY."""
        threshold_pct = threshold_pct if threshold_pct is not None else self.config.default_rebalance_threshold_pct
        fee_rate_pct = fee_rate_pct if fee_rate_pct is not None else self.config.default_fee_rate_pct

        positions = (
            position_analytics if position_analytics is not None
            else self.position_analytics_service.analyze_positions(portfolio_id)
        )
        cash_balance = self.position_analytics_service.portfolio_service.get_cash_balance(portfolio_id)
        positions_value = sum(position.current_value for position in positions)
        total_value = positions_value + cash_balance

        current_weights_pct = {position.symbol: position.weight_pct for position in positions}
        current_prices = {position.symbol: position.current_price for position in positions}

        trades: List[RebalanceTrade] = []
        total_fee = 0.0
        for symbol in sorted(set(current_weights_pct) | set(target_weights_pct)):
            current_weight = current_weights_pct.get(symbol, 0.0)
            target_weight = target_weights_pct.get(symbol, 0.0)
            drift = current_weight - target_weight
            if abs(drift) < 1e-6:
                continue
            if trigger == RebalanceTrigger.THRESHOLD and abs(drift) <= threshold_pct:
                continue

            price = current_prices.get(symbol)
            if price is None:
                price = self.price_service.get_current_price(symbol)

            diff_value = (total_value * target_weight / 100.0) - (total_value * current_weight / 100.0)
            fee = abs(diff_value) * fee_rate_pct / 100.0
            trades.append(
                RebalanceTrade(
                    symbol=symbol, action=RebalanceAction.BUY if diff_value > 0 else RebalanceAction.SELL,
                    current_weight_pct=current_weight, target_weight_pct=target_weight, drift_pct=drift,
                    quantity=abs(diff_value) / price if price > 0 else 0.0, estimated_price=price,
                    estimated_amount=abs(diff_value), estimated_fee=fee,
                )
            )
            total_fee += fee

        return RebalancePlan(
            portfolio_id=portfolio_id, trigger=trigger, needs_rebalancing=len(trades) > 0, trades=trades,
            total_estimated_fees=total_fee,
        )
