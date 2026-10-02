"""
OptiTrade — Hybrid Trading Engine (Orkestratör)
==================================================
Tarama (MarketRegimeScanner), Analiz (MultiTimeframeAnalyzer), Risk
(DynamicRiskManager) ve Öneri (AITraderPersona / InvestorPersona) katmanlarını
uçtan uca bağlayan ana motor. Ayrıca:

- Sembol başına üretilen öneriyi (``TradeRecommendation`` veya
  ``InvestorRecommendation``, ``profile``'a göre) belirli bir süre
  (varsayılan 15 dakika) bellek-içi cache'te tutar; geçerli bir cache
  girdisi varsa LLM'e (Groq) tekrar istek atılmaz. Trader ve investor
  profilleri AYRI cache'lerde tutulur, aynı sembol için profil değişimi
  diğer profilin cache'ini bozmaz.
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
from typing import Any, Dict, List, Literal, Optional, Union

from core.ai_trader_persona import AITraderPersona, TradeRecommendation
from core.analysis_presentation import is_data_sufficient, to_trade_signal
from core.cache_manager import TTLCache
from core.interfaces import (
    AnomalyDetectorProtocol,
    InvestorPersonaProtocol,
    NewsSentimentProtocol,
    RegimeScannerProtocol,
    RiskManagerProtocol,
    TimeframeAnalyzerProtocol,
    TraderPersonaProtocol,
)
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
        scanner: Optional[RegimeScannerProtocol] = None,
        analyzer: Optional[TimeframeAnalyzerProtocol] = None,
        risk_manager: Optional[RiskManagerProtocol] = None,
        ai_persona: Optional[TraderPersonaProtocol] = None,
        investor_persona: Optional[InvestorPersonaProtocol] = None,
        news_adapter: Optional[NewsSentimentProtocol] = None,
        anomaly_detector: Optional[AnomalyDetectorProtocol] = None,
        decision_engine: Optional[Any] = None,
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
        # `Any`, not a `core.interfaces` Protocol like the layers above:
        # only needs a `.decide(symbol) -> DecisionOutput` method
        # (decision_engine.service.DecisionEngine's own shape); kept
        # untyped here rather than adding a new Protocol for one method
        # used by one call site (`_apply_canonical_decision` below).
        # `None` here means "resolve the shared default lazily, on first
        # use in `_apply_canonical_decision`" - deliberately NOT resolved
        # eagerly here the way the other layers above are: this
        # constructor runs in test/script contexts (test_engine.py,
        # terminal_dashboard.py, every characterization test in
        # tests/test_hybrid_engine.py and tests/unit/test_hybrid_engine.py)
        # that construct a `HybridTradingEngine()` without ever calling
        # `.run()` or without injecting a fake, and none of those should
        # pay for (or depend on) a real Feature Store/engine registry
        # connection just from construction.
        self.decision_engine = decision_engine
        self._recommendation_cache: TTLCache[TradeRecommendation] = TTLCache(
            ttl_seconds=recommendation_cache_ttl_seconds
        )
        self._investor_cache: TTLCache[InvestorRecommendation] = TTLCache(
            ttl_seconds=recommendation_cache_ttl_seconds
        )
        self._alert_cache: TTLCache = TTLCache(ttl_seconds=alert_cache_ttl_seconds)

    def run(
        self, symbols: List[str], profile: Literal["trader", "investor"] = "trader"
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
        self, scanned: ScannedSymbol, profile: Literal["trader", "investor"]
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
                recommendation = self._apply_canonical_decision(symbol, recommendation)
            else:
                recommendation = self.investor_persona.generate_recommendation(
                    symbol=symbol,
                    market_regime=scanned.regime,
                    analysis=analysis,
                    news_sentiment=news_sentiment,
                )
                recommendation = self._apply_canonical_decision_to_investor_horizon(symbol, recommendation)

            cache.set(symbol, recommendation)
            return recommendation
        except Exception as exc:
            logger.error(f"{symbol}: hibrit motor hatası ({profile}): {exc}")
            return None

    def _apply_canonical_decision(
        self, symbol: str, recommendation: TradeRecommendation
    ) -> TradeRecommendation:
        """Overrides the LLM's own `signal`/`confidence_score` with the
        Decision Engine's statistical vote for this symbol - see
        docs/architecture/gap-analysis.md section 2 ("LLMs are
        explanation engines only; they do not make investment
        decisions"). `AITraderPersona`'s prompt/schema are unchanged
        (it still produces a `signal` of its own), so `trader_analysis`/
        `investor_analysis`/`trader_commentary` keep reading as a
        synthesis that arrives at *a* signal - but the signal actually
        returned to the caller is always the same one `decision_engine`
        would give any other consumer for this symbol, never the LLM's.
        `entry_price`/`stop_loss`/`take_profit_*` are untouched (already
        sourced from `risk_manager`, not the LLM, before this runs).

        A Decision Engine failure (infra down, zero valid votes, etc.)
        falls back to the LLM's own signal rather than dropping the
        recommendation entirely - this symbol's caching/error-isolation
        behavior in `_process_symbol` is otherwise unaffected. A
        successful-but-low-data_sufficiency output (e.g. only 1 of 5
        engines voted) gets the same fallback treatment via
        `analysis_presentation.is_data_sufficient()` - see
        intelligence/opportunity.py:60's identical precedent."""
        try:
            decision_engine = self.decision_engine
            if decision_engine is None:
                from decision_engine.service import get_default_decision_engine

                decision_engine = get_default_decision_engine()
            decision_output = decision_engine.decide(symbol, strict=True)
        except Exception as exc:
            logger.error(
                f"{symbol}: decision engine yetkisi uygulanamadi, LLM sinyali korunuyor: {exc}"
            )
            return recommendation
        if not is_data_sufficient(decision_output):
            logger.warning(
                f"{symbol}: decision engine data_sufficiency={decision_output.data_sufficiency:.2f} "
                "yetersiz (quality gate), LLM sinyali korunuyor"
            )
            return recommendation
        signal, confidence_score = to_trade_signal(decision_output)
        return recommendation.model_copy(update={"signal": signal, "confidence_score": confidence_score})

    def _apply_canonical_decision_to_investor_horizon(
        self, symbol: str, recommendation: InvestorRecommendation
    ) -> InvestorRecommendation:
        """Overrides ONLY `horizon_1_week`'s signal/confidence_score with
        the Decision Engine's statistical vote - `decision_engine.decide()`
        produces one undifferentiated-by-horizon decision, closest in
        meaning to a current-conditions (short-horizon) vote, so only the
        1-week horizon is overridden (see docs/superpowers/specs/2026-10-01-
        decision-path-consolidation-design.md's Global Constraints).
        `horizon_1_month`/`horizon_1_year`/`investor_commentary` stay
        fully LLM-driven - decision_engine has no medium/long-horizon
        concept to supersede them with (see claude_build_spec.md Phase 1's
        not-yet-built models/medium_horizon, models/long_horizon).

        A Decision Engine failure falls back to the LLM's own
        horizon_1_week signal rather than dropping the recommendation -
        same resilience shape as `_apply_canonical_decision` above,
        including the same low-data_sufficiency quality gate."""
        try:
            decision_engine = self.decision_engine
            if decision_engine is None:
                from decision_engine.service import get_default_decision_engine

                decision_engine = get_default_decision_engine()
            decision_output = decision_engine.decide(symbol, strict=True)
        except Exception as exc:
            logger.error(
                f"{symbol}: decision engine yetkisi (investor 1-hafta) uygulanamadi, LLM sinyali korunuyor: {exc}"
            )
            return recommendation
        if not is_data_sufficient(decision_output):
            logger.warning(
                f"{symbol}: decision engine data_sufficiency={decision_output.data_sufficiency:.2f} "
                "yetersiz (investor 1-hafta, quality gate), LLM sinyali korunuyor"
            )
            return recommendation
        signal, confidence_score = to_trade_signal(decision_output)
        updated_horizon = recommendation.horizon_1_week.model_copy(
            update={"signal": signal, "confidence_score": confidence_score}
        )
        return recommendation.model_copy(update={"horizon_1_week": updated_horizon})

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
