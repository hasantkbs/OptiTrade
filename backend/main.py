from fastapi import FastAPI, HTTPException, Query, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from typing import Any, Dict, List, Optional
import logging
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

load_dotenv()  # backend/.env varsa (ör. GROQ_API_KEY) burada yüklenir

from models.schemas import (
    AnalysisRequest, AnalysisResult, ScanRequest, ScanResult,
    ChartResponse, ChartPoint,
    EnhancedAnalysisRequest, MonteCarloResult, RecommendationResult,
    PortfolioOptRequest, PortfolioOptResult,
    SessionInfo,
)
from core.analyzer import analyze
from core.ml_predictor import get_model_info
from core.monitoring import init_db, log_prediction, validate_predictions, get_performance_stats
from research.ml_trainer import train as train_model
from core.advanced_analysis import run_monte_carlo, optimize_portfolio, compute_recommendation
from core.session_analysis import compute_session_score, get_current_session, SESSIONS
from core.news_analyzer import get_news_summary, analyze_news
from core.sector_intelligence import (
    analyze_sector, get_sector_overview,
    sector_overview_to_dict, sector_detail_to_dict,
    SECTOR_DEFINITIONS,
)
from data.fetcher import fetch_history
from v2.api.router import router as v2_router
from api.v1.router import api_v1_router
from core.rate_limiter import limiter
from pipeline import PipelineResponse, PipelineService, QuantAnalysisRequest
from model_serving import MLPredictionRequest, MLPredictionResult, ServingHealthReport
from model_serving.exceptions import ModelServingError, NoActiveModelError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Firebase Admin ─────────────────────────────────────────────────────────────
_firebase_app = None
try:
    import firebase_admin
    from firebase_admin import credentials, auth as fb_auth

    _cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "firebase-credentials.json")
    if os.path.exists(_cred_path):
        cred = credentials.Certificate(_cred_path)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK baslatildi.")
    else:
        logger.warning("Firebase credentials bulunamadi. Auth devre disi.")
except ImportError:
    logger.warning("firebase-admin paketi kurulu degil. Auth devre disi.")

# ── Rate Limiter (bkz. core/rate_limiter.py — api/ router'larıyla paylaşılır) ───

