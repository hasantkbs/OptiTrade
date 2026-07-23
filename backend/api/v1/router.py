"""
OptiTrade — API v1 Router
===========================
All business endpoints live here.  main.py mounts this router twice:
  • /api/v1  — new versioned path for future clients
  • /        — legacy path that keeps the existing iOS app working

To add a new endpoint: add it here only.  Never add it directly to main.py.
To deprecate an endpoint: remove it from this router (the legacy mount will
also disappear, prompting a mobile update).

Breaking changes to existing response shapes are forbidden without an
explicit approval and a version bump to v2.
"""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request

from cache_manager import get_cache_manager, invalidate_cache
from core.advanced_analysis import compute_recommendation, optimize_portfolio, run_monte_carlo
from core.analyzer import analyze
from core.ml_predictor import get_model_info
from core.news_analyzer import analyze_news, get_general_market_news, get_news_summary, get_topic_news
from core.sector_intelligence import (
    SECTOR_DEFINITIONS,
    analyze_sector,
    get_sector_overview,
    sector_detail_to_dict,
    sector_overview_to_dict,
)
from core.session_analysis import SESSIONS, compute_session_score, get_current_session
from data.fetcher import fetch_history
from models.schemas import (
    AnalysisRequest,
    AnalysisResult,
    ChartPoint,
    ChartResponse,
    EnhancedAnalysisRequest,
    MonteCarloResult,
    PortfolioOptRequest,
    PortfolioOptResult,
    RecommendationResult,
    ScanRequest,
    ScanResult,
    SessionInfo,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Symbol Lists ───────────────────────────────────────────────────────────────
BIST_SYMBOLS: List[str] = [
    "THYAO.IS", "GARAN.IS", "ASELS.IS", "KCHOL.IS", "SISE.IS",
    "EREGL.IS", "BIMAS.IS", "AKBNK.IS", "YKBNK.IS", "TUPRS.IS",
    "TOASO.IS", "FROTO.IS", "SAHOL.IS", "PGSUS.IS", "TAVHL.IS",
]
CRYPTO_SYMBOLS: List[str] = [
    "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "AVAX-USD",
    "XRP-USD", "ADA-USD", "DOT-USD", "LINK-USD", "DOGE-USD",
]
BUY_CODES  = {"STRONG_BUY", "BUY"}
SELL_CODES = {"STRONG_SELL", "SELL"}

_executor = ThreadPoolExecutor(max_workers=16)

# ── Auth dependency ────────────────────────────────────────────────────────────
# verify_firebase_token lives in main.py.  We avoid importing main here
# (circular import) by resolving the dependency lazily at call time via a
# shared module.  The dependency is registered by main.py at startup.

import api.v1.auth as _auth_module

def _get_firebase_auth():
    """Return the currently registered auth dependency (set by main.py)."""
    return _auth_module.get_auth_dependency()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _categorize(results: List[AnalysisResult]) -> ScanResult:
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


def _enrich(result: AnalysisResult, mc_data: Optional[dict]) -> AnalysisResult:
    mc_model = None
    if mc_data and mc_data.get("n_simulations", 0) > 0:
        mc_model = MonteCarloResult(**mc_data)
    chart_ai_result = None
    try:
        from ml.chart_model import is_model_available, predict_chart_signal
        if is_model_available():
            import yfinance as yf
            h = yf.Ticker(result.symbol).history(period="3mo")
            if not h.empty:
                chart_ai_result = predict_chart_signal(h)
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
        "monte_carlo":    mc_model,
        "recommendation": RecommendationResult(**rec_data),
    })


def _safe_analyze(symbol: str, asset_type: str) -> Optional[AnalysisResult]:
    try:
        return analyze(symbol=symbol, asset_type=asset_type)
    except Exception as exc:
        logger.warning("Analysis failed for %s: %s", symbol, exc)
        return None


async def _parallel_scan(symbols: List[str], asset_type: str) -> List[AnalysisResult]:
    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(_executor, _safe_analyze, sym, asset_type)
        for sym in symbols
    ]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


# ── ML Status ─────────────────────────────────────────────────────────────────

@router.get("/ml/status")
def ml_status():
    cache = get_cache_manager()
    cached = cache.get("ml_status")
    if cached is not None:
        return cached
    result = get_model_info()
    cache.set("ml_status", result, ttl=3600)
    return result


