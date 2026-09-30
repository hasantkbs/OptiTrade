"""
OptiTrade Watchlist & Alert Platform — Portfolio Alerts.

Reuses `portfolio.analytics.PositionAnalyticsService`/`portfolio.risk.
RiskAnalyticsService` directly - never recomputes position weights,
VaR, drawdown, or concentration a second time.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from portfolio.analytics import PositionAnalyticsService
from portfolio.exceptions import InsufficientPriceDataError
from portfolio.risk import RiskAnalyticsService
from watchlist.config import WatchlistConfig
from watchlist.exceptions import InsufficientAlertDataError, InvalidAlertError
from watchlist.models import Alert, AlertCategory, AlertTriggerEvent, AlertType


class PortfolioAlertEvaluator:
    def __init__(
        self,
        position_analytics_service: Optional[PositionAnalyticsService] = None,
        risk_analytics_service: Optional[RiskAnalyticsService] = None,
        config: Optional[WatchlistConfig] = None,
    ) -> None:
        self.config = config or WatchlistConfig.from_env()
        self.position_analytics_service = position_analytics_service or PositionAnalyticsService()
        self.risk_analytics_service = risk_analytics_service or RiskAnalyticsService(
            position_analytics_service=self.position_analytics_service,
        )

    def evaluate(self, alert: Alert) -> Tuple[Optional[AlertTriggerEvent], Dict[str, float]]:
        if alert.category != AlertCategory.PORTFOLIO:
            raise InvalidAlertError(f"PortfolioAlertEvaluator cannot evaluate category {alert.category!r}")
        if alert.portfolio_id is None:
            raise InvalidAlertError("portfolio alerts require a portfolio_id")

        if alert.alert_type == AlertType.PORTFOLIO_ALLOCATION_EXCEEDED:
            return self._allocation_check(alert)
        if alert.alert_type == AlertType.PORTFOLIO_VAR_EXCEEDED:
            return self._risk_metric_check(
                alert, metric_name="var_95_pct",
                default_threshold=self.config.portfolio_var_threshold_pct,
                describe=lambda value, threshold: (
                    f"portfolio {alert.portfolio_id} VaR(95%) {value:.2f}% breached the {threshold:.2f}% limit"
                ),
            )
        if alert.alert_type == AlertType.PORTFOLIO_DRAWDOWN_EXCEEDED:
            return self._risk_metric_check(
                alert, metric_name="max_drawdown_pct",
                default_threshold=self.config.portfolio_drawdown_threshold_pct,
                describe=lambda value, threshold: (
                    f"portfolio {alert.portfolio_id} max drawdown {value:.2f}% breached the {threshold:.2f}% limit"
                ),
            )
        if alert.alert_type == AlertType.PORTFOLIO_CONCENTRATION:
            return self._risk_metric_check(
                alert, metric_name="concentration_risk",
                default_threshold=self.config.portfolio_concentration_threshold,
                describe=lambda value, threshold: (
                    f"portfolio {alert.portfolio_id} concentration risk (HHI={value:.2f}) "
                    f"exceeds {threshold:.2f}"
                ),
            )
        raise InvalidAlertError(f"unsupported portfolio alert_type {alert.alert_type!r}")

    def _positions(self, alert: Alert):
        positions = self.position_analytics_service.analyze_positions(alert.portfolio_id)
        if not positions:
            raise InsufficientAlertDataError(f"portfolio {alert.portfolio_id} has no open positions")
        return positions

    def _allocation_check(self, alert: Alert) -> Tuple[Optional[AlertTriggerEvent], Dict[str, float]]:
        positions = self._positions(alert)
        threshold = alert.parameters.get("threshold_pct", self.config.portfolio_allocation_threshold_pct)

        if alert.symbol:
            position = next((p for p in positions if p.symbol == alert.symbol), None)
            if position is None:
                return None, {}
            new_state = {"weight_pct": position.weight_pct}
            if position.weight_pct <= threshold:
                return None, new_state
            event = self._event(
                alert, f"{position.symbol} allocation {position.weight_pct:.1f}% exceeds {threshold:.1f}%",
                {"symbol_weight_pct": position.weight_pct, "threshold_pct": threshold},
            )
            return event, new_state

        worst = max(positions, key=lambda position: position.weight_pct)
        new_state = {"max_weight_pct": worst.weight_pct}
        if worst.weight_pct <= threshold:
            return None, new_state
        event = self._event(
            alert, f"{worst.symbol} allocation {worst.weight_pct:.1f}% exceeds {threshold:.1f}%",
            {"weight_pct": worst.weight_pct, "threshold_pct": threshold}, symbol=worst.symbol,
        )
        return event, new_state

    def _risk_metric_check(
        self, alert: Alert, metric_name: str, default_threshold: float, describe,
    ) -> Tuple[Optional[AlertTriggerEvent], Dict[str, float]]:
        positions = self._positions(alert)
        try:
            risk = self.risk_analytics_service.analyze(alert.portfolio_id, positions)
        except InsufficientPriceDataError as exc:
            raise InsufficientAlertDataError(str(exc)) from exc

        value = getattr(risk, metric_name)
        threshold = alert.parameters.get("threshold", default_threshold)
        new_state = {metric_name: value}

        # VaR/drawdown are negative numbers (a bigger loss is MORE
        # negative, i.e. lower); concentration is a positive [0, 1]
        # score (a bigger risk is higher) - both "worse than threshold"
        # directions are expressed correctly by a single comparison
        # once the sign convention of each metric is taken into account.
        breached = value < threshold if threshold < 0 else value > threshold
        if not breached:
            return None, new_state

        event = self._event(alert, describe(value, threshold), {metric_name: value, "threshold": threshold})
        return event, new_state

    @staticmethod
    def _event(
        alert: Alert, message: str, evidence: Dict[str, float], symbol: Optional[str] = None,
    ) -> AlertTriggerEvent:
        return AlertTriggerEvent(
            alert_id=alert.id, owner=alert.owner, portfolio_id=alert.portfolio_id,
            symbol=symbol if symbol is not None else alert.symbol,
            category=alert.category, alert_type=alert.alert_type, message=message, evidence=evidence,
        )