# ── FastAPI App ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="OptiTrade API",
    description="Hisse senedi ve kripto analiz motoru — v3.1",
    version="3.1.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS (production-ready) ────────────────────────────────────────────────────
ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://localhost:3000",
    "https://optitrade-fcda9.web.app",
    "https://optitrade-fcda9.firebaseapp.com",
]
_cors_origins = os.getenv("ALLOWED_ORIGINS", "").split(",")
ALLOWED_ORIGINS += [o.strip() for o in _cors_origins if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(v2_router)
app.include_router(api_v1_router)

# ── Background Tasks ──────────────────────────────────────────────────────────

async def self_evolution_loop() -> None:
    """Günlük doğrulama ve haftalık eğitim yapan arka plan döngüsü."""
    while True:
        try:
            logger.info("Kendi kendini geliştirme döngüsü çalışıyor...")
            # 1. Tahminleri doğrula
            validated = validate_predictions()
            if validated > 0:
                logger.info(f"{validated} tahmin doğrulandı.")
            
            # 2. Haftalık eğitimi kontrol et (Her Pazar gecesi gibi basit bir mantık veya her 7 günde bir)
            # Şimdilik basitçe her gün bir kez kontrol edip haftalık tetikleme yapabiliriz
            # Ya da doğrudan her gün eğitimi yenileyebiliriz (veri seti küçükse)
            # Kullanıcının isteği üzerine günlük ve haftalık test/eğitim:
            train_model()
            logger.info("Model güncel verilerle yeniden eğitildi.")
            
        except Exception as e:
            logger.error(f"Self-evolution döngüsünde hata: {e}")
        
        # 24 saat bekle (86400 saniye)
        await asyncio.sleep(86400)

@app.on_event("startup")
async def startup_event() -> None:
    init_db()
    global _pipeline_service
    try:
        _pipeline_service = PipelineService()
    except Exception as e:
        logger.error(f"Quant pipeline baslatilamadi: {e}")
    asyncio.create_task(self_evolution_loop())

@app.get("/ml/performance")
def get_ml_performance(days: int = 30) -> Dict[str, Any]:
    return get_performance_stats(days=days)

# ── Symbol Lists ───────────────────────────────────────────────────────────────
BIST_SYMBOLS = [
    "THYAO.IS", "GARAN.IS", "ASELS.IS", "KCHOL.IS", "SISE.IS",
    "EREGL.IS", "BIMAS.IS", "AKBNK.IS", "YKBNK.IS", "TUPRS.IS",
    "TOASO.IS", "FROTO.IS", "SAHOL.IS", "PGSUS.IS", "TAVHL.IS",
]
CRYPTO_SYMBOLS = [
    "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "AVAX-USD",
    "XRP-USD", "ADA-USD", "DOT-USD", "LINK-USD", "DOGE-USD",
]
BUY_CODES  = {"STRONG_BUY", "BUY"}
SELL_CODES = {"STRONG_SELL", "SELL"}

# Thread pool for parallel yfinance calls
_executor = ThreadPoolExecutor(max_workers=16)

# Quant Research Platform pipeline — constructed once at startup (see
# startup_event) and reused across every request; None until then.
_pipeline_service: Optional[PipelineService] = None

# ── Firebase Auth Dependency ───────────────────────────────────────────────────
async def verify_firebase_token(
    authorization: Optional[str] = Header(default=None)
) -> Optional[str]:
    if _firebase_app is None:
        return None
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Yetkilendirme tokeni eksik.")
    token = authorization.split(" ", 1)[1]
    try:
        decoded = fb_auth.verify_id_token(token, app=_firebase_app)
        return decoded["uid"]
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Gecersiz token: {e}")

# ── Helpers ────────────────────────────────────────────────────────────────────
def categorize(results: List[AnalysisResult]) -> ScanResult:
    top_buys = sorted(
        [r for r in results if r.decision_code in BUY_CODES],
        key=lambda x: x.score, reverse=True,
    )[:10]
    top_sells = sorted(
        [r for r in results if r.decision_code in SELL_CODES],
        key=lambda x: x.score,
    )[:10]
    neutral = [r for r in results if r.decision_code == "NEUTRAL"]
    return ScanResult(
        top_buys=top_buys, top_sells=top_sells,
        neutral=neutral, total_scanned=len(results),
    )

def _enrich_result(result: AnalysisResult, mc_data: Optional[Dict[str, Any]]) -> AnalysisResult:
    mc_model = None
    if mc_data and mc_data.get("n_simulations", 0) > 0:
        mc_model = MonteCarloResult(**mc_data)
    # Chart AI entegrasyonu (model varsa)
    chart_ai_result = None
    try:
        from ml.chart_model import predict_chart_signal, is_model_available
        if is_model_available():
            import yfinance as yf
            hist_ai = yf.Ticker(result.symbol).history(period="3mo")
            if not hist_ai.empty:
                chart_ai_result = predict_chart_signal(hist_ai)
    except Exception:
        pass
    rec_data = compute_recommendation(
        score=result.score,
        ml_confidence=result.ml_confidence,
        monte_carlo=mc_data,
        risk_level=result.risk_level,
        chart_ai=chart_ai_result,
    )
    return result.model_copy(update={
        "monte_carlo":     mc_model,
        "recommendation":  RecommendationResult(**rec_data),
    })

def _analyze_safe(symbol: str, asset_type: str) -> Optional[AnalysisResult]:
    try:
        return analyze(symbol=symbol, asset_type=asset_type)
    except Exception as e:
        logger.warning(f"Analiz hatasi {symbol}: {e}")
        return None

async def _parallel_scan(symbols: List[str], asset_type: str) -> List[AnalysisResult]:
    """Tüm sembolleri ThreadPoolExecutor ile paralel analiz et."""
    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(_executor, _analyze_safe, sym, asset_type)
        for sym in symbols
    ]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]

# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/")
def root() -> Dict[str, str]:
    return {"status": "ok", "message": "OptiTrade API v3.2"}

@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "healthy"}

@app.get("/ml/status")
def ml_status() -> Dict[str, Any]:
    return get_model_info()

# ── News ──────────────────────────────────────────────────────────────────────

