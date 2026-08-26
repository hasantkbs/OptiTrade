"""
OptiTrade Portfolio Intelligence Platform — Recommendation Engine
(requirement 7).

Reuses `PositionAnalyticsService`/`RiskAnalyticsService`/
`RebalancingService` output directly (never recomputes) and, when a
`pipeline_service` (`pipeline.service.PipelineService`) is supplied,
factors in the Decision Engine's own already-computed BUY/HOLD/SELL
signal for each held symbol - "Use Decision Engine outputs together
with Portfolio Analytics".
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from core.structured_logging import STATUS_ERROR, log_event
from decision_engine.models import Prediction
from portfolio.analytics import PositionAnalyticsService
from portfolio.config import PortfolioConfig
from portfolio.exceptions import InsufficientPriceDataError
from portfolio.models import (
    PositionAnalytics,
    Recommendation,
    RecommendationSeverity,
    RecommendationType,
    RiskAnalytics,
)
from portfolio.rebalancing import RebalancingService
from portfolio.risk import RiskAnalyticsService

logger = logging.getLogger(__name__)

_OVERWEIGHT_WARNING_THRESHOLD_PCT = 25.0
_OVERWEIGHT_CRITICAL_THRESHOLD_PCT = 40.0
_SECTOR_CONCENTRATION_THRESHOLD_PCT = 40.0
_CONCENTRATION_WARNING_THRESHOLD = 0.5
_CONCENTRATION_CRITICAL_THRESHOLD = 0.7
_LOW_DIVERSIFICATION_THRESHOLD = 0.3
_HELD_WEIGHT_MATERIAL_PCT = 5.0


class RecommendationEngine:
    def __init__(
        self,
        position_analytics_service: Optional[PositionAnalyticsService] = None,
        risk_analytics_service: Optional[RiskAnalyticsService] = None,
        rebalancing_service: Optional[RebalancingService] = None,
        pipeline_service=None,
        config: Optional[PortfolioConfig] = None,
    ) -> None:
        self.config = config or PortfolioConfig.from_env()
        self.position_analytics_service = position_analytics_service or PositionAnalyticsService(config=self.config)
        self.risk_analytics_service = risk_analytics_service or RiskAnalyticsService(
            position_analytics_service=self.position_analytics_service, config=self.config,
        )
        self.rebalancing_service = rebalancing_service or RebalancingService(
            position_analytics_service=self.position_analytics_service, config=self.config,
        )
        # Optional[pipeline.service.PipelineService] - not type-hinted
        # to avoid constructing the whole production Pipeline merely to
        # annotate an optional dependency.
        self.pipeline_service = pipeline_service

    def generate(
        self,
        portfolio_id: int,
        target_weights_pct: Optional[Dict[str, float]] = None,
        position_analytics: Optional[List[PositionAnalytics]] = None,
        risk_analytics: Optional[RiskAnalytics] = None,
    ) -> List[Recommendation]:
        positions = (
            position_analytics if position_analytics is not None
            else self.position_analytics_service.analyze_positions(portfolio_id)
        )
        if not positions:
            return []

        recommendations: List[Recommendation] = []
        recommendations.extend(self._overweight_warnings(positions))
        recommendations.extend(self._sector_diversification_warnings(positions))

        risk = risk_analytics
        if risk is None:
            try:
                risk = self.risk_analytics_service.analyze(portfolio_id, positions)
            except InsufficientPriceDataError:
                risk = None
        if risk is not None:
            recommendations.extend(self._risk_based_recommendations(risk, len(positions)))

        if target_weights_pct:
            recommendations.extend(self._rebalance_suggestions(portfolio_id, target_weights_pct, positions))

        if self.pipeline_service is not None:
            recommendations.extend(self._decision_signal_recommendations(positions))

        return recommendations

    def _overweight_warnings(self, positions: List[PositionAnalytics]) -> List[Recommendation]:
        warnings = []
        for position in positions:
            if position.weight_pct <= _OVERWEIGHT_WARNING_THRESHOLD_PCT:
                continue
            severity = (
                RecommendationSeverity.CRITICAL if position.weight_pct > _OVERWEIGHT_CRITICAL_THRESHOLD_PCT
                else RecommendationSeverity.WARNING
            )
            warnings.append(
                Recommendation(
                    recommendation_type=RecommendationType.OVERWEIGHT, severity=severity, symbol=position.symbol,
                    message=(
                        f"{position.symbol} is {position.weight_pct:.1f}% of the portfolio, above the "
                        f"{_OVERWEIGHT_WARNING_THRESHOLD_PCT:.0f}% overweight threshold."
                    ),
                    evidence=[f"weight_pct={position.weight_pct:.2f}"],
                )
            )
        return warnings

    def _sector_diversification_warnings(self, positions: List[PositionAnalytics]) -> List[Recommendation]:
        weight_by_sector: Dict[str, float] = {}
        for position in positions:
            weight_by_sector[position.sector] = weight_by_sector.get(position.sector, 0.0) + position.weight_pct

        warnings = []
        for sector, weight in weight_by_sector.items():
            if weight <= _SECTOR_CONCENTRATION_THRESHOLD_PCT:
                continue
            warnings.append(
                Recommendation(
                    recommendation_type=RecommendationType.DIVERSIFICATION, severity=RecommendationSeverity.WARNING,
                    message=(
                        f"The {sector} sector is {weight:.1f}% of the portfolio - consider diversifying "
                        f"into other sectors."
                    ),
                    evidence=[f"sector={sector}", f"weight_pct={weight:.2f}"],
                )
            )
        return warnings

    def _risk_based_recommendations(self, risk: RiskAnalytics, position_count: int) -> List[Recommendation]:
        recommendations = []
        if risk.concentration_risk > _CONCENTRATION_WARNING_THRESHOLD:
            severity = (
                RecommendationSeverity.CRITICAL if risk.concentration_risk > _CONCENTRATION_CRITICAL_THRESHOLD
                else RecommendationSeverity.WARNING
            )
            recommendations.append(
                Recommendation(
                    recommendation_type=RecommendationType.CONCENTRATION, severity=severity,
                    message=(
                        f"Concentration risk (HHI={risk.concentration_risk:.2f}) is high - holdings are "
                        f"not well spread across positions."
                    ),
                    evidence=[f"concentration_risk={risk.concentration_risk:.3f}"],
                )
            )
        if position_count >= 2 and risk.diversification_score < _LOW_DIVERSIFICATION_THRESHOLD:
            recommendations.append(
                Recommendation(
                    recommendation_type=RecommendationType.DIVERSIFICATION, severity=RecommendationSeverity.WARNING,
                    message=(
                        f"Diversification score is low ({risk.diversification_score:.2f}) - held positions "
                        f"tend to move together, reducing the benefit of holding more than one."
                    ),
                    evidence=[f"diversification_score={risk.diversification_score:.3f}"],
                )
            )
        return recommendations

    def _rebalance_suggestions(
        self, portfolio_id: int, target_weights_pct: Dict[str, float], positions: List[PositionAnalytics],
    ) -> List[Recommendation]:
        from portfolio.models import RebalanceTrigger

        plan = self.rebalancing_service.build_plan(
            portfolio_id, target_weights_pct, trigger=RebalanceTrigger.THRESHOLD, position_analytics=positions,
        )
        if not plan.needs_rebalancing:
            return []
        trade_summary = ", ".join(f"{trade.symbol} ({trade.action.value})" for trade in plan.trades)
        return [
            Recommendation(
                recommendation_type=RecommendationType.REBALANCE, severity=RecommendationSeverity.INFO,
                message=f"Portfolio has drifted from its target allocation - suggested trades: {trade_summary}.",
                evidence=[f"{trade.symbol}: drift={trade.drift_pct:.2f}pp" for trade in plan.trades],
            )
        ]

    def _decision_signal_recommendations(self, positions: List[PositionAnalytics]) -> List[Recommendation]:
        recommendations = []
        for position in positions:
            try:
                response = self.pipeline_service.run(position.symbol)
            except Exception as exc:
                log_event(
                    logger, component="portfolio", module="portfolio.recommendations",
                    operation="decision_signal_lookup", status=STATUS_ERROR, symbol=position.symbol,
                    error_type=type(exc).__name__, level=logging.WARNING,
                )
                continue

            if response.decision == Prediction.SELL and position.weight_pct > _HELD_WEIGHT_MATERIAL_PCT:
                recommendations.append(
                    Recommendation(
                        recommendation_type=RecommendationType.DECISION_SIGNAL, severity=RecommendationSeverity.WARNING,
                        symbol=position.symbol,
                        message=(
                            f"Decision Engine signals SELL on {position.symbol} (confidence "
                            f"{response.confidence:.0%}), currently held at {position.weight_pct:.1f}% weight."
                        ),
                        evidence=[f"decision={response.decision.value}", f"confidence={response.confidence:.3f}"],
                        related_decision=response.decision,
                    )
                )
            elif response.decision == Prediction.BUY and position.weight_pct < _HELD_WEIGHT_MATERIAL_PCT:
                recommendations.append(
                    Recommendation(
                        recommendation_type=RecommendationType.DECISION_SIGNAL, severity=RecommendationSeverity.INFO,
                        symbol=position.symbol,
                        message=(
                            f"Decision Engine signals BUY on {position.symbol} (confidence "
                            f"{response.confidence:.0%}), currently a small {position.weight_pct:.1f}% position."
                        ),
                        evidence=[f"decision={response.decision.value}", f"confidence={response.confidence:.3f}"],
                        related_decision=response.decision,
                    )
                )
        return recommendations
