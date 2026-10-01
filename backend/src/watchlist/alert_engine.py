"""
OptiTrade Watchlist & Alert Platform — Alert Engine (central
orchestrator).

Dispatches PRICE/TECHNICAL/PORTFOLIO/NEWS alerts to their dedicated
evaluators; Decision Engine alerts (BUY/SELL appears, confidence/
expected-return/risk changes) are implemented directly here, since they
have no dedicated evaluator module - they call straight into
`pipeline.service.PipelineService.run(symbol)`, the exact same
production Decision Engine output `model_serving`/`portfolio` already
reuse, and compare it against `alert.last_state` for edge-triggered
"appeared"/"changed" semantics (never firing every scan the underlying
condition merely remains true).

"Learning integration": each Decision alert's evidence is enriched with
the 30-day accuracy of whichever engines actually contributed to that
decision (`learning.service.LearningService.get_accuracy`), read-only -
so a notification carries not just "BUY appeared" but how reliable that
signal has recently been.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

from core.structured_logging import STATUS_ERROR, log_event
from decision_engine.models import Prediction
from learning.models import RollingWindow
from learning.service import LearningService
from watchlist.config import WatchlistConfig
from watchlist.exceptions import InsufficientAlertDataError, InvalidAlertError
from watchlist.models import Alert, AlertCategory, AlertTriggerEvent, AlertType
from watchlist.news_alerts import NewsAlertEvaluator
from watchlist.portfolio_alerts import PortfolioAlertEvaluator
from watchlist.price_alerts import PriceAlertEvaluator
from watchlist.technical_alerts import TechnicalAlertEvaluator

logger = logging.getLogger(__name__)

_DECISION_ENCODING = {Prediction.SELL: -1.0, Prediction.HOLD: 0.0, Prediction.BUY: 1.0}


class AlertEngine:
    def __init__(
        self,
        price_evaluator: Optional[PriceAlertEvaluator] = None,
        technical_evaluator: Optional[TechnicalAlertEvaluator] = None,
        portfolio_evaluator: Optional[PortfolioAlertEvaluator] = None,
        news_evaluator: Optional[NewsAlertEvaluator] = None,
        pipeline_service=None,
        learning_service: Optional[LearningService] = None,
        config: Optional[WatchlistConfig] = None,
    ) -> None:
        self.config = config or WatchlistConfig.from_env()
        self.price_evaluator = price_evaluator or PriceAlertEvaluator(config=self.config)
        self.technical_evaluator = technical_evaluator or TechnicalAlertEvaluator(config=self.config)
        self.portfolio_evaluator = portfolio_evaluator or PortfolioAlertEvaluator(config=self.config)
        self.news_evaluator = news_evaluator or NewsAlertEvaluator(config=self.config)
        # Optional[pipeline.service.PipelineService] - not type-hinted
        # to avoid constructing the whole production Pipeline merely to
        # annotate an optional dependency.
        self.pipeline_service = pipeline_service
        self.learning_service = learning_service or LearningService()

    def evaluate(self, alert: Alert) -> Tuple[Optional[AlertTriggerEvent], Dict[str, float]]:
        """Returns `(trigger_event_or_None, updated_last_state)` -
        `scheduler.py` persists `updated_last_state` unconditionally."""
        if alert.category == AlertCategory.PRICE:
            return self.price_evaluator.evaluate(alert)
        if alert.category == AlertCategory.TECHNICAL:
            return self.technical_evaluator.evaluate(alert)
        if alert.category == AlertCategory.PORTFOLIO:
            return self.portfolio_evaluator.evaluate(alert)
        if alert.category == AlertCategory.NEWS:
            return self.news_evaluator.evaluate(alert)
        if alert.category == AlertCategory.DECISION:
            return self._evaluate_decision(alert)
        raise InvalidAlertError(f"unknown alert category {alert.category!r}")

    def _evaluate_decision(self, alert: Alert) -> Tuple[Optional[AlertTriggerEvent], Dict[str, float]]:
        if self.pipeline_service is None:
            raise InsufficientAlertDataError("no Pipeline service configured for Decision Engine alerts")
        if not alert.symbol:
            raise InvalidAlertError("decision alerts require a symbol")

        response = self.pipeline_service.run(alert.symbol)
        new_state = {
            "decision": _DECISION_ENCODING[response.decision],
            "confidence": response.confidence,
            "expected_return": response.expected_return,
            "expected_volatility": response.expected_volatility,
        }

        if alert.alert_type == AlertType.DECISION_BUY:
            return self._decision_appears(alert, response, Prediction.BUY, new_state)
        if alert.alert_type == AlertType.DECISION_SELL:
            return self._decision_appears(alert, response, Prediction.SELL, new_state)
        if alert.alert_type == AlertType.CONFIDENCE_CHANGE:
            return self._value_change(
                alert, response, "confidence", response.confidence, self.config.confidence_change_threshold,
                new_state,
            )
        if alert.alert_type == AlertType.EXPECTED_RETURN_CHANGE:
            return self._value_change(
                alert, response, "expected_return", response.expected_return,
                self.config.expected_return_change_threshold_pct, new_state,
            )
        if alert.alert_type == AlertType.RISK_CHANGE:
            return self._value_change(
                alert, response, "expected_volatility", response.expected_volatility,
                self.config.risk_change_threshold_pct, new_state,
            )
        raise InvalidAlertError(f"unsupported decision alert_type {alert.alert_type!r}")

    def _decision_appears(
        self, alert: Alert, response, target: Prediction, new_state: Dict[str, float],
    ) -> Tuple[Optional[AlertTriggerEvent], Dict[str, float]]:
        if response.decision != target:
            return None, new_state

        previous_decision = alert.last_state.get("decision")
        if previous_decision == _DECISION_ENCODING[target]:
            return None, new_state  # already was this decision last scan - edge-triggered, not level-triggered

        evidence = {"confidence": response.confidence, "expected_return": response.expected_return}
        evidence.update(self._engine_accuracy_evidence(response))
        event = AlertTriggerEvent(
            alert_id=alert.id, owner=alert.owner, symbol=alert.symbol, category=alert.category,
            alert_type=alert.alert_type,
            message=f"{alert.symbol}: Decision Engine now says {target.value} (confidence {response.confidence:.0%})",
            evidence=evidence, related_decision=target,
        )
        return event, new_state

    def _value_change(
        self, alert: Alert, response, state_key: str, current_value: float, default_threshold: float,
        new_state: Dict[str, float],
    ) -> Tuple[Optional[AlertTriggerEvent], Dict[str, float]]:
        previous_value = alert.last_state.get(state_key)
        if previous_value is None:
            return None, new_state  # first observation - nothing to compare a change against yet

        threshold = alert.parameters.get("threshold", default_threshold)
        delta = current_value - previous_value
        if abs(delta) < threshold:
            return None, new_state

        evidence = {state_key: current_value, "previous": previous_value, "delta": delta}
        evidence.update(self._engine_accuracy_evidence(response))
        event = AlertTriggerEvent(
            alert_id=alert.id, owner=alert.owner, symbol=alert.symbol, category=alert.category,
            alert_type=alert.alert_type,
            message=f"{alert.symbol}: {state_key.replace('_', ' ')} changed by {delta:+.3f} (now {current_value:.3f})",
            evidence=evidence, related_decision=response.decision,
        )
        return event, new_state

    def _engine_accuracy_evidence(self, response) -> Dict[str, float]:
        """Best-effort: the average 30-day accuracy of whichever
        engines successfully contributed to this decision. Never raises
        - a missing/incomplete accuracy history must not block an
        otherwise-valid alert from firing."""
        accuracies = []
        for item in getattr(response, "engine_breakdown", []):
            if item.status.value != "success":
                continue
            try:
                metrics = self.learning_service.get_accuracy(
                    item.engine_name, item.engine_version, RollingWindow.THIRTY_DAY,
                )
            except Exception as exc:
                log_event(
                    logger, component="watchlist", module="watchlist.alert_engine", operation="engine_accuracy",
                    status=STATUS_ERROR, engine_name=item.engine_name, error_type=type(exc).__name__,
                    level=logging.WARNING,
                )
                continue
            if metrics is not None:
                accuracies.append(metrics.accuracy)
        if not accuracies:
            return {}
        return {"contributing_engine_accuracy_pct": (sum(accuracies) / len(accuracies)) * 100.0}
