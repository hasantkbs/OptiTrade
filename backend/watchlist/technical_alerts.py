"""
OptiTrade Watchlist & Alert Platform — Technical Alerts.

Every indicator value is read straight from the Feature Store, exactly
as `engines.technical` already computed and wrote it - this module
never recomputes RSI/MACD/EMA/Bollinger/volume/ATR itself, only
interprets already-stored values against alert thresholds
(requirement: "Feature Store integration").
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from engines.technical.config import (
    FEATURE_ATR_PCT,
    FEATURE_BB_PERCENT_B,
    FEATURE_EMA_CROSSOVER,
    FEATURE_MACD_LINE,
    FEATURE_MACD_SIGNAL,
    FEATURE_RSI,
    FEATURE_VOLUME_RATIO,
)
from feature_store.service import FeatureStoreService, get_default_feature_store_service
from watchlist.config import WatchlistConfig
from watchlist.exceptions import InsufficientAlertDataError, InvalidAlertError
from watchlist.models import Alert, AlertCategory, AlertTriggerEvent, AlertType

_GOLDEN_CROSS_VALUE = 2.0
_DEATH_CROSS_VALUE = -2.0


class TechnicalAlertEvaluator:
    def __init__(
        self, feature_store: Optional[FeatureStoreService] = None, config: Optional[WatchlistConfig] = None,
    ) -> None:
        self.config = config or WatchlistConfig.from_env()
        self.feature_store = feature_store or get_default_feature_store_service()

    def evaluate(self, alert: Alert) -> Tuple[Optional[AlertTriggerEvent], Dict[str, float]]:
        if alert.category != AlertCategory.TECHNICAL:
            raise InvalidAlertError(f"TechnicalAlertEvaluator cannot evaluate category {alert.category!r}")
        if not alert.symbol:
            raise InvalidAlertError("technical alerts require a symbol")

        if alert.alert_type == AlertType.RSI_THRESHOLD:
            return self._rsi_check(alert)
        if alert.alert_type == AlertType.MACD_CROSSOVER:
            return self._macd_crossover_check(alert)
        if alert.alert_type == AlertType.EMA_CROSSOVER:
            return self._ema_crossover_check(alert)
        if alert.alert_type == AlertType.BOLLINGER_BREAKOUT:
            return self._bollinger_check(alert)
        if alert.alert_type == AlertType.VOLUME_SPIKE:
            return self._volume_spike_check(alert)
        if alert.alert_type == AlertType.ATR_EXPANSION:
            return self._atr_expansion_check(alert)
        raise InvalidAlertError(f"unsupported technical alert_type {alert.alert_type!r}")

    def _feature_value(self, symbol: str, feature_name: str) -> Optional[float]:
        record = self.feature_store.get_latest_feature(symbol, feature_name)
        if record is None:
            return None
        age_seconds = (datetime.now(timezone.utc) - record.event_timestamp).total_seconds()
        if age_seconds > self.config.feature_max_age_seconds:
            return None
        return record.value

    def _require_feature(self, symbol: str, feature_name: str) -> float:
        value = self._feature_value(symbol, feature_name)
        if value is None:
            raise InsufficientAlertDataError(
                f"no fresh {feature_name!r} feature available for {symbol!r}"
            )
        return value

    def _rsi_check(self, alert: Alert) -> Tuple[Optional[AlertTriggerEvent], Dict[str, float]]:
        rsi = self._require_feature(alert.symbol, FEATURE_RSI)
        new_state = {"rsi": rsi}
        overbought = alert.parameters.get("overbought", self.config.rsi_overbought)
        oversold = alert.parameters.get("oversold", self.config.rsi_oversold)

        if rsi >= overbought:
            return self._event(alert, f"{alert.symbol} RSI {rsi:.1f} is overbought (>= {overbought:.1f})",
                                {"rsi": rsi, "overbought": overbought}), new_state
        if rsi <= oversold:
            return self._event(alert, f"{alert.symbol} RSI {rsi:.1f} is oversold (<= {oversold:.1f})",
                                {"rsi": rsi, "oversold": oversold}), new_state
        return None, new_state

    def _macd_crossover_check(self, alert: Alert) -> Tuple[Optional[AlertTriggerEvent], Dict[str, float]]:
        macd_line = self._require_feature(alert.symbol, FEATURE_MACD_LINE)
        macd_signal = self._require_feature(alert.symbol, FEATURE_MACD_SIGNAL)
        current_diff = macd_line - macd_signal
        new_state = {"macd_line": macd_line, "macd_signal": macd_signal, "macd_diff": current_diff}

        previous_diff = alert.last_state.get("macd_diff")
        if previous_diff is None:
            return None, new_state  # first observation - nothing to compare a crossover against yet

        crossed_bullish = previous_diff <= 0 < current_diff
        crossed_bearish = previous_diff >= 0 > current_diff
        if not (crossed_bullish or crossed_bearish):
            return None, new_state

        direction = "bullish" if crossed_bullish else "bearish"
        event = self._event(
            alert, f"{alert.symbol} MACD {direction} crossover (line {macd_line:.4f}, signal {macd_signal:.4f})",
            {"macd_line": macd_line, "macd_signal": macd_signal, "macd_diff": current_diff},
        )
        return event, new_state

    def _ema_crossover_check(self, alert: Alert) -> Tuple[Optional[AlertTriggerEvent], Dict[str, float]]:
        crossover_value = self._require_feature(alert.symbol, FEATURE_EMA_CROSSOVER)
        new_state = {"ema_crossover": crossover_value}

        if crossover_value == _GOLDEN_CROSS_VALUE:
            return self._event(alert, f"{alert.symbol} EMA golden cross", {"ema_crossover": crossover_value}), new_state
        if crossover_value == _DEATH_CROSS_VALUE:
            return self._event(alert, f"{alert.symbol} EMA death cross", {"ema_crossover": crossover_value}), new_state
        return None, new_state

    def _bollinger_check(self, alert: Alert) -> Tuple[Optional[AlertTriggerEvent], Dict[str, float]]:
        percent_b = self._require_feature(alert.symbol, FEATURE_BB_PERCENT_B)
        new_state = {"bollinger_percent_b": percent_b}
        upper = alert.parameters.get("upper_percent_b", self.config.bollinger_upper_percent_b)
        lower = alert.parameters.get("lower_percent_b", self.config.bollinger_lower_percent_b)

        if percent_b > upper:
            return self._event(
                alert, f"{alert.symbol} broke out above the Bollinger upper band (%B={percent_b:.2f})",
                {"bollinger_percent_b": percent_b, "upper_percent_b": upper},
            ), new_state
        if percent_b < lower:
            return self._event(
                alert, f"{alert.symbol} broke out below the Bollinger lower band (%B={percent_b:.2f})",
                {"bollinger_percent_b": percent_b, "lower_percent_b": lower},
            ), new_state
        return None, new_state

    def _volume_spike_check(self, alert: Alert) -> Tuple[Optional[AlertTriggerEvent], Dict[str, float]]:
        volume_ratio = self._require_feature(alert.symbol, FEATURE_VOLUME_RATIO)
        new_state = {"volume_ratio": volume_ratio}
        threshold = alert.parameters.get("spike_ratio", self.config.volume_spike_ratio)

        if volume_ratio < threshold:
            return None, new_state
        event = self._event(
            alert, f"{alert.symbol} volume is {volume_ratio:.1f}x average (threshold {threshold:.1f}x)",
            {"volume_ratio": volume_ratio, "threshold": threshold},
        )
        return event, new_state

    def _atr_expansion_check(self, alert: Alert) -> Tuple[Optional[AlertTriggerEvent], Dict[str, float]]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=self.config.atr_history_lookback * 2)
        history = self.feature_store.get_feature_history(alert.symbol, FEATURE_ATR_PCT, start, end)
        if len(history) < 2:
            raise InsufficientAlertDataError(f"not enough ATR history available for {alert.symbol!r}")

        history = sorted(history, key=lambda record: record.event_timestamp)
        current_atr_pct = history[-1].value
        baseline_records = history[:-1][-self.config.atr_history_lookback:]
        baseline_average = sum(record.value for record in baseline_records) / len(baseline_records)
        new_state = {"atr_pct": current_atr_pct, "atr_baseline_pct": baseline_average}

        ratio = alert.parameters.get("expansion_ratio", self.config.atr_expansion_ratio)
        if baseline_average <= 0 or current_atr_pct < baseline_average * ratio:
            return None, new_state

        event = self._event(
            alert,
            f"{alert.symbol} ATR% expanded to {current_atr_pct:.2f} vs a {baseline_average:.2f} baseline "
            f"({ratio:.1f}x threshold)",
            {"atr_pct": current_atr_pct, "atr_baseline_pct": baseline_average, "ratio": ratio},
        )
        return event, new_state

    @staticmethod
    def _event(alert: Alert, message: str, evidence: Dict[str, float]) -> AlertTriggerEvent:
        return AlertTriggerEvent(
            alert_id=alert.id, owner=alert.owner, symbol=alert.symbol, category=alert.category,
            alert_type=alert.alert_type, message=message, evidence=evidence,
        )
