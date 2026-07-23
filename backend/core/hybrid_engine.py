"""
OptiTrade — Hybrid Trading Engine (Orkestratör)
==================================================
Tarama (MarketRegimeScanner), Analiz (MultiTimeframeAnalyzer), Risk
(DynamicRiskManager) ve Öneri (AITraderPersona / InvestorPersona) katmanlarını
uçtan uca bağlayan ana motor. Ayrıca:

- Sembol başına üretilen öneriyi (TradeRecommendation veya
  InvestorRecommendation, ``profile``'a göre) belirli bir süre (varsayılan
  15 dakika) bellek-içi cache'te tutar; geçerli bir cache girdisi varsa
  LLM'e (Groq) tekrar istek atılmaz. Trader ve investor profilleri AYRI
  cache'lerde tutulur, aynı sembol için profil değişimi diğer profilin
  cache'ini bozmaz.
- Piyasa rejimi filtresini geçen semboller için opsiyonel olarak haber
  duygusu (``NewsSentimentAdapter``) çeker ve AI'ya sunar.
- ``check_alerts()``: verilen sembolleri (rejim filtresi UYGULANMADAN) ani
  fiyat/hacim/haber şoku için kontrol eder. Bir öneri isteği (``run()``)
  zaten bir sembol için analiz+haber verisi çekmişse, ``check_alerts()``
  bu veriyi tekrar çekmeden yeniden kullanır (kendi 2 dakikalık cache'i
  üzerinden) — ek yfinance/haber isteği yapmaz.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union

from core.ai_trader_persona import AITraderPersona, TradeRecommendation
from core.cache_manager import TTLCache
from core.investor_persona import InvestorPersona, InvestorRecommendation
from core.market_anomaly_detector import MarketAlert, MarketAnomalyDetector
from core.mtf_analyzer import MultiTimeframeAnalyzer
from core.news_adapter import NewsSentimentAdapter
from core.regime_scanner import MarketRegimeScanner, ScannedSymbol
from core.risk_manager import DynamicRiskManager

logger = logging.getLogger(__name__)

DEFAULT_RECOMMENDATION_CACHE_TTL_SECONDS = 15 * 60  # 15 dakika
DEFAULT_ALERT_CACHE_TTL_SECONDS = 2 * 60  # 2 dakika

# TTLCache.get() süresi dolmuş/hiç yazılmamış bir anahtar için de None döner;
# "kontrol edildi, uyarı yok" durumunu bundan ayırt etmek için sentinel.
_NO_ALERT = object()


class HybridTradingEngine:
    """Dört katmanı (Tarama → Analiz → Risk → Öneri) sırayla çalıştıran orkestratör.

    Her katman bağımsız olarak enjekte edilebilir (test/mock için); verilmezse
    varsayılan parametrelerle örneklenir.
    """

    def __init__(
        self,
        scanner: Optional[MarketRegimeScanner] = None,
        analyzer: Optional[MultiTimeframeAnalyzer] = None,
        risk_manager: Optional[DynamicRiskManager] = None,
        ai_persona: Optional[AITraderPersona] = None,
        investor_persona: Optional[InvestorPersona] = None,
        news_adapter: Optional[NewsSentimentAdapter] = None,
        anomaly_detector: Optional[MarketAnomalyDetector] = None,
        recommendation_cache_ttl_seconds: float = DEFAULT_RECOMMENDATION_CACHE_TTL_SECONDS,
        alert_cache_ttl_seconds: float = DEFAULT_ALERT_CACHE_TTL_SECONDS,
    ) -> None:
        self.scanner = scanner or MarketRegimeScanner()
        self.analyzer = analyzer or MultiTimeframeAnalyzer()
        self.risk_manager = risk_manager or DynamicRiskManager()
        self.ai_persona = ai_persona or AITraderPersona()
        self.investor_persona = investor_persona or InvestorPersona()
        self.news_adapter = news_adapter or NewsSentimentAdapter()
        self.anomaly_detector = anomaly_detector or MarketAnomalyDetector()
        self._recommendation_cache: TTLCache[TradeRecommendation] = TTLCache(
            ttl_seconds=recommendation_cache_ttl_seconds
        )
        self._investor_cache: TTLCache[InvestorRecommendation] = TTLCache(
            ttl_seconds=recommendation_cache_ttl_seconds
        )
        self._alert_cache: TTLCache = TTLCache(ttl_seconds=alert_cache_ttl_seconds)

    def run(
        self, symbols: List[str], profile: str = "trader"
    ) -> Union[List[TradeRecommendation], List[InvestorRecommendation]]:
        """Sembol listesini uçtan uca işleyip AI tarafından üretilmiş önerileri döner.

        ``profile="trader"`` (varsayılan) kısa vadeli ``TradeRecommendation``
        üretir (mevcut davranış, değişmedi). ``profile="investor"`` giriş/SL/TP
        içermeyen, 1 hafta/1 ay/1 yıl ufuklu ``InvestorRecommendation`` üretir.

        Piyasa rejimine göre fırsatsız (CHOPPY) sembolleri eler; kalanlar için
        (cache'te geçerli bir öneri yoksa) analiz + haber duygusu hesaplanır
        ve seçilen profile göre uygun persona'ya sunularak nihai öneri üretilir.
        Herhangi bir sembolde hata oluşursa o sembol atlanır, akış durmaz.
        """
        recommendations: List[Union[TradeRecommendation, InvestorRecommendation]] = []

        scanned_symbols = self.scanner.scan_and_filter(symbols)
        logger.info(f"{len(scanned_symbols)}/{len(symbols)} sembol piyasa rejimi filtresini geçti")

        for scanned in scanned_symbols:
            recommendation = self._process_symbol(scanned, profile)
            if recommendation is not None:
                recommendations.append(recommendation)

        return recommendations

    def check_alerts(self, symbols: List[str]) -> List[MarketAlert]:
        """Verilen tüm sembolleri (piyasa rejimi filtresi UYGULANMADAN) ani değişiklik için kontrol eder.

        Rejim filtresi bilerek atlanır: CHOPPY bir sembolün ani hacim/fiyat
        şoku göstermesi, tam olarak rejim değişikliğinin habercisi olabilir.
        """
        alerts: List[MarketAlert] = []
        for scanned in self.scanner.scan(symbols):
            alert = self._get_or_check_alert(scanned)
            if alert is not None:
                alerts.append(alert)
        return alerts

    def _process_symbol(
        self, scanned: ScannedSymbol, profile: str
    ) -> Optional[Union[TradeRecommendation, InvestorRecommendation]]:
        symbol = scanned.symbol
        cache = self._recommendation_cache if profile == "trader" else self._investor_cache

        cached = cache.get(symbol)
        if cached is not None:
            logger.info(f"{symbol}: geçerli cache bulundu ({profile}), LLM çağrısı atlanıyor")
            return cached

        try:
            analysis = self.analyzer.analyze(symbol)
            if analysis is None:
                logger.warning(f"{symbol}: analiz verisi yetersiz, atlanıyor")
                return None

            news_sentiment = self.news_adapter.get_sentiment(symbol)

            # Zaten çekilmiş analiz+haber verisini alert kontrolü için de kullan (ek istek yok).
            self._update_alert_cache(scanned, analysis, news_sentiment)

            if profile == "trader":
                risk = self.risk_manager.calculate(
                    entry_price=analysis["current_price"],
                    atr=analysis["atr_daily"],
                )
                recommendation: Union[TradeRecommendation, InvestorRecommendation] = (
                    self.ai_persona.generate_recommendation(
                        symbol=symbol,
                        market_regime=scanned.regime,
                        analysis=analysis,
                        risk=risk,
                        news_sentiment=news_sentiment,
                    )
                )
            else:
                recommendation = self.investor_persona.generate_recommendation(
                    symbol=symbol,
                    market_regime=scanned.regime,
                    analysis=analysis,
                    news_sentiment=news_sentiment,
                )

            cache.set(symbol, recommendation)
            return recommendation
        except Exception as exc:
            logger.error(f"{symbol}: hibrit motor hatası ({profile}): {exc}")
            return None

    def _get_or_check_alert(self, scanned: ScannedSymbol) -> Optional[MarketAlert]:
        symbol = scanned.symbol
        cached = self._alert_cache.get(symbol)
        if cached is not None:
            return None if cached is _NO_ALERT else cached

        try:
            analysis = self.analyzer.analyze(symbol)
            if analysis is None:
                return None
            news_sentiment = self.news_adapter.get_sentiment(symbol)
            return self._update_alert_cache(scanned, analysis, news_sentiment)
        except Exception as exc:
            logger.error(f"{symbol}: alert kontrolü hatası: {exc}")
            return None

    def _update_alert_cache(
        self, scanned: ScannedSymbol, analysis: Dict[str, Any], news_sentiment: Optional[Dict[str, Any]]
    ) -> Optional[MarketAlert]:
        alert = self.anomaly_detector.detect(
            symbol=scanned.symbol,
            regime=scanned.regime,
            analysis=analysis,
            news_sentiment=news_sentiment,
        )
        self._alert_cache.set(scanned.symbol, alert if alert is not None else _NO_ALERT)
        return alert