# ── Cache Admin ────────────────────────────────────────────────────────────────

@router.post("/admin/cache/clear")
def clear_cache(
    pattern: Optional[str] = None,
    uid: Optional[str] = Depends(_get_firebase_auth()),
):
    removed = invalidate_cache(pattern)
    return {"status": "cleared", "pattern": pattern or "all", "removed": removed}


@router.get("/admin/cache/stats")
def cache_stats(uid: Optional[str] = Depends(_get_firebase_auth())):
    return get_cache_manager().get_stats()


# ── News ──────────────────────────────────────────────────────────────────────
# NOTE: static /news/... routes below must stay registered BEFORE the dynamic
# /news/{symbol} route — Starlette matches routes in registration order, so a
# request to /news/market would otherwise be captured by /news/{symbol} first
# (treating "market" as a ticker) if that route were declared earlier.

@router.get("/news/market")
def news_market_general(
    request: Request,
    lang: Optional[str] = None,
    uid: Optional[str] = Depends(_get_firebase_auth()),
):
    """Sembole bağlı olmayan genel piyasa gündemi (BIST + ABD + kripto, TR+EN).
    lang=tr|en verilirse başlıklar o dile çevrilir."""
    return get_general_market_news(lang=lang)


@router.get("/news/topic")
def news_for_topic(
    request: Request,
    q: str,
    lang: Optional[str] = None,
    uid: Optional[str] = Depends(_get_firebase_auth()),
):
    """Serbest metin sorgusu için haber (örn. bir sektör adı) — sembol gerektirmez.
    lang=tr|en verilirse başlıklar o dile çevrilir."""
    if not q.strip():
        raise HTTPException(status_code=400, detail="q parametresi gerekli")
    return get_topic_news(q.strip(), lang=lang)


@router.get("/news/{symbol}")
def news_for_symbol(
    request: Request,
    symbol: str,
    market: str = "AUTO",
    lang: Optional[str] = None,
    uid: Optional[str] = Depends(_get_firebase_auth()),
):
    return get_news_summary(symbol.upper(), market=market.upper(), lang=lang)


@router.post("/news/sector")
def news_for_sector(
    request: Request,
    body: dict,
    uid: Optional[str] = Depends(_get_firebase_auth()),
):
    symbols = body.get("symbols", [])[:10]
    market  = body.get("market", "AUTO").upper()
    if not symbols:
        raise HTTPException(status_code=400, detail="symbols listesi gerekli")

    results = []
    for sym in symbols:
        try:
            results.append(get_news_summary(sym.upper(), market=market))
        except Exception as exc:
            logger.warning("News fetch failed for %s: %s", sym, exc)

    if not results:
        raise HTTPException(status_code=404, detail="Haber alınamadı")

    avg_sentiment = sum(r["sentiment_score"] for r in results) / len(results)
    total_pos = sum(r["positive_count"] for r in results)
    total_neg = sum(r["negative_count"] for r in results)
    sector_label = (
        "POSITIVE"          if avg_sentiment >  0.3  else
        "SLIGHTLY_POSITIVE" if avg_sentiment >  0.05 else
        "SLIGHTLY_NEGATIVE" if avg_sentiment > -0.3  else
        "NEGATIVE"          if avg_sentiment <= -0.3 else
        "NEUTRAL"
    )
    return {
        "symbols": symbols, "market": market,
        "sector_sentiment": round(avg_sentiment, 4),
        "sector_label": sector_label,
        "total_positive": total_pos, "total_negative": total_neg,
        "symbol_results": results,
    }


# ── Market ────────────────────────────────────────────────────────────────────

@router.get("/market/watchlist/{market}")
def market_watchlist(
    market: str,
    uid: Optional[str] = Depends(_get_firebase_auth()),
):
    from core.market_config import MARKETS, get_default_watchlist, get_symbols_for_market
    market = market.upper()
    if market not in MARKETS:
        raise HTTPException(status_code=400, detail=f"Geçerli piyasalar: {list(MARKETS.keys())}")
    return {
        "market":    market,
        "info":      MARKETS[market],
        "watchlist": get_default_watchlist(market),
        "symbols":   get_symbols_for_market(market),
    }


