"""
OptiTrade — AI Trader Persona (Hibrit Öneri ve LLM Yorum Katmanı)
====================================================================
Piyasa rejimi, teknik analiz, risk seviyeleri ve (opsiyonel) haber
duygusunu Groq'un (ücretsiz katman) OpenAI-uyumlu Chat Completions
API'sine sunup, zorlanmış tool-calling ile yapılandırılmış (Pydantic)
bir ticaret önerisi üretir.

Model, karar vermeden önce iki ayrı uzman perspektifinden (kısa vadeli
Teknik Trader + uzun vadeli Makro Yatırımcı) ardışık olarak akıl yürütür,
ardından bir CIO (Chief Investment Officer) şapkasıyla bu iki görüşü
sentezleyip nihai kararı verir. Bu "iki uzman + sentez" sırası, hem
``TradeRecommendation``'daki alan sırasına hem de tool şemasındaki
``properties``/``required`` sırasına bilerek yansıtılmıştır — zorlanmış
JSON tool-calling'de argümanlar genelde şema sırasına yakın üretildiği
için bu, modelin nihai yoruma (``trader_commentary``) atlamadan önce
gerçekten "düşünmesini" teşvik eder.
"""
from __future__ import annotations

import json
import logging
import os
from enum import Enum
from typing import Any, Dict, Optional

from groq import Groq
from pydantic import BaseModel, Field, ValidationError

from core.regime_scanner import MarketRegime
from core.risk_manager import RiskLevels

logger = logging.getLogger(__name__)

# Groq ücretsiz katmanında kullanılabilir modeller zamanla değişebilir —
# güncel liste için https://console.groq.com/docs/models
DEFAULT_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

_SYSTEM_PROMPT = (
    "Sen profesyonel, risk yönetimini her şeyin üstünde tutan bir Wall Street "
    "kantitatif fon yönetim ekibisin. Karar vermeden önce iki farklı uzman "
    "gibi SIRAYLA düşün, sonra sentezle:\n\n"
    "1. ÖNCE bir Teknik Trader (Day/Swing Trader) ol: kısa vadeli (1H/1D) "
    "momentumu, RSI, MACD histogramını, hacim patlamasını, Bollinger squeeze "
    "durumunu ve ATR bazlı kırılımları yorumla. Ayrıca "
    "technical_analysis.patterns.active_patterns içindeki mum "
    "formasyonlarını ve support_proximity_pct / resistance_proximity_pct "
    "(Destek/Direnç yüzdesel yakınlığı) alanlarını MUTLAKA değerlendir — "
    "bir formasyon varsa ismiyle an, ör: \"Grafikte oluşan Hammer "
    "formasyonu ve desteğe %1.2 yakınlığımız, kısa vadeli bir tepki "
    "yükselişine işaret ediyor.\". active_patterns boşsa bunu da belirt "
    "(\"belirgin bir formasyon yok\"). Bu analizi trader_analysis alanına "
    "yaz.\n\n"
    "2. SONRA bir Makro Yatırımcı (Value Investor) ol: haftalık (1W) trendi, "
    "piyasa rejimini (market_regime) ve haber duygusunu (varsa "
    "news_sentiment) yorumla. news_sentiment.news_category "
    "(MACRO/EARNINGS/REGULATORY/PARTNERSHIP/GENERAL) ve "
    "news_sentiment.impact_level (HIGH/MEDIUM/LOW) alanlarını MUTLAKA "
    "değerlendir, ör: \"Gelen bilanço (EARNINGS) haberlerinin YÜKSEK "
    "etkisi, kısa vadede oynaklığı artırabilir.\". Bu analizi "
    "investor_analysis alanına yaz.\n\n"
    "3. EN SON Risk Yöneticisi (CIO — Chief Investment Officer) şapkanı tak: "
    "yukarıdaki iki uzman görüşünü sentezle ve Risk/Ödül (R:R) oranını "
    "kontrol et. Teknik Trader ile Makro Yatırımcı birbiriyle çelişiyorsa "
    "VEYA Risk/Ödül oranı elverişsizse (is_valid=false, R:R < 2.0), sinyali "
    "ACIMASIZCA NEUTRAL'a çek ve confidence_score'u düşür — asla elindeki "
    "verilerle çelişen bir sinyal verme. Bu sentezi trader_commentary "
    "alanına yaz.\n\n"
    "Cevabını MUTLAKA submit_trade_recommendation aracını çağırarak ver.\n\n"
    "trader_analysis, investor_analysis ve trader_commentary alanlarının "
    "ÜÇÜ DE BAŞTAN SONA SADECE Türkçe olmalı — başka hiçbir dilden "
    "(İngilizce, Rusça vb.) tek bir kelime bile karıştırma. Girdi verisindeki "
    "İngilizce teknik etiketleri (ör. BULLISH, BEARISH, MIXED, "
    "SLIGHTLY_POSITIVE) olduğu gibi ALINTILAMA — anlamını Türkçeye çevirerek "
    "yaz (ör. \"BULLISH\" yerine \"yükseliş yönlü\", \"SLIGHTLY_POSITIVE\" "
    "yerine \"hafif olumlu\")."
)


