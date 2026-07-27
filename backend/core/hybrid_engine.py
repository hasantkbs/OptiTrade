"""
OptiTrade — Hybrid Trading Engine (Orkestratör)
==================================================
Tarama (MarketRegimeScanner), Analiz (MultiTimeframeAnalyzer), Risk
(DynamicRiskManager) ve Öneri (AITraderPersona) katmanlarını uçtan uca
bağlayan ana motor. Ayrıca:

- Sembol başına üretilen ``TradeRecommendation``'ları belirli bir süre
  (varsayılan 15 dakika) bellek-içi cache'te tutar; geçerli bir cache
  girdisi varsa LLM'e (Groq) tekrar istek atılmaz — bu, ör. bir
  dashboard'un sık sık (60 saniyede bir) ``run()`` çağırmasını
  LLM/rate-limit maliyeti olmadan mümkün kılar.
- Piyasa rejimi filtresini geçen semboller için opsiyonel olarak haber
  duygusu (``NewsSentimentAdapter``) çeker ve AI'ya sunar.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from core.ai_trader_persona import AITraderPersona, TradeRecommendation
from core.cache_manager import TTLCache
from core.interfaces import (
    NewsSentimentProtocol,
    RegimeScannerProtocol,
    RiskManagerProtocol,
    TimeframeAnalyzerProtocol,
    TraderPersonaProtocol,
)
from core.mtf_analyzer import MultiTimeframeAnalyzer
from core.news_adapter import NewsSentimentAdapter
from core.regime_scanner import MarketRegimeScanner, ScannedSymbol
from core.risk_manager import DynamicRiskManager

logger = logging.getLogger(__name__)

DEFAULT_RECOMMENDATION_CACHE_TTL_SECONDS = 15 * 60  # 15 dakika


class HybridTradingEngine:
    """Dört katmanı (Tarama → Analiz → Risk → Öneri) sırayla çalıştıran orkestratör.

    Her katman bağımsız olarak enjekte edilebilir (test/mock için); verilmezse
    varsayılan parametrelerle örneklenir.
    """

    def __init__(
        self,
        scanner: Optional[RegimeScannerProtocol] = None,
        analyzer: Optional[TimeframeAnalyzerProtocol] = None,
        risk_manager: Optional[RiskManagerProtocol] = None,
        ai_persona: Optional[TraderPersonaProtocol] = None,
        news_adapter: Optional[NewsSentimentProtocol] = None,
        recommendation_cache_ttl_seconds: float = DEFAULT_RECOMMENDATION_CACHE_TTL_SECONDS,
    ) -> None:
        self.scanner = scanner or MarketRegimeScanner()
        self.analyzer = analyzer or MultiTimeframeAnalyzer()
        self.risk_manager = risk_manager or DynamicRiskManager()
        self.ai_persona = ai_persona or AITraderPersona()
        self.news_adapter = news_adapter or NewsSentimentAdapter()
        self._recommendation_cache: TTLCache[TradeRecommendation] = TTLCache(
            ttl_seconds=recommendation_cache_ttl_seconds
        )

    def run(self, symbols: List[str]) -> List[TradeRecommendation]:
        """Sembol listesini uçtan uca işleyip AI tarafından üretilmiş önerileri döner.

        Piyasa rejimine göre fırsatsız (CHOPPY) sembolleri eler; kalanlar için
        (cache'te geçerli bir öneri yoksa) analiz + risk + haber duygusu
        hesaplanır ve LLM'e sunularak nihai öneri üretilir. Herhangi bir
        sembolde hata oluşursa o sembol atlanır, akış durmaz.
        """
        recommendations: List[TradeRecommendation] = []

        scanned_symbols = self.scanner.scan_and_filter(symbols)
        logger.info(f"{len(scanned_symbols)}/{len(symbols)} sembol piyasa rejimi filtresini geçti")

        for scanned in scanned_symbols:
            recommendation = self._process_symbol(scanned)
            if recommendation is not None:
                recommendations.append(recommendation)

        return recommendations

    def _process_symbol(self, scanned: ScannedSymbol) -> Optional[TradeRecommendation]:
        symbol = scanned.symbol

        cached = self._recommendation_cache.get(symbol)
        if cached is not None:
            logger.info(f"{symbol}: geçerli cache bulundu, LLM çağrısı atlanıyor")
            return cached

        try:
            analysis = self.analyzer.analyze(symbol)
            if analysis is None:
                logger.warning(f"{symbol}: analiz verisi yetersiz, atlanıyor")
                return None

            risk = self.risk_manager.calculate(
                entry_price=analysis["current_price"],
                atr=analysis["atr_daily"],
            )

            news_sentiment = self.news_adapter.get_sentiment(symbol)

            recommendation = self.ai_persona.generate_recommendation(
                symbol=symbol,
                market_regime=scanned.regime,
                analysis=analysis,
                risk=risk,
                news_sentiment=news_sentiment,
            )
            self._recommendation_cache.set(symbol, recommendation)
            return recommendation
        except Exception as exc:
            logger.error(f"{symbol}: hibrit motor hatası: {exc}")
            return None