@router.get("/market/list")
def market_list():
    from core.market_config import MARKETS
    return {"markets": MARKETS}


# ── Sectors ───────────────────────────────────────────────────────────────────

@router.get("/sectors/overview")
def sectors_overview(
    request: Request,
    market: str = "US",
    uid: Optional[str] = Depends(_get_firebase_auth()),
):
    market = market.upper()
    if market not in ("TR", "US"):
        raise HTTPException(status_code=400, detail="market: TR veya US olmalı")
    results = get_sector_overview(market=market, use_cache=True)
    return {
        "market":  market,
        "sectors": sector_overview_to_dict(results),
        "top_opportunity": {
            "sector":  results[0].sector   if results else None,
            "name_tr": results[0].name_tr  if results else None,
            "score":   results[0].opportunity_score if results else None,
            "trend":   results[0].trend    if results else None,
            "advice":  results[0].advice   if results else None,
        } if results else None,
    }


@router.get("/sectors/list/all")
def sectors_list():
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


@router.get("/sectors/{sector_key}")
def sector_detail(
    request: Request,
    sector_key: str,
    market: str = "US",
    uid: Optional[str] = Depends(_get_firebase_auth()),
):
    sector_key = sector_key.upper()
    market     = market.upper()
    if sector_key not in SECTOR_DEFINITIONS:
        raise HTTPException(
            status_code=404,
            detail=f"Bilinmeyen sektör. Geçerliler: {list(SECTOR_DEFINITIONS.keys())}",
        )
    result = analyze_sector(sector_key, market=market, use_cache=True)
    return sector_detail_to_dict(result)


# ── User ──────────────────────────────────────────────────────────────────────

@router.post("/user/preferences")
def save_user_preferences(
    request: Request,
    body: dict,
    uid: Optional[str] = Depends(_get_firebase_auth()),
):
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
    except Exception as exc:
        logger.warning("Firebase preferences write failed: %s", exc)
        return {"status": "ok", "market": market, "warning": "Firebase kayıt başarısız"}


# ── Session ────────────────────────────────────────────────────────────────────

@router.get("/session/info", response_model=SessionInfo)
def session_info():
    data = compute_session_score(
        rsi=50, macd=0, macd_signal_val=0,
        macd_hist=0, volume_ratio=1.0, base_score=50,
    )
    return SessionInfo(**data)


@router.get("/session/all")
def all_sessions():
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


@router.post("/session/analyze", response_model=SessionInfo)
def session_analyze(
    request: Request,
    body: AnalysisRequest,
    uid: Optional[str] = Depends(_get_firebase_auth()),
):
    result = analyze(symbol=body.symbol, potential_price=body.potential_price,
                     asset_type=body.asset_type)
    if result is None:
        raise HTTPException(status_code=404, detail=f"{body.symbol} için veri bulunamadı.")
    ind  = result.indicators
    data = compute_session_score(
        rsi=ind.rsi, macd=ind.macd, macd_signal_val=ind.macd_signal,
        macd_hist=ind.macd_histogram, volume_ratio=ind.volume_ratio,
        base_score=result.score,
    )
    return SessionInfo(**data)


# ── Price ──────────────────────────────────────────────────────────────────────

@router.get("/price/{symbol}")
def get_current_price(request: Request, symbol: str):
    hist = fetch_history(symbol.upper(), period="5d")
    if hist is None or hist.empty:
        raise HTTPException(status_code=404, detail=f"{symbol} fiyatı bulunamadı.")
    current    = float(hist["Close"].iloc[-1])
    prev       = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
    change_pct = ((current - prev) / prev) * 100 if prev > 0 else 0.0
    return {
        "symbol":     symbol.upper(),
        "price":      round(current, 4),
        "change_pct": round(change_pct, 2),
        "timestamp":  hist.index[-1].isoformat(),
    }


# ── Prediction storage (fire-and-forget) ─────────────────────────────────────

