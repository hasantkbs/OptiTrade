"""
OptiTrade Watchlist & Alert Platform — Price Alerts.

Reuses `data.fetcher.fetch_history` directly - the same function
`main.py`'s own `/price/{symbol}` endpoint already uses for "current
price" - rather than a second price-fetching path.
"""
from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

from data.fetcher import fetch_history
from watchlist.config import WatchlistConfig
from watchlist.exceptions import InsufficientAlertDataError, InvalidAlertError
from watchlist.models import Alert, AlertCategory, AlertTriggerEvent, AlertType

_DEFAULT_PERCENT_MOVE_THRESHOLD_PCT = 5.0
_DEFAULT_GAP_THRESHOLD_PCT = 3.0


class PriceAlertEvaluator:
    def __init__(self, price_fetcher: Optional[Callable] = None, config: Optional[WatchlistConfig] = None) -> None:
        self.config = config or WatchlistConfig.from_env()
        self.price_fetcher = price_fetcher or fetch_history

    def evaluate(self, alert: Alert) -> Tuple[Optional[AlertTriggerEvent], Dict[str, float]]:
        """Returns `(trigger_event_or_None, updated_last_state)` - the
        caller (scheduler.py) persists `updated_last_state`
        unconditionally, regardless of whether this alert fired."""
        if alert.category != AlertCategory.PRICE:
            raise InvalidAlertError(f"PriceAlertEvaluator cannot evaluate category {alert.category!r}")
        if not alert.symbol:
            raise InvalidAlertError("price alerts require a symbol")

        history = self.price_fetcher(alert.symbol, period="5d")
        if history is None or history.empty:
            raise InsufficientAlertDataError(f"no price data available for {alert.symbol!r}")

        current_price = float(history["Close"].iloc[-1])

        if alert.alert_type == AlertType.PRICE_ABOVE:
            return self._threshold_check(alert, current_price, above=True)
        if alert.alert_type == AlertType.PRICE_BELOW:
            return self._threshold_check(alert, current_price, above=False)
        if alert.alert_type == AlertType.PRICE_PERCENT_MOVE:
            return self._percent_move_check(alert, history, current_price)
        if alert.alert_type == AlertType.PRICE_GAP:
            return self._gap_check(alert, history, current_price)
        raise InvalidAlertError(f"unsupported price alert_type {alert.alert_type!r}")

    def _threshold_check(
        self, alert: Alert, current_price: float, above: bool,
    ) -> Tuple[Optional[AlertTriggerEvent], Dict[str, float]]:
        threshold = alert.parameters.get("threshold")
        if threshold is None:
            raise InvalidAlertError(f"alert {alert.id!r}: missing required parameter 'threshold'")
        new_state = {"last_price": current_price}

        condition_met = current_price > threshold if above else current_price < threshold
        if not condition_met:
            return None, new_state

        direction = "above" if above else "below"
        event = AlertTriggerEvent(
            alert_id=alert.id, owner=alert.owner, symbol=alert.symbol, category=alert.category,
            alert_type=alert.alert_type,
            message=f"{alert.symbol} price {current_price:.2f} is {direction} {threshold:.2f}",
            evidence={"price": current_price, "threshold": threshold},
        )
        return event, new_state

    def _percent_move_check(
        self, alert: Alert, history, current_price: float,
    ) -> Tuple[Optional[AlertTriggerEvent], Dict[str, float]]:
        if len(history) < 2:
            raise InsufficientAlertDataError(f"not enough price history to compute a % move for {alert.symbol!r}")
        previous_close = float(history["Close"].iloc[-2])
        change_pct = ((current_price - previous_close) / previous_close * 100.0) if previous_close else 0.0
        new_state = {"last_price": current_price, "change_pct": change_pct}

        threshold_pct = alert.parameters.get("threshold_pct", _DEFAULT_PERCENT_MOVE_THRESHOLD_PCT)
        if abs(change_pct) < threshold_pct:
            return None, new_state

        event = AlertTriggerEvent(
            alert_id=alert.id, owner=alert.owner, symbol=alert.symbol, category=alert.category,
            alert_type=alert.alert_type,
            message=f"{alert.symbol} moved {change_pct:+.2f}% (threshold {threshold_pct:.2f}%)",
            evidence={"price": current_price, "change_pct": change_pct, "threshold_pct": threshold_pct},
        )
        return event, new_state

    def _gap_check(
        self, alert: Alert, history, current_price: float,
    ) -> Tuple[Optional[AlertTriggerEvent], Dict[str, float]]:
        if len(history) < 2:
            raise InsufficientAlertDataError(f"not enough price history to compute a gap for {alert.symbol!r}")
        today_open = float(history["Open"].iloc[-1])
        previous_close = float(history["Close"].iloc[-2])
        gap_pct = ((today_open - previous_close) / previous_close * 100.0) if previous_close else 0.0
        new_state = {"last_price": current_price, "gap_pct": gap_pct}

        threshold_pct = alert.parameters.get("threshold_pct", _DEFAULT_GAP_THRESHOLD_PCT)
        if abs(gap_pct) < threshold_pct:
            return None, new_state

        event = AlertTriggerEvent(
            alert_id=alert.id, owner=alert.owner, symbol=alert.symbol, category=alert.category,
            alert_type=alert.alert_type,
            message=f"{alert.symbol} gapped {gap_pct:+.2f}% at the open (threshold {threshold_pct:.2f}%)",
            evidence={"open": today_open, "previous_close": previous_close, "gap_pct": gap_pct,
                      "threshold_pct": threshold_pct},
        )
        return event, new_state
