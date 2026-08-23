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
from typing import List, Literal, Union

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from core.ai_trader_persona import TradeRecommendation
from core.hybrid_engine import HybridTradingEngine
from core.investor_persona import InvestorRecommendation
from core.market_anomaly_detector import MarketAlert
from core.rate_limiter import limiter

router = APIRouter(prefix="/signals", tags=["Trading Signals"])


class SignalsAnalyzeRequest(BaseModel):
    """``POST /analyze`` ve ``POST /alerts`` için ortak istek gövdesi."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"symbols": ["BTC-USD", "AAPL", "THYAO.IS"], "profile": "trader"}}
    )

    symbols: List[str] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Analiz edilecek sembol listesi (yfinance formatında, ör. BIST için '.IS' soneki).",
    )
    profile: Literal["trader", "investor"] = Field(
        default="trader",
        description=(
            "'trader': kısa vadeli AL/SAT önerisi (giriş/stop-loss/take-profit). "
            "'investor': 1 hafta / 1 ay / 1 yıl ufuklu, giriş/SL/TP içermeyen uzun "
            "vadeli görüş. Yalnızca /analyze tarafından kullanılır, /alerts bu alanı yok sayar."
        ),
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
    response_model=List[Union[TradeRecommendation, InvestorRecommendation]],
    summary="Sembol listesi için hibrit AI ticaret/yatırım önerisi üret",
    description=(
        "Verilen sembolleri piyasa rejimi taramasından geçirir; geçerli "
        "olanlar için çoklu zaman dilimi teknik analiz hesaplar, haber "
        "duygusuyla birlikte Groq LLM'e sunarak yapılandırılmış bir öneri "
        "üretir.\n\n"
        "``profile=\"trader\"`` (varsayılan): kısa vadeli AL/SAT önerisi, "
        "ATR bazlı risk seviyeleri (giriş/stop-loss/take-profit) ile "
        "birlikte.\n\n"
        "``profile=\"investor\"``: giriş/SL/TP içermeyen, 1 hafta / 1 ay / "
        "1 yıl ufuklarında ayrı AL/SAT/TUT yönü ve güven skoru içeren uzun "
        "vadeli görüş.\n\n"
        "Son 15 dakika içinde aynı sembol+profil için üretilmiş bir öneri "
        "varsa, LLM'e tekrar istek atılmadan doğrudan cache'ten döner.\n\n"
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
) -> List[Union[TradeRecommendation, InvestorRecommendation]]:
    recommendations = engine.run(body.symbols, profile=body.profile)
    if not recommendations:
        raise HTTPException(
            status_code=404,
            detail="Hiçbir sembol için öneri üretilemedi (piyasa rejimi filtresi, veri veya AI hatası).",
        )
    return recommendations


@router.post(
    "/alerts",
    response_model=List[MarketAlert],
    summary="Sembol listesi için ani piyasa değişikliği (fiyat/hacim/haber şoku) kontrolü",
    description=(
        "Verilen sembolleri piyasa rejimi filtresi UYGULANMADAN kontrol eder "
        "(CHOPPY bir sembolün ani hacim/fiyat şoku göstermesi rejim "
        "değişikliğinin habercisi olabilir). Fiyat/hacim şoku (anormal hacim "
        "veya ATR'ye göre büyük fiyat hareketi) veya yüksek etkili haber "
        "tespit edilen semboller döner.\n\n"
        "Hiçbir uyarı tespit edilmezse boş liste döner — bu normal ve "
        "beklenen bir sonuçtur, hata değildir (``/analyze``'ın aksine 404 "
        "dönmez)."
    ),
    responses={
        422: {"description": "İstek gövdesi geçersiz (ör. boş sembol listesi)."},
    },
)
@limiter.limit("20/minute")
def check_alerts(
    request: Request,
    body: SignalsAnalyzeRequest,
    engine: HybridTradingEngine = Depends(get_engine),
) -> List[MarketAlert]:
    return engine.check_alerts(body.symbols)