async def _store_prediction_bg(result: AnalysisResult) -> None:
    """
    Async background task — called by FastAPI BackgroundTasks after the response
    is sent.  Stores the analysis result as a prediction row.  Never raises so
    that a DB failure cannot affect the API response.
    """
    from db.session import get_session_factory
    from db import repository
    factory = get_session_factory()
    if factory is None:
        return
    try:
        async with factory() as session:
            await repository.store_prediction(
                session,
                symbol=result.symbol,
                asset_type=result.asset_type,
                score=result.score,
                decision_code=result.decision_code,
                confidence_pct=(
                    result.recommendation.confidence_pct
                    if result.recommendation else None
                ),
                indicators_json=(
                    result.indicators.model_dump() if result.indicators else None
                ),
                scoring_breakdown_json=result.scoring_breakdown,
                long_signals=result.long_signals,
                short_signals=result.short_signals,
                actual_price_at_prediction=(
                    result.indicators.current_price if result.indicators else None
                ),
            )
    except Exception as exc:
        logger.warning("Failed to store prediction for %s: %s", result.symbol, exc)


# ── Analyze ────────────────────────────────────────────────────────────────────

@router.post("/analyze", response_model=AnalysisResult)
async def analyze_symbol(
    request: Request,
    body: AnalysisRequest,
    background_tasks: BackgroundTasks,
    uid: Optional[str] = Depends(_get_firebase_auth()),
):
    loop   = asyncio.get_running_loop()
    result = await loop.run_in_executor(_executor, _safe_analyze, body.symbol, body.asset_type)
    if result is None:
        raise HTTPException(status_code=404, detail=f"{body.symbol} için veri bulunamadı.")
    rec_data = compute_recommendation(
        score=result.score, ml_confidence=result.ml_confidence,
        monte_carlo=None, risk_level=result.risk_level,
    )
    enriched = result.model_copy(update={"recommendation": RecommendationResult(**rec_data)})
    background_tasks.add_task(_store_prediction_bg, enriched)
    return enriched


@router.post("/analyze/enhanced", response_model=AnalysisResult)
async def analyze_enhanced(
    request: Request,
    body: EnhancedAnalysisRequest,
    background_tasks: BackgroundTasks,
    uid: Optional[str] = Depends(_get_firebase_auth()),
):
    is_trader = False
    if uid:
        try:
            from firebase_admin import firestore
            db   = firestore.client()
            user = db.collection("users").document(uid).get().to_dict()
            if user and user.get("subscriptionLevel") == "TRADE":
                is_trader = True
        except Exception:
            pass

    loop   = asyncio.get_running_loop()
    result = await loop.run_in_executor(_executor, _safe_analyze, body.symbol, body.asset_type)
    if result is None:
        raise HTTPException(status_code=404, detail=f"{body.symbol} için veri bulunamadı.")

    mc_data = None
    if body.run_monte_carlo or is_trader:
        n_sims = body.n_simulations * 2 if is_trader else body.n_simulations
        hist   = await loop.run_in_executor(
            _executor, fetch_history, body.symbol.upper(), "1y"
        )
        if hist is not None and not hist.empty:
            mc_data = run_monte_carlo(
                prices=hist["Close"],
                n_simulations=n_sims,
                n_days=body.n_days,
            )
    enriched = _enrich(result, mc_data)
    background_tasks.add_task(_store_prediction_bg, enriched)
    return enriched


# ── Prediction History ────────────────────────────────────────────────────────

@router.get("/predictions/{symbol}")
async def get_predictions(
    symbol: str,
    limit: int = Query(default=50, ge=1, le=500),
    uid: Optional[str] = Depends(_get_firebase_auth()),
):
    """
    Return the stored prediction history for a symbol.
    Includes actual outcomes once they are updated by the reconciliation job.
    Returns [] when PostgreSQL is not configured.
    """
    from db.session import get_session_factory
    from db import repository
    factory = get_session_factory()
    if factory is None:
        return {"symbol": symbol.upper(), "predictions": [], "db_available": False}
    async with factory() as session:
        predictions = await repository.get_predictions(
            session, symbol=symbol.upper(), limit=limit
        )
    return {
        "symbol":       symbol.upper(),
        "count":        len(predictions),
        "predictions":  predictions,
        "db_available": True,
    }


# ── Portfolio ──────────────────────────────────────────────────────────────────

