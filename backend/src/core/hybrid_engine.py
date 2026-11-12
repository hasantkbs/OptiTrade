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

from core.ai_trader_persona import AITraderPersona, TradeRecommendation, TradeSignal
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
from core.no_trade import NoTradeOutcome, NoTradeReason
from core.regime_scanner import MarketRegimeScanner, ScannedSymbol
from core.risk_manager import DynamicRiskManager, RiskLevels
from core.structured_logging import STATUS_SKIPPED, log_event
from decision_engine.exceptions import NoValidVotesError

logger = logging.getLogger(__name__)

DEFAULT_RECOMMENDATION_CACHE_TTL_SECONDS = 15 * 60  # 15 dakika
DEFAULT_ALERT_CACHE_TTL_SECONDS = 2 * 60  # 2 dakika

# TTLCache.get() süresi dolmuş/hiç yazılmamış bir anahtar için de None döner;
# "kontrol edildi, uyarı yok" durumunu bundan ayırt etmek için sentinel.
_NO_ALERT = object()

_LONG_SIGNALS = (TradeSignal.BUY, TradeSignal.STRONG_BUY)


def _direction_consistent_risk_levels(
    signal: TradeSignal, risk: RiskLevels
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """`DynamicRiskManager.calculate()` (core/risk_manager.py) only ever
    computes long-side geometry (`stop_loss = entry - k*ATR`,
    `take_profit = entry + k*ATR`) - correct for BUY/STRONG_BUY, but
    structurally wrong for SELL/STRONG_SELL (where a real short position
    would need the mirror-image levels) and meaningless for NEUTRAL (no
    position at all). Finding 8's risk-geometry issue (CTO Remediation
    Plan Revision 4 Section 10.6) was exactly a SELL override shipping
    with these long-side levels attached as if they were its own. Per
    that section's explicit instruction, this omits the levels (`None`)
    rather than inventing short-side geometry `DynamicRiskManager` does
    not implement - a full risk-manager rewrite is out of scope for this
    task."""
    if signal in _LONG_SIGNALS:
        return risk.stop_loss, risk.take_profit_1, risk.take_profit_2
    return None, None, None


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
                narrative = self.ai_persona.generate_recommendation(
                    symbol=symbol,
                    market_regime=scanned.regime,
                    analysis=analysis,
                    risk=risk,
                    news_sentiment=news_sentiment,
                )
                outcome: Union[TradeRecommendation, InvestorRecommendation, NoTradeOutcome] = (
                    self._apply_canonical_decision(symbol, narrative, risk)
                )
            else:
                narrative = self.investor_persona.generate_recommendation(
                    symbol=symbol,
                    market_regime=scanned.regime,
                    analysis=analysis,
                    news_sentiment=news_sentiment,
                )
                outcome = self._apply_canonical_decision_to_investor_horizon(symbol, narrative)

            if isinstance(outcome, NoTradeOutcome):
                self._record_no_trade(outcome, profile)
                return None

            cache.set(symbol, outcome)
            return outcome
        except Exception as exc:
            logger.error(f"{symbol}: hibrit motor hatası ({profile}): {exc}")
            return None

    def _apply_canonical_decision(
        self, symbol: str, narrative: TradeRecommendation, risk: RiskLevels
    ) -> Union[TradeRecommendation, NoTradeOutcome]:
        """Assembles the final `TradeRecommendation` entirely from the
        Decision Engine's statistical vote and `risk_manager`'s levels -
        per CTO Remediation Plan Revision 4 (Finding F8): the canonical
        Decision Engine is the ONLY authority for the final signal;
        `narrative` (AITraderPersona's output) contributes only
        `trader_analysis`/`investor_analysis`/`trader_commentary` - its
        own `signal`/`confidence_score`/`entry_price`/`stop_loss`/
        `take_profit_*` are always `None` already (scrubbed in
        `AITraderPersona.generate_recommendation`) and are never read
        here.

        A Decision Engine exception, zero valid votes, or insufficient
        data (`analysis_presentation.is_data_sufficient()` - same
        quality gate `intelligence/opportunity.py:60` uses) no longer
        falls back to any LLM-authored signal - that fallback was itself
        the vulnerability Finding F8 identified (the two paths where the
        override used to be skipped). Each produces an explicit
        `NoTradeOutcome` with the matching `NoTradeReason` instead; the
        caller (`_process_symbol`) drops the symbol from the response
        and records the outcome as a diagnostic event - see
        `core.no_trade` and docs/architecture/CTO_REMEDIATION_PLAN.md
        Section 5."""
        try:
            decision_engine = self.decision_engine
            if decision_engine is None:
                from decision_engine.service import get_default_decision_engine

                decision_engine = get_default_decision_engine()
            decision_output = decision_engine.decide(symbol, strict=True)
        except NoValidVotesError as exc:
            logger.error(f"{symbol}: decision engine icin gecerli oy yok, NO_TRADE: {exc}")
            return NoTradeOutcome(symbol=symbol, reason=NoTradeReason.NO_VALID_ENGINE_VOTES)
        except Exception as exc:
            logger.error(f"{symbol}: decision engine kullanilamiyor, NO_TRADE: {exc}")
            return NoTradeOutcome(symbol=symbol, reason=NoTradeReason.DECISION_ENGINE_UNAVAILABLE)
        if not is_data_sufficient(decision_output):
            logger.warning(
                f"{symbol}: decision engine data_sufficiency={decision_output.data_sufficiency:.2f} "
                "yetersiz (quality gate), NO_TRADE"
            )
            return NoTradeOutcome(symbol=symbol, reason=NoTradeReason.INSUFFICIENT_DATA)

        signal, confidence_score = to_trade_signal(decision_output)
        stop_loss, take_profit_1, take_profit_2 = _direction_consistent_risk_levels(signal, risk)
        return narrative.model_copy(
            update={
                "signal": signal,
                "confidence_score": confidence_score,
                "entry_price": risk.entry_price,
                "stop_loss": stop_loss,
                "take_profit_1": take_profit_1,
                "take_profit_2": take_profit_2,
                "signal_source": "decision_engine",
            }
        )

    def _apply_canonical_decision_to_investor_horizon(
        self, symbol: str, narrative: InvestorRecommendation
    ) -> Union[InvestorRecommendation, NoTradeOutcome]:
        """Assembles `horizon_1_week`'s signal/confidence_score entirely
        from the Decision Engine's statistical vote -
        `decision_engine.decide()` produces one undifferentiated-by-
        horizon decision, closest in meaning to a current-conditions
        (short-horizon) vote, so only the 1-week horizon is ever
        populated this way (see docs/superpowers/specs/2026-10-01-
        decision-path-consolidation-design.md's Global Constraints).
        `horizon_1_month`/`horizon_1_year` stay `None`/unavailable
        always (Finding F9) - `InvestorPersona` never sets them (see
        its own docstrings) and nothing here ever does either.

        A Decision Engine exception, zero valid votes, or insufficient
        data no longer falls back to the LLM's own (nonexistent, per
        Finding F9) horizon_1_week signal - the entire recommendation
        becomes an explicit `NoTradeOutcome` instead, with the same
        three reason codes `_apply_canonical_decision` uses. There is no
        partial shape in this plan for "this one horizon within this
        response is NO_TRADE while the others are fine" - the whole
        symbol is dropped, exactly as the trader profile does."""
        try:
            decision_engine = self.decision_engine
            if decision_engine is None:
                from decision_engine.service import get_default_decision_engine

                decision_engine = get_default_decision_engine()
            decision_output = decision_engine.decide(symbol, strict=True)
        except NoValidVotesError as exc:
            logger.error(f"{symbol}: decision engine icin gecerli oy yok (investor 1-hafta), NO_TRADE: {exc}")
            return NoTradeOutcome(symbol=symbol, reason=NoTradeReason.NO_VALID_ENGINE_VOTES)
        except Exception as exc:
            logger.error(f"{symbol}: decision engine kullanilamiyor (investor 1-hafta), NO_TRADE: {exc}")
            return NoTradeOutcome(symbol=symbol, reason=NoTradeReason.DECISION_ENGINE_UNAVAILABLE)
        if not is_data_sufficient(decision_output):
            logger.warning(
                f"{symbol}: decision engine data_sufficiency={decision_output.data_sufficiency:.2f} "
                "yetersiz (investor 1-hafta, quality gate), NO_TRADE"
            )
            return NoTradeOutcome(symbol=symbol, reason=NoTradeReason.INSUFFICIENT_DATA)

        signal, confidence_score = to_trade_signal(decision_output)
        updated_horizon = narrative.horizon_1_week.model_copy(
            update={"signal": signal, "confidence_score": confidence_score, "signal_source": "decision_engine"}
        )
        return narrative.model_copy(update={"horizon_1_week": updated_horizon})

    @staticmethod
    def _record_no_trade(outcome: NoTradeOutcome, profile: str) -> None:
        """Logs the NO_TRADE reason as a structured diagnostic event
        (never user-facing narrative - see `core.structured_logging`'s
        own module docstring on why). Deliberately does NOT cache the
        outcome under any TTL (`_process_symbol` returns before reaching
        either `cache.set()` call) - a transient Decision Engine failure
        must not leave a stale NO_TRADE result served for the
        recommendation cache's full 15-minute TTL (CTO Remediation Plan
        Revision 4 Section 5.2)."""
        log_event(
            logger,
            component="hybrid_engine",
            module="core.hybrid_engine",
            operation="no_trade",
            status=STATUS_SKIPPED,
            symbol=outcome.symbol,
            profile=profile,
            reason=outcome.reason.value,
        )

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
