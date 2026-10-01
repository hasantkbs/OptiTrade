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
    "Her ufuk için ayrı bir signal (STRONG_BUY/BUY/NEUTRAL/SELL/STRONG_SELL) "
    "ve confidence_score (0-100) belirle — ufuklar birbirinden FARKLI "
    "yönlerde olabilir (ör. 1 hafta SAT, 1 yıl AL), bu çelişki değil, "
    "gerçekçi bir durumdur; asla ufukları yapay olarak birbirine benzetme.\n\n"
    "investor_commentary alanına, üç ufku birlikte değerlendiren, deneyimli "
    "bir portföy yöneticisi üslubuyla 3-4 cümlelik bir sentez yaz.\n\n"
    "Cevabını MUTLAKA submit_investor_recommendation aracını çağırarak ver.\n\n"
    "Tüm metin alanları (rationale'lar ve investor_commentary) BAŞTAN SONA "
    "SADECE Türkçe olmalı — İngilizce teknik etiketleri (ör. BULLISH, MIXED) "
    "olduğu gibi ALINTILAMA, anlamını Türkçeye çevirerek yaz."
)


class HorizonView(BaseModel):
    """Belirli bir zaman ufku için AL/SAT/TUT yönü, güven skoru ve gerekçe."""

    signal: TradeSignal
    confidence_score: int = Field(..., ge=0, le=100)
    rationale: str = Field(..., description="1-2 cümlelik Türkçe gerekçe")


class InvestorRecommendation(BaseModel):
    """InvestorPersona'nın ürettiği ufuk-bazlı yapılandırılmış yatırım önerisi."""

    symbol: str
    market_regime: str
    horizon_1_week: HorizonView
    horizon_1_month: HorizonView
    horizon_1_year: HorizonView
    investor_commentary: str = Field(
        ...,
        description="Üç ufku birlikte değerlendiren 3-4 cümlelik Türkçe sentez.",
    )


_TOOL_NAME = "submit_investor_recommendation"
_HORIZON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "signal": {"type": "string", "enum": [s.value for s in TradeSignal]},
        "confidence_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "rationale": {"type": "string"},
    },
    "required": ["signal", "confidence_score", "rationale"],
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
            "ufuklarında ayrı yatırım önerileri üret:\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}\n\n"
            "Her ufkun signal ve confidence_score'unu, o ufka uygun veriye "
            "(kısa vade için mikro sinyaller, uzun vade için rejim/haber) "
            "dayandır — ufuklar arasında yapay bir tutarlılık zorlaması yapma."
        )
