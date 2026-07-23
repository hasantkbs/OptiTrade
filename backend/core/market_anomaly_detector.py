"""
OptiTrade — Market Anomaly Detector (Ani Piyasa Değişikliği Tespiti)
========================================================================
MultiTimeframeAnalyzer'ın ürettiği analiz sözlüğü ve NewsSentimentAdapter'ın
ürettiği haber özetinden, ek bir veri çekmeden (tamamen zaten hesaplanmış
metriklerden) ani piyasa değişikliği tespiti yapar. LLM çağrısı yapmaz —
saf, deterministik eşik kontrolü.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from core.regime_scanner import MarketRegime


class MarketAlert(BaseModel):
    """Tespit edilen ani piyasa değişikliği uyarısı."""

    symbol: str
    alert_type: Literal["PRICE_VOLUME_SHOCK", "NEWS_SHOCK", "COMBINED"]
    severity: Literal["MEDIUM", "HIGH"]
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MarketAnomalyDetector:
    """Fiyat/hacim şoku ve yüksek etkili haber şokunu birlikte değerlendiren, durumsuz (stateless) dedektör."""

    def __init__(
        self,
        volume_ratio_threshold: float = 3.0,
        price_move_atr_multiple_threshold: float = 2.5,
    ) -> None:
        self.volume_ratio_threshold = volume_ratio_threshold
        self.price_move_atr_multiple_threshold = price_move_atr_multiple_threshold

    def detect(
        self,
        symbol: str,
        regime: MarketRegime,
        analysis: Dict[str, Any],
        news_sentiment: Optional[Dict[str, Any]],
    ) -> Optional[MarketAlert]:
        """Verilen analiz/haber verisinden bir MarketAlert üretir; şok yoksa None döner."""
        price_volume_triggered, price_direction, pv_details = self._check_price_volume(analysis)
        news_triggered, news_direction, news_details = self._check_news(news_sentiment)

        if not price_volume_triggered and not news_triggered:
            return None

        if price_volume_triggered and news_triggered:
            alert_type = "COMBINED"
            severity = "HIGH"
            direction = price_direction if price_direction == news_direction else "NEUTRAL"
        elif price_volume_triggered:
            alert_type = "PRICE_VOLUME_SHOCK"
            severity = "MEDIUM"
            direction = price_direction
        else:
            alert_type = "NEWS_SHOCK"
            severity = "MEDIUM"
            direction = news_direction

        details = {"market_regime": regime.value, **pv_details, **news_details}
        message = self._build_message(alert_type, direction, details)

        return MarketAlert(
            symbol=symbol,
            alert_type=alert_type,
            severity=severity,
            direction=direction,
            message=message,
            details=details,
        )

    def _check_price_volume(self, analysis: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        micro = analysis.get("micro", {}) or {}
        macro = analysis.get("macro", {}) or {}

        volume_ratio = float(micro.get("volume_ratio", 0.0))
        price_move_atr_multiple = float(macro.get("price_move_atr_multiple", 0.0))
        daily_return_pct = float(macro.get("daily_return_pct", 0.0))

        triggered = (
            volume_ratio >= self.volume_ratio_threshold
            or price_move_atr_multiple >= self.price_move_atr_multiple_threshold
        )
        direction = "BULLISH" if daily_return_pct > 0 else ("BEARISH" if daily_return_pct < 0 else "NEUTRAL")
        details = {
            "volume_ratio": volume_ratio,
            "price_move_atr_multiple": price_move_atr_multiple,
            "daily_return_pct": daily_return_pct,
        }
        return triggered, direction, details

    def _check_news(self, news_sentiment: Optional[Dict[str, Any]]) -> Tuple[bool, str, Dict[str, Any]]:
        if not news_sentiment:
            return False, "NEUTRAL", {}

        impact_level = news_sentiment.get("impact_level")
        sentiment_score = float(news_sentiment.get("sentiment_score", 0.0))
        sentiment_label = news_sentiment.get("sentiment_label", "NEUTRAL")

        triggered = impact_level == "HIGH"
        direction = "BULLISH" if sentiment_score > 0 else ("BEARISH" if sentiment_score < 0 else "NEUTRAL")
        details = {
            "news_impact_level": impact_level,
            "news_sentiment_score": sentiment_score,
            "news_sentiment_label": sentiment_label,
        }
        return triggered, direction, details

    @staticmethod
    def _build_message(alert_type: str, direction: str, details: Dict[str, Any]) -> str:
        if alert_type == "COMBINED" and direction == "NEUTRAL":
            return "Fiyat/hacim hareketi ile haber duygusu birbiriyle çelişiyor — yön belirsiz, dikkatli izleyin."

        direction_tr = {"BULLISH": "yükseliş yönlü", "BEARISH": "düşüş yönlü", "NEUTRAL": "yönü belirsiz"}[direction]

        if alert_type == "COMBINED":
            return (
                f"Hem fiyat/hacim hem de haber kaynaklı ani hareket tespit edildi — {direction_tr} bir gelişme. "
                "Pozisyonunuzu yeniden değerlendirin."
            )
        if alert_type == "PRICE_VOLUME_SHOCK":
            return (
                f"Anormal fiyat/hacim hareketi tespit edildi (hacim oranı: {details.get('volume_ratio')}x, "
                f"ATR katı: {details.get('price_move_atr_multiple')}) — {direction_tr} bir gelişme."
            )
        return (
            f"Yüksek etkili haber akışı tespit edildi — {direction_tr} bir gelişme. "
            "Fiyat henüz tepki vermemiş olabilir."
        )