class TradeSignal(str, Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    NEUTRAL = "NEUTRAL"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


class TradeRecommendation(BaseModel):
    """AITraderPersona'nın ürettiği yapılandırılmış nihai ticaret önerisi."""

    symbol: str
    market_regime: str
    trader_analysis: str = Field(
        ...,
        description=(
            "Teknik Trader bakış açısı: kısa vadeli (1H/1D) momentum, RSI, "
            "MACD histogramı, hacim ve ATR bazlı kırılımlar üzerine "
            "2-3 cümlelik Türkçe analiz."
        ),
    )
    investor_analysis: str = Field(
        ...,
        description=(
            "Makro Yatırımcı bakış açısı: haftalık (1W) trend, piyasa "
            "rejimi ve haber duygusu üzerine 2-3 cümlelik Türkçe analiz."
        ),
    )
    signal: TradeSignal
    confidence_score: int = Field(..., ge=0, le=100, description="0-100 arası AI güvenilirlik derecesi")
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    trader_commentary: str = Field(
        ...,
        description=(
            "CIO (Chief Investment Officer) sentezi: trader_analysis ve "
            "investor_analysis'i birleştirip Risk/Ödül oranını değerlendiren, "
            "deneyimli bir fon yöneticisi üslubuyla yazılmış 3-4 cümlelik "
            "Türkçe nihai yorum."
        ),
    )


# Groq'un OpenAI-uyumlu tool-calling arayüzü için elle tanımlanmış JSON şema.
# Pydantic'in otomatik model_json_schema()'sı yerine elle yazılmasının nedeni:
# enum $defs/$ref çözümlemesi bazı sağlayıcılarda tutarsız davranabiliyor —
# düz bir şema, modelin doğru argümanlarla çağırma ihtimalini artırıyor.
# Alan sırası bilerek "iki analiz → karar → sentez" akışını izliyor.
_TOOL_NAME = "submit_trade_recommendation"
_RECOMMENDATION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
        "market_regime": {"type": "string"},
        "trader_analysis": {
            "type": "string",
            "description": (
                "Teknik Trader bakış açısı: kısa vadeli (1H/1D) momentum, RSI, "
                "MACD histogramı, hacim ve ATR bazlı kırılımlar üzerine "
                "2-3 cümlelik Türkçe analiz."
            ),
        },
        "investor_analysis": {
            "type": "string",
            "description": (
                "Makro Yatırımcı bakış açısı: haftalık (1W) trend, piyasa "
                "rejimi ve haber duygusu üzerine 2-3 cümlelik Türkçe analiz."
            ),
        },
        "signal": {"type": "string", "enum": [s.value for s in TradeSignal]},
        "confidence_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "entry_price": {"type": "number"},
        "stop_loss": {"type": "number"},
        "take_profit_1": {"type": "number"},
        "take_profit_2": {"type": "number"},
        "trader_commentary": {
            "type": "string",
            "description": (
                "CIO sentezi: trader_analysis ve investor_analysis'i "
                "birleştiren 3-4 cümlelik Türkçe nihai yorum."
            ),
        },
    },
    "required": [
        "symbol",
        "market_regime",
        "trader_analysis",
        "investor_analysis",
        "signal",
        "confidence_score",
        "entry_price",
        "stop_loss",
        "take_profit_1",
        "take_profit_2",
        "trader_commentary",
    ],
    "additionalProperties": False,
}


class AITraderPersona:
    """Teknik + risk + (opsiyonel) haber verisini LLM'e sunup yapılandırılmış öneri üreten katman.

    Haber duygusu bu sınıf tarafından çekilmez — çağıran taraf isterse
    ``news_sentiment`` parametresiyle dışarıdan sağlar. Bu, sınıfı
    ``core/news_analyzer.py``'dan bağımsız ve izole test edilebilir tutar.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL) -> None:
        self._client = Groq(api_key=api_key) if api_key else Groq()
        self._model = model

    def generate_recommendation(
        self,
        symbol: str,
        market_regime: MarketRegime,
        analysis: Dict[str, Any],
        risk: RiskLevels,
        news_sentiment: Optional[Dict[str, Any]] = None,
    ) -> TradeRecommendation:
        """Verilen tüm sinyalleri LLM'e sunup yapılandırılmış bir ``TradeRecommendation`` döner."""
        prompt = self._build_prompt(symbol, market_regime, analysis, risk, news_sentiment)

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
                        "description": "Yapılandırılmış ticaret önerisini gönderir.",
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
            return TradeRecommendation.model_validate(arguments)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise RuntimeError(f"{symbol}: Groq çıktısı beklenen şemaya uymuyor: {exc}") from exc

    @staticmethod
    def _build_prompt(
        symbol: str,
        market_regime: MarketRegime,
        analysis: Dict[str, Any],
        risk: RiskLevels,
        news_sentiment: Optional[Dict[str, Any]],
    ) -> str:
        payload = {
            "symbol": symbol,
            "market_regime": market_regime.value,
            "technical_analysis": analysis,
            "risk_levels": risk.model_dump(),
            "news_sentiment": news_sentiment or "Veri sağlanmadı",
        }
        return (
            "Aşağıdaki verilere dayanarak bu sembol için bir ticaret önerisi üret:\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}\n\n"
            "entry_price, stop_loss, take_profit_1, take_profit_2 alanlarını "
            "risk_levels içindeki değerlerle birebir doldur. confidence_score'u "
            "teknik analizin piyasa rejimiyle uyumuna göre belirle; rejim ile "
            "teknik sinyaller çelişiyorsa güveni düşür. "
            "technical_analysis.patterns içindeki mum formasyonlarını ve "
            "news_sentiment.news_category / impact_level bilgisini "
            "analizlerinde mutlaka değerlendir."
        )