@router.post("/portfolio/optimize", response_model=PortfolioOptResult)
def portfolio_optimize(
    request: Request,
    body: PortfolioOptRequest,
    uid: Optional[str] = Depends(_get_firebase_auth()),
):
    if len(body.symbols) < 2:
        raise HTTPException(status_code=400, detail="En az 2 sembol gereklidir.")
    if len(body.symbols) > 20:
        raise HTTPException(status_code=400, detail="En fazla 20 sembol desteklenmektedir.")
    price_data = {}
    for sym in body.symbols:
        hist = fetch_history(sym.upper(), period="1y")
        if hist is not None and not hist.empty:
            price_data[sym.upper()] = hist["Close"]
    if len(price_data) < 2:
        raise HTTPException(status_code=404, detail="Yeterli fiyat verisi bulunamadı.")
    result = optimize_portfolio(price_data, risk_tolerance=body.risk_tolerance)
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return PortfolioOptResult(**result)


# ── Scan ──────────────────────────────────────────────────────────────────────

@router.post("/scan", response_model=ScanResult)
async def scan_symbols(
    request: Request,
    body: ScanRequest,
    uid: Optional[str] = Depends(_get_firebase_auth()),
):
    results = await _parallel_scan(body.symbols, body.asset_type)
    return _categorize(results)


@router.get("/scan/bist", response_model=ScanResult)
async def scan_bist(
    request: Request,
    uid: Optional[str] = Depends(_get_firebase_auth()),
):
    cache = get_cache_manager()
    cached = cache.get("scan_bist")
    if cached is not None:
        return cached
    results     = await _parallel_scan(BIST_SYMBOLS, "stock")
    scan_result = _categorize(results)
    cache.set("scan_bist", scan_result, ttl=120)
    return scan_result


@router.get("/scan/crypto", response_model=ScanResult)
async def scan_crypto(
    request: Request,
    uid: Optional[str] = Depends(_get_firebase_auth()),
):
    cache = get_cache_manager()
    cached = cache.get("scan_crypto")
    if cached is not None:
        return cached
    results     = await _parallel_scan(CRYPTO_SYMBOLS, "crypto")
    scan_result = _categorize(results)
    cache.set("scan_crypto", scan_result, ttl=120)
    return scan_result


# ── Symbols ────────────────────────────────────────────────────────────────────

@router.get("/symbols/bist",   response_model=List[str])
def get_bist_symbols():   return BIST_SYMBOLS

@router.get("/symbols/crypto", response_model=List[str])
def get_crypto_symbols(): return CRYPTO_SYMBOLS


# ── Chart ──────────────────────────────────────────────────────────────────────

@router.get("/chart/{symbol}", response_model=ChartResponse)
def get_chart(
    request: Request,
    symbol: str,
    period: str = Query(default="3mo", pattern="^(1mo|3mo|6mo|1y)$"),
):
    cache     = get_cache_manager()
    cache_key = f"chart_{symbol.upper()}_{period}"
    cached    = cache.get(cache_key)
    if cached is not None:
        return cached

    hist = fetch_history(symbol.upper(), period=period)
    if hist is None or hist.empty:
        raise HTTPException(status_code=404, detail=f"{symbol} için grafik verisi bulunamadı.")

    prices     = hist["Close"]
    rsi_series = None
    if len(prices) >= 15:
        delta    = prices.diff()
        gain     = delta.where(delta > 0, 0.0)
        loss     = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(com=13, min_periods=14).mean()
        avg_loss = loss.ewm(com=13, min_periods=14).mean()
        rs       = avg_gain / avg_loss.replace(0, np.nan)
        rsi_series = 100 - (100 / (1 + rs))

    points = []
    for i, (idx, row) in enumerate(hist.iterrows()):
        rsi_val = None
        if rsi_series is not None:
            v = rsi_series.iloc[i]
            if v == v:  # NaN check
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
    chart_response = ChartResponse(
        symbol=symbol.upper(), period=period, points=points,
        change_pct=round(change_pct, 2),
        high=round(float(hist["High"].max()), 4),
        low=round(float(hist["Low"].min()),  4),
    )
    cache.set(cache_key, chart_response, ttl=300)
    return chart_response


# ── v2 modular endpoints (api/v1/endpoints/) ──────────────────────────────────
from api.v1.endpoints import signals  # noqa: E402

router.include_router(signals.router)
