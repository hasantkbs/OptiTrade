"""
OptiTrade — Trading Signals API Endpoint'leri
================================================
Mobil uygulamanın (Flutter/React Native) ``HybridTradingEngine`` çıktısını
tükettiği REST katmanı.

NOT: Bu dosyada bilerek ``from __future__ import annotations`` KULLANILMIYOR.
slowapi'nin ``@limiter.limit()`` dekoratörü fonksiyonu sardığında, sarmalanan
fonksiyonun ``__globals__``'ı slowapi'nin kendi modülüne işaret ediyor;
ertelenmiş (string) tip anotasyonları açıksa FastAPI/Pydantic bu isimleri
(ör. ``SignalsAnalyzeRequest``) o namespace'te bulamayıp
``PydanticUndefinedAnnotation`` hatası veriyor. Anotasyonlar burada eager
(anında) değerlendirildiği için bu sorun oluşmuyor.
"""
from functools import lru_cache
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from core.ai_trader_persona import TradeRecommendation
from core.hybrid_engine import HybridTradingEngine
from core.rate_limiter import limiter

router = APIRouter(prefix="/signals", tags=["Trading Signals"])


class SignalsAnalyzeRequest(BaseModel):
    """``POST /analyze`` için istek gövdesi."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"symbols": ["BTC-USD", "AAPL", "THYAO.IS"]}}
    )

    symbols: List[str] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Analiz edilecek sembol listesi (yfinance formatında, ör. BIST için '.IS' soneki).",
    )


@lru_cache()
def get_engine() -> HybridTradingEngine:
    """Süreç genelinde tek bir ``HybridTradingEngine`` örneği (singleton).

    ``HybridTradingEngine`` kendi içinde sembol başına 15 dakikalık bir
    ``TradeRecommendation`` cache'i tutar. Her istekte yeni bir örnek
    oluşturmak bu cache'i sıfırlar ve asıl amacını (art arda gelen
    isteklerde LLM'i tekrar tekrar yormamak) boşa çıkarır. ``lru_cache()``
    parametresiz çağrıldığından her seferinde aynı örneği döner —
    FastAPI'de tekil (singleton) bağımlılık için standart örüntü.
    """
    return HybridTradingEngine()


@router.post(
    "/analyze",
    response_model=List[TradeRecommendation],
    summary="Sembol listesi için hibrit AI ticaret önerisi üret",
    description=(
        "Verilen sembolleri piyasa rejimi taramasından geçirir; geçerli "
        "olanlar için çoklu zaman dilimi teknik analiz ve ATR bazlı risk "
        "seviyeleri hesaplar, haber duygusuyla birlikte Groq LLM'e sunarak "
        "yapılandırılmış bir ticaret önerisi üretir.\n\n"
        "Son 15 dakika içinde aynı sembol için üretilmiş bir öneri varsa, "
        "LLM'e tekrar istek atılmadan doğrudan cache'ten döner.\n\n"
        "Piyasa rejimi filtresini geçemeyen veya veri sağlanamayan "
        "semboller yanıtta yer almaz — dönen liste istekteki sembol "
        "sayısından kısa olabilir."
    ),
    responses={
        404: {"description": "Hiçbir sembol için öneri üretilemedi."},
        422: {"description": "İstek gövdesi geçersiz (ör. boş sembol listesi)."},
    },
)
@limiter.limit("20/minute")
def analyze_signals(
    request: Request,
    body: SignalsAnalyzeRequest,
    engine: HybridTradingEngine = Depends(get_engine),
) -> List[TradeRecommendation]:
    recommendations = engine.run(body.symbols)
    if not recommendations:
        raise HTTPException(
            status_code=404,
            detail="Hiçbir sembol için öneri üretilemedi (piyasa rejimi filtresi, veri veya AI hatası).",
        )
    return recommendations
