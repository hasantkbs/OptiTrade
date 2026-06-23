from fastapi import FastAPI, HTTPException, Query, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from typing import List, Optional
import logging
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

from models.schemas import (
    AnalysisRequest, AnalysisResult, ScanRequest, ScanResult,
    ChartResponse, ChartPoint,
    EnhancedAnalysisRequest, MonteCarloResult, RecommendationResult,
    PortfolioOptRequest, PortfolioOptResult,
    SessionInfo,
)
from core.analyzer import analyze
from core.ml_predictor import get_model_info
from core.advanced_analysis import run_monte_carlo, optimize_portfolio, compute_recommendation
from core.session_analysis import compute_session_score, get_current_session, SESSIONS
from core.news_analyzer import get_news_summary, analyze_news
from core.sector_intelligence import (
    analyze_sector, get_sector_overview,
    sector_overview_to_dict, sector_detail_to_dict,
    SECTOR_DEFINITIONS,
)
from data.fetcher import fetch_history
from cache_manager import cached, async_cached, invalidate_cache, get_cache_manager

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

# ── Rate Limiter ───────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ── FastAPI App ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="OptiTrade API",
    description="Hisse senedi ve kripto analiz motoru — v3.2 (Optimized)",
    version="3.2.0",
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

# ── Thread Pool (Optimized) ────────────────────────────────────────────────────
_executor = ThreadPoolExecutor(max_workers=20)

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

def _analyze_safe(symbol: str, asset_type: str) -> Optional[AnalysisResult]:
    try:
        return analyze(symbol=symbol, asset_type=asset_type)
    except Exception as e:
        logger.warning(f"Analiz hatasi {symbol}: {e}")
        return None

async def _parallel_scan(symbols: List[str], asset_type: str) -> List[AnalysisResult]:
    """Tüm sembolleri ThreadPoolExecutor ile paralel analiz et (optimized)."""
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
def root():
    return {
        "status": "ok",
        "message": "OptiTrade API v3.2",
        "cache": get_cache_manager().get_stats()
    }

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/ml/status")
@cached("ml_status", ttl=3600)
def ml_status():
    return get_model_info()

# ── Cache Management ───────────────────────────────────────────────────────────

@app.post("/admin/cache/clear")
def clear_cache(pattern: Optional[str] = None):
    """Clear cache (admin only in production)."""
    invalidate_cache(pattern)
    return {"status": "cleared", "pattern": pattern or "all"}

@app.get("/admin/cache/stats")
def cache_stats():
    """Get cache statistics."""
    return get_cache_manager().get_stats()

# ── Scan Endpoints (Cached) ────────────────────────────────────────────────────

@app.get("/scan/bist", response_model=ScanResult)
@limiter.limit("10/minute")
async def scan_bist(
    request: Request,
    uid: Optional[str] = Depends(verify_firebase_token)
):
    """Scan BIST 100 stocks (cached for 2 min)."""
    cache_key = "scan_bist"
    cache_mgr = get_cache_manager()
    cached_result = cache_mgr.get(cache_key)
    if cached_result:
        return cached_result

    results = await _parallel_scan(BIST_SYMBOLS, "stock")
    scan_result = categorize(results)
    cache_mgr.set(cache_key, scan_result, ttl=120)
    return scan_result

@app.get("/scan/crypto", response_model=ScanResult)
@limiter.limit("10/minute")
async def scan_crypto(
    request: Request,
    uid: Optional[str] = Depends(verify_firebase_token)
):
    """Scan Crypto assets (cached for 2 min)."""
    cache_key = "scan_crypto"
    cache_mgr = get_cache_manager()
    cached_result = cache_mgr.get(cache_key)
    if cached_result:
        return cached_result

    results = await _parallel_scan(CRYPTO_SYMBOLS, "crypto")
    scan_result = categorize(results)
    cache_mgr.set(cache_key, scan_result, ttl=120)
    return scan_result

@app.post("/scan", response_model=ScanResult)
@limiter.limit("20/minute")
async def scan_symbols(
    request: Request,
    body: ScanRequest,
    uid: Optional[str] = Depends(verify_firebase_token)
):
    """Custom symbol scan."""
    results = await _parallel_scan(body.symbols, body.asset_type)
    return categorize(results)

# ── Symbols ────────────────────────────────────────────────────────────────────

@app.get("/symbols/bist", response_model=List[str])
@cached("symbols_bist", ttl=86400)
def get_bist_symbols():
    return BIST_SYMBOLS

@app.get("/symbols/crypto", response_model=List[str])
@cached("symbols_crypto", ttl=86400)
def get_crypto_symbols():
    return CRYPTO_SYMBOLS

# ── Chart (Cached) ────────────────────────────────────────────────────────────

@app.get("/chart/{symbol}", response_model=ChartResponse)
@limiter.limit("30/minute")
def get_chart(
    request: Request,
    symbol: str,
    period: str = Query(default="3mo", pattern="^(1mo|3mo|6mo|1y)$"),
):
    """Get chart data (cached for 5 min)."""
    import numpy as np

    cache_key = f"chart_{symbol}_{period}"
    cache_mgr = get_cache_manager()
    cached_result = cache_mgr.get(cache_key)
    if cached_result:
        return cached_result

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

    points = [
        ChartPoint(
            x=idx.isoformat(),
            y=float(row["Close"]),
            rsi=float(rsi_series.loc[idx]) if rsi_series is not None else None
        )
        for idx, row in hist.iterrows()
    ]

    response = ChartResponse(
        symbol=symbol.upper(),
        period=period,
        points=points
    )
    cache_mgr.set(cache_key, response, ttl=300)
    return response