@app.get("/news/{symbol}")
@limiter.limit("20/minute")
def news_for_symbol(
    request: Request,
    symbol: str,
    market: str = "AUTO",   # TR | US | CRYPTO | AUTO
    uid: Optional[str] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """Sembol için haber duygu analizini döndür. market=TR|US|CRYPTO|AUTO"""
    return get_news_summary(symbol.upper(), market=market.upper())

@app.post("/news/sector")
@limiter.limit("10/minute")
def news_for_sector(
    request: Request,
    body: Dict[str, Any],
    uid: Optional[str] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """
    Piyasa/sektöre göre birden fazla sembol için haberler.
    Body: {"symbols": ["GARAN.IS","THYAO.IS"], "market": "TR"}
    """
    symbols: List[str] = body.get("symbols", [])[:10]
    market  = body.get("market", "AUTO").upper()
    if not symbols:
        raise HTTPException(status_code=400, detail="symbols listesi gerekli")

    results: List[Dict[str, Any]] = []
    for sym in symbols:
        try:
            summary = get_news_summary(sym.upper(), market=market)
            results.append(summary)
        except Exception as e:
            logger.warning(f"Haber hatası {sym}: {e}")

    if not results:
        raise HTTPException(status_code=404, detail="Haber alınamadı")

    avg_sentiment = sum(r["sentiment_score"] for r in results) / len(results)
    total_pos = sum(r["positive_count"] for r in results)
    total_neg = sum(r["negative_count"] for r in results)
    sector_label = (
        "POSITIVE"          if avg_sentiment >  0.3 else
        "SLIGHTLY_POSITIVE" if avg_sentiment >  0.05 else
        "SLIGHTLY_NEGATIVE" if avg_sentiment > -0.3 else
        "NEGATIVE"          if avg_sentiment <= -0.3 else
        "NEUTRAL"
    )
    return {
        "symbols":          symbols,
        "market":           market,
        "sector_sentiment": round(avg_sentiment, 4),
        "sector_label":     sector_label,
        "total_positive":   total_pos,
        "total_negative":   total_neg,
        "symbol_results":   results,
    }

@app.get("/market/watchlist/{market}")
def market_watchlist(
    market: str,
    uid: Optional[str] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """Piyasa için varsayılan izleme listesi döndür."""
    from core.market_config import get_default_watchlist, get_symbols_for_market, MARKETS
    market = market.upper()
    if market not in MARKETS:
        raise HTTPException(status_code=400, detail=f"Geçerli piyasalar: {list(MARKETS.keys())}")
    return {
        "market":    market,
        "info":      MARKETS[market],
        "watchlist": get_default_watchlist(market),
        "symbols":   get_symbols_for_market(market),
    }

@app.get("/market/list")
def market_list() -> Dict[str, Any]:
    """Desteklenen piyasaları listele."""
    from core.market_config import MARKETS
    return {"markets": MARKETS}

# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Sector Intelligence Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/sectors/overview")
@limiter.limit("6/minute")
def sectors_overview(
    request: Request,
    market: str = "US",   # TR | US
    uid: Optional[str] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """
    Piyasadaki tüm sektörleri fırsat skoruna göre sıralı döndür.
    Kullanıcıya hangi sektörde ilerleyeceğini söyler.
    """
    market = market.upper()
    if market not in ("TR", "US"):
        raise HTTPException(status_code=400, detail="market: TR veya US olmalı")
    results = get_sector_overview(market=market, use_cache=True)
    return {
        "market":  market,
        "sectors": sector_overview_to_dict(results),
        "top_opportunity": {
            "sector":    results[0].sector   if results else None,
            "name_tr":   results[0].name_tr  if results else None,
            "score":     results[0].opportunity_score if results else None,
            "trend":     results[0].trend    if results else None,
            "advice":    results[0].advice   if results else None,
        } if results else None,
    }


@app.get("/sectors/{sector_key}")
@limiter.limit("10/minute")
def sector_detail(
    request: Request,
    sector_key: str,
    market: str = "US",
    uid: Optional[str] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """
    Belirli bir sektörün detaylı analizi — tüm semboller + fırsat tavsiyesi.
    """
    sector_key = sector_key.upper()
    market     = market.upper()
    if sector_key not in SECTOR_DEFINITIONS:
        raise HTTPException(
            status_code=404,
            detail=f"Bilinmeyen sektör. Geçerliler: {list(SECTOR_DEFINITIONS.keys())}"
        )
    result = analyze_sector(sector_key, market=market, use_cache=True)
    return sector_detail_to_dict(result)


@app.get("/sectors/list/all")
def sectors_list() -> Dict[str, Any]:
    """Tanımlı tüm sektörlerin listesini döndür."""
    return {
        "sectors": [
            {
                "key":         k,
                "name_tr":     v["name_tr"],
                "icon":        v.get("icon", "📊"),
                "description": v.get("description", ""),
                "risk":        v.get("risk", "MEDIUM"),
                "has_tr":      bool(v.get("tr_symbols")),
                "has_us":      bool(v.get("us_symbols")),
            }
            for k, v in SECTOR_DEFINITIONS.items()
        ]
    }

@app.post("/user/preferences")
@limiter.limit("30/minute")
def save_user_preferences(
    request: Request,
    body: Dict[str, Any],
    uid: Optional[str] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """
    Kullanıcı piyasa tercihini Firebase'e kaydet.
    Body: {"market": "TR", "uid": "..."}
    """
    user_uid = uid or body.get("uid")
    if not user_uid:
        raise HTTPException(status_code=401, detail="UID gerekli")
    market = body.get("market", "US").upper()
    from core.market_config import MARKETS
    if market not in MARKETS:
        raise HTTPException(status_code=400, detail=f"Geçersiz piyasa: {market}")
    try:
        from firebase_admin import firestore
        db = firestore.client()
        db.collection("users").document(user_uid).set(
            {"preferences": {"market": market, "updatedAt": firestore.SERVER_TIMESTAMP}},
            merge=True,
        )
        return {"status": "ok", "market": market}
    except Exception as e:
        logger.warning(f"Firebase preferences yazılamadı: {e}")
        return {"status": "ok", "market": market, "warning": "Firebase kayıt başarısız"}

# ── Session ────────────────────────────────────────────────────────────────────

@app.get("/session/info", response_model=SessionInfo)
@limiter.limit("60/minute")
def session_info(request: Request) -> SessionInfo:
    data = compute_session_score(
        rsi=50, macd=0, macd_signal_val=0,
        macd_hist=0, volume_ratio=1.0, base_score=50,
    )
    return SessionInfo(**data)

@app.get("/session/all")
def all_sessions() -> List[Dict[str, Any]]:
    return [
        {
            "code": s.code, "name": s.name,
            "start": s.start.strftime("%H:%M"),
            "end": s.end.strftime("%H:%M"),
            "volatility_mult": s.volatility_mult,
            "description": s.description,
            "currencies": s.currencies,
        }
        for s in SESSIONS
    ]

@app.post("/session/analyze", response_model=SessionInfo)
@limiter.limit("30/minute")
def session_analyze(request: Request, body: AnalysisRequest,
                    uid: Optional[str] = Depends(verify_firebase_token)) -> SessionInfo:
    result = analyze(symbol=body.symbol, potential_price=body.potential_price,
                     asset_type=body.asset_type)
    if result is None:
        raise HTTPException(status_code=404, detail=f"{body.symbol} icin veri bulunamadi.")
    ind = result.indicators
    data = compute_session_score(
        rsi=ind.rsi, macd=ind.macd, macd_signal_val=ind.macd_signal,
        macd_hist=ind.macd_histogram, volume_ratio=ind.volume_ratio,
        base_score=result.score,
    )
    return SessionInfo(**data)

# ── Price ──────────────────────────────────────────────────────────────────────

@app.get("/price/{symbol}")
@limiter.limit("60/minute")
def get_current_price(request: Request, symbol: str) -> Dict[str, Any]:
    hist = fetch_history(symbol.upper(), period="5d")
    if hist is None or hist.empty:
        raise HTTPException(status_code=404, detail=f"{symbol} fiyati bulunamadi.")
    current = float(hist["Close"].iloc[-1])
    prev    = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
    change_pct = ((current - prev) / prev) * 100 if prev > 0 else 0.0
    return {
        "symbol": symbol.upper(),
        "price": round(current, 4),
        "change_pct": round(change_pct, 2),
        "timestamp": hist.index[-1].isoformat(),
    }

# ── Analyze ────────────────────────────────────────────────────────────────────

@app.post("/analyze", response_model=AnalysisResult)
@limiter.limit("30/minute")
def analyze_symbol(request: Request, body: AnalysisRequest,
                   uid: Optional[str] = Depends(verify_firebase_token)) -> AnalysisResult:
    result = analyze(symbol=body.symbol, potential_price=body.potential_price,
                     asset_type=body.asset_type)
    if result is None:
        raise HTTPException(status_code=404, detail=f"{body.symbol} icin veri bulunamadi.")
    rec_data = compute_recommendation(
        score=result.score, ml_confidence=result.ml_confidence,
        monte_carlo=None, risk_level=result.risk_level,
    )
    return result.model_copy(update={"recommendation": RecommendationResult(**rec_data)})

@app.post("/analyze/enhanced", response_model=AnalysisResult)
@limiter.limit("10/minute")
def analyze_enhanced(request: Request, body: EnhancedAnalysisRequest,
                     uid: Optional[str] = Depends(verify_firebase_token)) -> AnalysisResult:

    # Trader check (Basitleştirilmiş mantık - Firebase'den çekilebilir)
    is_trader: bool = False
    if uid:
        try:
            from firebase_admin import firestore
            db = firestore.client()
            user = db.collection("users").document(uid).get().to_dict()
            if user and user.get("subscriptionLevel") == "TRADE":
                is_trader = True
        except: pass

    result = analyze(symbol=body.symbol, potential_price=body.potential_price,
                     asset_type=body.asset_type)
    if result is None:
        raise HTTPException(status_code=404, detail=f"{body.symbol} icin veri bulunamadi.")
    
    mc_data: Optional[Dict[str, Any]] = None
    if body.run_monte_carlo or is_trader:
        # Trader'lar için simülasyon sayısını 2 katına çıkarıyoruz
        n_sims = body.n_simulations * 2 if is_trader else body.n_simulations
        hist = fetch_history(body.symbol.upper(), period="1y")
        if hist is not None and not hist.empty:
            mc_data = run_monte_carlo(
                prices=hist["Close"],
                n_simulations=n_sims,
                n_days=body.n_days,
            )
    return _enrich_result(result, mc_data)

# ── Quant Research Platform ─────────────────────────────────────────────────────

@app.post("/quant/analyze", response_model=PipelineResponse)
@limiter.limit("10/minute")
async def quant_analyze(
    request: Request, body: QuantAnalysisRequest,
    uid: Optional[str] = Depends(verify_firebase_token),
) -> PipelineResponse:
    """Runs the new Quant Research Platform pipeline (Feature Store ->
    Technical/Fundamental/News Engines -> Decision Engine ->
    Explanation Engine -> Learning Tracker) for one symbol. Separate
    from the legacy /analyze endpoint - see that endpoint's docstring
    for the backward-compatibility guarantee this one does not carry."""
    if _pipeline_service is None:
        raise HTTPException(status_code=503, detail="Quant pipeline henüz hazır değil.")
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(_executor, _pipeline_service.run, body.symbol.upper())
    except Exception as e:
        logger.error(f"Quant pipeline hatasi ({body.symbol}): {e}")
        raise HTTPException(status_code=500, detail=f"{body.symbol} icin analiz calistirilamadi.")

@app.post("/quant/predict", response_model=MLPredictionResult)
@limiter.limit("10/minute")
async def quant_predict(
    request: Request, body: MLPredictionRequest,
    uid: Optional[str] = Depends(verify_firebase_token),
) -> MLPredictionResult:
    """Direct prediction from a single trained ML model (Model Serving
    Platform), bypassing Decision Engine aggregation - separate,
    additive endpoint; `/quant/analyze` already folds every ACTIVE
    model into its own aggregated decision (see `pipeline.service.
    PipelineService.run`), so this one exists purely for callers that
    want a specific model's raw vote and metadata instead. Backward
    compatible with every existing endpoint - nothing here changes any
    other route's request or response shape."""
    if _pipeline_service is None:
        raise HTTPException(status_code=503, detail="Quant pipeline henüz hazır değil.")
    try:
        return await _pipeline_service.model_serving.predict_async(
            body.symbol.upper(), body.label_name, body.horizon_days,
        )
    except NoActiveModelError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ModelServingError as e:
        logger.error(f"Model serving hatasi ({body.symbol}): {e}")
        raise HTTPException(status_code=500, detail=f"{body.symbol} icin ML tahmini yapilamadi.")

@app.get("/quant/model-serving/health", response_model=ServingHealthReport)
def quant_model_serving_health() -> ServingHealthReport:
    """Structured Model Serving health: per-model load status,
    inference latency, cache connectivity, loading failure count."""
    if _pipeline_service is None:
        raise HTTPException(status_code=503, detail="Quant pipeline henüz hazır değil.")
    return _pipeline_service.model_serving.health_report()

# ── Portfolio ──────────────────────────────────────────────────────────────────

@app.post("/portfolio/optimize", response_model=PortfolioOptResult)
@limiter.limit("5/minute")
def portfolio_optimize(request: Request, body: PortfolioOptRequest,
                       uid: Optional[str] = Depends(verify_firebase_token)) -> PortfolioOptResult:
    if len(body.symbols) < 2:
        raise HTTPException(status_code=400, detail="En az 2 sembol gereklidir.")
    if len(body.symbols) > 20:
        raise HTTPException(status_code=400, detail="En fazla 20 sembol desteklenmektedir.")
    price_data: Dict[str, Any] = {}
    for sym in body.symbols:
        hist = fetch_history(sym.upper(), period="1y")
        if hist is not None and not hist.empty:
            price_data[sym.upper()] = hist["Close"]
    if len(price_data) < 2:
        raise HTTPException(status_code=404, detail="Yeterli fiyat verisi bulunamadi.")
    result = optimize_portfolio(price_data, risk_tolerance=body.risk_tolerance)
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return PortfolioOptResult(**result)

# ── Scan (parallel) ────────────────────────────────────────────────────────────

@app.post("/scan", response_model=ScanResult)
@limiter.limit("5/minute")
async def scan_symbols(request: Request, body: ScanRequest,
                       uid: Optional[str] = Depends(verify_firebase_token)) -> ScanResult:
    results = await _parallel_scan(body.symbols, body.asset_type)
    return categorize(results)

@app.get("/scan/bist", response_model=ScanResult)
@limiter.limit("5/minute")
async def scan_bist(request: Request,
                    uid: Optional[str] = Depends(verify_firebase_token)) -> ScanResult:
    results = await _parallel_scan(BIST_SYMBOLS, "stock")
    return categorize(results)

@app.get("/scan/crypto", response_model=ScanResult)
@limiter.limit("5/minute")
async def scan_crypto(request: Request,
                      uid: Optional[str] = Depends(verify_firebase_token)) -> ScanResult:
    results = await _parallel_scan(CRYPTO_SYMBOLS, "crypto")
    return categorize(results)

# ── Symbols ────────────────────────────────────────────────────────────────────

@app.get("/symbols/bist",   response_model=List[str])
def get_bist_symbols() -> List[str]:   return BIST_SYMBOLS

@app.get("/symbols/crypto", response_model=List[str])
def get_crypto_symbols() -> List[str]: return CRYPTO_SYMBOLS

# ── Chart ──────────────────────────────────────────────────────────────────────

@app.get("/chart/{symbol}", response_model=ChartResponse)
@limiter.limit("30/minute")
def get_chart(
    request: Request,
    symbol: str,
    period: str = Query(default="3mo", pattern="^(1mo|3mo|6mo|1y)$"),
) -> ChartResponse:
    import numpy as np
    hist = fetch_history(symbol.upper(), period=period)
    if hist is None or hist.empty:
        raise HTTPException(status_code=404, detail=f"{symbol} icin grafik verisi bulunamadi.")

    prices = hist["Close"]
    rsi_series = None
    if len(prices) >= 15:
        delta    = prices.diff()
        gain     = delta.where(delta > 0, 0.0)
        loss     = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(com=13, min_periods=14).mean()
        avg_loss = loss.ewm(com=13, min_periods=14).mean()
        rs       = avg_gain / avg_loss.replace(0, np.nan)
        rsi_series = 100 - (100 / (1 + rs))

    points: List[ChartPoint] = []
    for i, (idx, row) in enumerate(hist.iterrows()):
        rsi_val = None
        if rsi_series is not None:
            v = rsi_series.iloc[i]
            if v == v:  # NaN kontrolü
                rsi_val = float(v)
        points.append(ChartPoint(
            date=idx.strftime("%Y-%m-%d"),
            close=round(float(row["Close"]), 4),
            volume=float(row["Volume"]),
            rsi=round(rsi_val, 1) if rsi_val is not None else None,
        ))

    first_close = float(hist["Close"].iloc[0])
    last_close  = float(hist["Close"].iloc[-1])
    change_pct  = ((last_close - first_close) / first_close) * 100 if first_close > 0 else 0.0
    return ChartResponse(
        symbol=symbol.upper(), period=period, points=points,
        change_pct=round(change_pct, 2),
        high=round(float(hist["High"].max()), 4),
        low=round(float(hist["Low"].min()),  4),
    )
