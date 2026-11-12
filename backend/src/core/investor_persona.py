"""
OptiTrade — Investor Persona (Uzun Vadeli Yatırımcı Öneri Katmanı)
======================================================================
AITraderPersona'nın kısa vadeli ticaret odaklı yaklaşımından farklı olarak,
aynı teknik analiz + piyasa rejimi + haber duygusu verisini 1 hafta / 1 ay /
1 yıl ufuklarında ayrı ayrı AL/SAT/TUT yönü ve güven skoruna dönüştürür.
Giriş/Stop-Loss/Take-Profit üretmez — yatırım bir "trade" değildir.

Bu motorda temel analiz (bilanço, büyüme oranları vb.) veri kaynağı yoktur
(core/analyzer.py'daki ayrı FundamentalSignalEngine bu motora bağlanmamıştır)
— bu nedenle 1 yıllık görüş yalnızca piyasa rejimi sürekliliği ve makro haber
bağlamına dayanır. Bu sınırlılık, investor_commentary'ye LLM çıktısından
BAĞIMSIZ, kod tarafından eklenen sabit bir uyarı cümlesiyle her zaman
belirtilir.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

from groq import Groq
from pydantic import BaseModel, Field, ValidationError

from core.ai_trader_persona import TradeSignal
from core.no_trade import SignalSource
from core.regime_scanner import MarketRegime

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

_FUNDAMENTAL_DATA_DISCLAIMER = (
    " (Not: Bu görüş temel analiz -bilanço, büyüme oranları- verisi içermez; "
    "yalnızca piyasa rejimi ve haber bağlamına dayanır.)"
)

_SYSTEM_PROMPT = (
    "Sen deneyimli, uzun vadeli bir Value Investor / Portföy Yöneticisisin. "
    "Karar vermeden önce üç farklı ufuktan SIRAYLA düşün, sonra sentezle:\n\n"
    "1. ÖNCE 1 HAFTALIK ufku değerlendir: kısa vadeli teknik momentum "
    "(RSI, MACD histogramı, hacim) ve piyasa rejiminin (market_regime) bu "
    "hafta için ima ettiği yönü yorumla. horizon_1_week alanına yaz.\n\n"
    "2. SONRA 1 AYLIK ufku değerlendir: haftalık trend yönü (weekly_trend_up), "
    "EMA50/EMA200 kesişimi ve piyasa rejiminin kalıcılığını yorumla. "
    "horizon_1_month alanına yaz.\n\n"
    "3. EN SON 1 YILLIK ufku değerlendir: piyasa rejiminin sürekliliğini ve "
    "haber duygusunun (varsa news_sentiment) makro kategorisini "
    "(news_sentiment.news_category, özellikle MACRO/REGULATORY) yorumla. "
    "Temel analiz (bilanço/büyüme) verisi SANA SAĞLANMADI — bunu tahmin etme, "
    "yalnızca elindeki rejim ve haber verisine dayan. horizon_1_year alanına "
    "yaz.\n\n"
    "NOT: Her ufuk için bir AL/SAT/TUT kararı VE güven skoru VERMİYORSUN — "
    "bunlar senin görevin değil; ayrı, istatistiksel bir Karar Motoru "
    "tarafından (yalnızca 1 hafta ufku için) belirleniyor, 1 ay ve 1 yıl "
    "ufukları için ise henüz doğrulanmış bir model bulunmuyor ve bu "
    "ufuklar bilerek boş bırakılacak. Senin görevin SADECE her ufkun "
    "rationale (gerekçe) alanına, o ufka özgü verilere dayanan 1-2 "
    "cümlelik, dürüst bir Türkçe analiz yazmak — ufuklar arasında yapay "
    "bir tutarlılık zorlaması yapma, veriler gerçekten çelişkili bir "
    "görünüm veriyorsa bunu rationale'da açıkça belirt.\n\n"
    "investor_commentary alanına, üç ufku birlikte değerlendiren, deneyimli "
    "bir portföy yöneticisi üslubuyla 3-4 cümlelik bir sentez yaz.\n\n"
    "Cevabını MUTLAKA submit_investor_recommendation aracını çağırarak ver.\n\n"
    "Tüm metin alanları (rationale'lar ve investor_commentary) BAŞTAN SONA "
    "SADECE Türkçe olmalı — İngilizce teknik etiketleri (ör. BULLISH, MIXED) "
    "olduğu gibi ALINTILAMA, anlamını Türkçeye çevirerek yaz."
)


class HorizonView(BaseModel):
    """Belirli bir zaman ufku için AL/SAT/TUT yönü, güven skoru ve gerekçe.

    Per CTO Remediation Plan Revision 4 (Finding F9, Section 5):
    `signal`/`confidence_score` are never set by `InvestorPersona`/the
    LLM for ANY horizon - absent from `_HORIZON_SCHEMA` below, and
    scrubbed to `None` unconditionally in `generate_recommendation()` as
    a structural backstop. `core.hybrid_engine` is the only writer of
    `horizon_1_week.signal`/`confidence_score` (from the canonical
    Decision Engine - the closest existing match to a current-conditions
    vote). `horizon_1_month`/`horizon_1_year` stay `None`/unavailable
    always: no validated horizon-specific model exists for them yet -
    see `InvestorRecommendation`'s own docstring. `rationale` remains
    LLM-authored narrative context throughout - explicitly non-
    authoritative, never a substitute for a validated decision.
    """

    signal: Optional[TradeSignal] = None
    confidence_score: Optional[int] = Field(None, ge=0, le=100)
    rationale: str = Field(..., description="1-2 cümlelik Türkçe gerekçe")
    # Set ONLY by core.hybrid_engine, for horizon_1_week, when the
    # canonical Decision Engine supplies a direction. None for
    # horizon_1_month/horizon_1_year (never set) and for horizon_1_week
    # before the orchestrator attaches it.
    signal_source: Optional[SignalSource] = None


class InvestorRecommendation(BaseModel):
    """InvestorPersona'nın ürettiği ufuk-bazlı yapılandırılmış yatırım önerisi.

    `horizon_1_month`/`horizon_1_year` are structurally unvalidated
    (Finding F9): no trained model exists for either horizon today, so
    their `signal`/`confidence_score` are always `None` - the LLM's own
    narrative `rationale` is the only content they ever carry, and this
    plan does not claim it is a validated decision. `horizon_1_week` is
    the one horizon the canonical Decision Engine actually backs today
    (by convention - decision_engine has no real per-horizon concept of
    its own); this is an existing compatibility behavior this class
    preserves, not a claim that `decision_engine` is itself a validated
    1-week model."""

    symbol: str
    market_regime: str
    horizon_1_week: HorizonView
    horizon_1_month: HorizonView
    horizon_1_year: HorizonView
    investor_commentary: str = Field(
        ...,
        description="Üç ufku birlikte değerlendiren 3-4 cümlelik Türkçe sentez.",
    )


# Finding F9 fix (CTO Remediation Plan Revision 4): signal/confidence_score
# are deliberately ABSENT from every horizon's schema - the LLM never
# produces a final AL/SAT/TUT decision or confidence for ANY horizon
# (not even 1-week); `core.hybrid_engine` is the sole writer of
# horizon_1_week's signal/confidence_score, from the canonical Decision
# Engine. `rationale` is the only field the LLM supplies per horizon.
_TOOL_NAME = "submit_investor_recommendation"
_HORIZON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "rationale": {"type": "string"},
    },
    "required": ["rationale"],
    "additionalProperties": False,
}
_RECOMMENDATION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
        "market_regime": {"type": "string"},
        "horizon_1_week": _HORIZON_SCHEMA,
        "horizon_1_month": _HORIZON_SCHEMA,
        "horizon_1_year": _HORIZON_SCHEMA,
        "investor_commentary": {"type": "string"},
    },
    "required": [
        "symbol", "market_regime",
        "horizon_1_week", "horizon_1_month", "horizon_1_year",
        "investor_commentary",
    ],
    "additionalProperties": False,
}

# Scrubbed unconditionally on every parsed horizon, for the same reason
# ai_trader_persona._LLM_FORBIDDEN_FIELDS exists: `additionalProperties:
# False` above is not a guarantee a provider actually honors it.
_LLM_FORBIDDEN_HORIZON_FIELDS = {"signal": None, "confidence_score": None, "signal_source": None}


class InvestorPersona:
    """Teknik + rejim + (opsiyonel) haber verisini LLM'e sunup ufuk-bazlı yatırım önerisi üreten katman."""

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL) -> None:
        self._client = Groq(api_key=api_key) if api_key else Groq()
        self._model = model

    def generate_recommendation(
        self,
        symbol: str,
        market_regime: MarketRegime,
        analysis: Dict[str, Any],
        news_sentiment: Optional[Dict[str, Any]] = None,
    ) -> InvestorRecommendation:
        """Verilen tüm sinyalleri LLM'e sunup yapılandırılmış bir InvestorRecommendation döner."""
        prompt = self._build_prompt(symbol, market_regime, analysis, news_sentiment)

        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=1536,
            temperature=0.3,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": _TOOL_NAME,
                        "description": "Yapılandırılmış yatırım önerisini gönderir.",
                        "parameters": _RECOMMENDATION_SCHEMA,
                    },
                }
            ],
            tool_choice={"type": "function", "function": {"name": _TOOL_NAME}},
        )

        tool_calls = response.choices[0].message.tool_calls
        if not tool_calls:
            raise RuntimeError(f"{symbol}: Groq yapılandırılmış çıktı üretemedi (tool_calls boş)")

        try:
            arguments = json.loads(tool_calls[0].function.arguments)
            recommendation = InvestorRecommendation.model_validate(arguments)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise RuntimeError(f"{symbol}: Groq çıktısı beklenen şemaya uymuyor: {exc}") from exc

        # Finding F9 structural fix: scrub signal/confidence_score on
        # every horizon unconditionally, even though _HORIZON_SCHEMA
        # never asks the LLM for them - see HorizonView's docstring and
        # _LLM_FORBIDDEN_HORIZON_FIELDS above.
        recommendation = recommendation.model_copy(update={
            "horizon_1_week": recommendation.horizon_1_week.model_copy(update=_LLM_FORBIDDEN_HORIZON_FIELDS),
            "horizon_1_month": recommendation.horizon_1_month.model_copy(update=_LLM_FORBIDDEN_HORIZON_FIELDS),
            "horizon_1_year": recommendation.horizon_1_year.model_copy(update=_LLM_FORBIDDEN_HORIZON_FIELDS),
        })
        recommendation.investor_commentary += _FUNDAMENTAL_DATA_DISCLAIMER
        return recommendation

    @staticmethod
    def _build_prompt(
        symbol: str,
        market_regime: MarketRegime,
        analysis: Dict[str, Any],
        news_sentiment: Optional[Dict[str, Any]],
    ) -> str:
        payload = {
            "symbol": symbol,
            "market_regime": market_regime.value,
            "technical_analysis": analysis,
            "news_sentiment": news_sentiment or "Veri sağlanmadı",
        }
        return (
            "Aşağıdaki verilere dayanarak bu sembol için 1 hafta / 1 ay / 1 yıl "
            "ufuklarında ayrı rationale (gerekçe) metinleri üret:\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}\n\n"
            "Her ufkun rationale'ını, o ufka uygun veriye (kısa vade için "
            "mikro sinyaller, uzun vade için rejim/haber) dayandır — "
            "ufuklar arasında yapay bir tutarlılık zorlaması yapma."
        )
