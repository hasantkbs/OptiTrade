"""
OptiTrade — Sector Intelligence Engine
=======================================
Sektörleri analiz eder, fırsat sıralama yapar ve kullanıcıya
hangi sektörde ilerlenmesi gerektiğini söyler.

Çıktı örneği:
  [
    {"sector": "TECH",     "score": 78, "trend": "BULLISH",  "opportunity": "STRONG"},
    {"sector": "ENERGY",   "score": 52, "trend": "NEUTRAL",  "opportunity": "MODERATE"},
    {"sector": "FINANCE",  "score": 31, "trend": "BEARISH",  "opportunity": "WEAK"},
  ]
  
  Tavsiye: "Teknoloji sektörü güçlü yükseliş sinyali veriyor.
             Bu sektörde değerlendirilebilecek hisseler: NVDA, AAPL, MSFT"
"""
from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from core.cache_manager import TTLCache

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Sektör Tanımları (piyasaya göre)
# ─────────────────────────────────────────────────────────────────────────────

SECTOR_DEFINITIONS: Dict[str, Dict] = {
    "TECH": {
        "name_tr":     "Teknoloji",
        "icon":        "💻",
        "description": "Yazılım, yarı iletken, yapay zeka, donanım",
        "tr_symbols":  ["LOGO.IS", "INDES.IS", "TCELL.IS", "TTKOM.IS"],
        "us_symbols":  ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMD"],
        "risk":        "HIGH",
    },
    "ENERGY": {
        "name_tr":     "Enerji",
        "icon":        "⚡",
        "description": "Petrol, doğalgaz, yenilenebilir enerji, rafineriler",
        "tr_symbols":  ["TUPRS.IS", "PETKM.IS", "ZOREN.IS", "ENKAI.IS"],
        "us_symbols":  ["XOM", "CVX", "COP", "SLB", "OXY"],
        "risk":        "MEDIUM",
    },
    "FINANCE": {
        "name_tr":     "Finans / Bankacılık",
        "icon":        "🏦",
        "description": "Bankalar, sigorta, yatırım şirketleri",
        "tr_symbols":  ["GARAN.IS", "AKBNK.IS", "YKBNK.IS", "ISCTR.IS", "HALKB.IS"],
        "us_symbols":  ["JPM", "BAC", "GS", "MS", "V", "MA"],
        "risk":        "MEDIUM",
    },
    "HEALTH": {
        "name_tr":     "Sağlık / İlaç",
        "icon":        "🏥",
        "description": "İlaç şirketleri, tıbbi cihaz, biyoteknoloji",
        "tr_symbols":  [],   # BIST'te az sayıda sağlık hissesi var
        "us_symbols":  ["JNJ", "LLY", "PFE", "UNH", "ABBV", "BMY"],
        "risk":        "LOW",
    },
    "INDUSTRIAL": {
        "name_tr":     "Sanayi / Üretim",
        "icon":        "🏭",
        "description": "Metal, çelik, savunma, havacılık, lojistik",
        "tr_symbols":  ["EREGL.IS", "KRDMD.IS", "ASELS.IS", "ENKAI.IS"],
        "us_symbols":  ["CAT", "GE", "HON", "BA", "LMT", "UPS"],
        "risk":        "MEDIUM",
    },
    "CONSUMER": {
        "name_tr":     "Tüketici / Perakende",
        "icon":        "🛒",
        "description": "Perakende, gıda, otomotiv, elektronik tüketici",
        "tr_symbols":  ["BIMAS.IS", "MGROS.IS", "FROTO.IS", "TOASO.IS", "ARCLK.IS", "ULKER.IS"],
        "us_symbols":  ["AMZN", "WMT", "HD", "MCD", "TSLA", "NKE"],
        "risk":        "MEDIUM",
    },
    "AVIATION": {
        "name_tr":     "Havacılık / Ulaşım",
        "icon":        "✈️",
        "description": "Havayolları, turizm, lojistik",
        "tr_symbols":  ["THYAO.IS", "PGSUS.IS"],
        "us_symbols":  ["DAL", "UAL", "AAL", "FDX"],
        "risk":        "HIGH",
    },
    "MATERIALS": {
        "name_tr":     "Hammadde / Emtia",
        "icon":        "⛏️",
        "description": "Madencilik, altın, çelik, kimya",
        "tr_symbols":  ["KOZAL.IS", "SODA.IS", "KCHOL.IS"],
        "us_symbols":  ["FCX", "NEM", "GOLD", "AA", "ALB"],
        "risk":        "HIGH",
    },
    "AGRICULTURE": {
        "name_tr":     "Tarım / Gıda Üretimi",
        "icon":        "🌾",
        "description": "Tarım kimyasalları, gıda üretimi, gübre",
        "tr_symbols":  ["ULKER.IS", "AEFES.IS"],
        "us_symbols":  ["ADM", "BG", "MOS", "CF", "DE"],
        "risk":        "LOW",
    },
    "HOLDING": {
        "name_tr":     "Holdingler",
        "icon":        "🏢",
        "description": "Diversifiye yatırım şirketleri",
        "tr_symbols":  ["KCHOL.IS", "SAHOL.IS", "DOHOL.IS"],
        "us_symbols":  [],
        "risk":        "MEDIUM",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Veri Yapıları
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SymbolSnapshot:
    symbol:         str
    price:          Optional[float]
    change_pct:     Optional[float]
    rsi:            Optional[float]
    score:          Optional[int]
    decision_code:  Optional[str]
    news_delta:     int = 0
    error:          Optional[str] = None


@dataclass
class SectorResult:
    sector:            str
    name_tr:           str
    icon:              str
    description:       str
    market:            str               # "TR" | "US"
    opportunity_score: float             # 0 – 100
    trend:             str               # "STRONG_BULL" | "BULLISH" | "NEUTRAL" | "BEARISH" | "STRONG_BEAR"
    opportunity_label: str               # "GÜÇLÜ FIRSAT" | "FIRSAT" | "NÖTR" | "KAÇIN" | "GÜÇLÜ KAÇ"
    avg_technical:     float             # Ortalama teknik skor
    avg_news_delta:    float             # Ortalama haber katkısı
    avg_change_pct:    float             # Ortalama günlük değişim
    bullish_count:     int               # Yükseliş sinyali veren sembol sayısı
    total_count:       int
    top_symbols:       List[str]         # En yüksek skorlu 3 sembol
    symbols:           List[SymbolSnapshot] = field(default_factory=list)
    advice:            str = ""
    risk:              str = "MEDIUM"    # LOW | MEDIUM | HIGH
    fetched_at:        float = field(default_factory=time.time)


# Önbellek: sektör bazlı, 15 dakika
_SECTOR_CACHE: TTLCache = TTLCache(ttl_seconds=900)


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Tek Sembol Analizi
# ─────────────────────────────────────────────────────────────────────────────

def _analyze_symbol_fast(symbol: str, market: str) -> SymbolSnapshot:
    """
    Tek sembol için hızlı teknik analiz + haber delta.
    Thread pool içinde çalışır.
    """
    try:
        from core.analyzer import analyze
        from core.news_analyzer import analyze_news
        from core.market_config import get_market_for_symbol

        result = analyze(symbol, include_news=False)
        if result is None:
            return SymbolSnapshot(symbol=symbol, price=None, change_pct=None,
                                  rsi=None, score=None, decision_code=None,
                                  error="Analiz başarısız")

        # Haber delta
        try:
            news = analyze_news(symbol, market=market, use_cache=True)
            news_delta = news.score_delta
        except Exception:
            news_delta = 0

        return SymbolSnapshot(
            symbol        = symbol,
            price         = result.indicators.current_price if result.indicators else None,
            change_pct    = result.indicators.price_velocity if result.indicators else None,
            rsi           = result.indicators.rsi if result.indicators else None,
            score         = int(result.score) if result.score else None,
            decision_code = result.decision_code,
            news_delta    = news_delta,
        )
    except Exception as e:
        return SymbolSnapshot(symbol=symbol, price=None, change_pct=None,
                              rsi=None, score=None, decision_code=None,
                              error=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Sektör Analizi
# ─────────────────────────────────────────────────────────────────────────────

def analyze_sector(
    sector_key: str,
    market: str = "US",
    max_workers: int = 4,
    use_cache: bool = True,
) -> SectorResult:
    """
    Bir sektörü tüm sembolleriyle analiz et.
    Paralel yfinance çağrıları ile ~3-5 saniyede tamamlanır.
    """
    ck = f"{sector_key}:{market}"
    if use_cache:
        cached = _SECTOR_CACHE.get(ck)
        if cached is not None:
            return cached

    defn = SECTOR_DEFINITIONS.get(sector_key)
    if defn is None:
        raise ValueError(f"Bilinmeyen sektör: {sector_key}")

    sym_key = "tr_symbols" if market == "TR" else "us_symbols"
    symbols = defn.get(sym_key, [])
    if not symbols:
        return _empty_sector(sector_key, defn, market)

    # Paralel analiz
    snapshots: List[SymbolSnapshot] = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(symbols))) as pool:
        futures = {pool.submit(_analyze_symbol_fast, sym, market): sym
                   for sym in symbols}
        for f in as_completed(futures, timeout=25):
            try:
                snapshots.append(f.result())
            except Exception as e:
                sym = futures[f]
                snapshots.append(SymbolSnapshot(
                    symbol=sym, price=None, change_pct=None,
                    rsi=None, score=None, decision_code=None, error=str(e)
                ))

    result = _compute_sector_result(sector_key, defn, market, snapshots)
    _SECTOR_CACHE.set(ck, result)
    return result


def _compute_sector_result(
    sector_key: str,
    defn: Dict,
    market: str,
    snapshots: List[SymbolSnapshot],
) -> SectorResult:

    valid = [s for s in snapshots if s.score is not None]
    if not valid:
        return _empty_sector(sector_key, defn, market)

    scores      = [s.score for s in valid]
    news_deltas = [s.news_delta for s in valid]
    changes     = [s.change_pct for s in valid if s.change_pct is not None]

    avg_technical  = sum(scores) / len(scores)
    avg_news_delta = sum(news_deltas) / len(news_deltas) if news_deltas else 0
    avg_change     = sum(changes) / len(changes) if changes else 0

    bullish = [s for s in valid if s.decision_code in ("BUY", "STRONG_BUY")]
    bearish = [s for s in valid if s.decision_code in ("SELL", "STRONG_SELL")]

    # Fırsat skoru hesaplama
    # 60% teknik + 25% haber + 15% fiyat momentum
    news_norm   = max(0, min(100, 50 + avg_news_delta * 3.33))
    change_norm = max(0, min(100, 50 + avg_change * 8))
    opportunity_score = (0.60 * avg_technical +
                         0.25 * news_norm     +
                         0.15 * change_norm)
    opportunity_score = round(min(100, max(0, opportunity_score)), 1)

    # Trend etiketi
    bull_ratio = len(bullish) / len(valid) if valid else 0
    bear_ratio = len(bearish) / len(valid) if valid else 0

    if opportunity_score >= 70 and bull_ratio >= 0.5:
        trend             = "STRONG_BULL"
        opportunity_label = "GÜÇLÜ FIRSAT"
    elif opportunity_score >= 58:
        trend             = "BULLISH"
        opportunity_label = "FIRSAT"
    elif opportunity_score <= 30 and bear_ratio >= 0.5:
        trend             = "STRONG_BEAR"
        opportunity_label = "GÜÇLÜ KAÇ"
    elif opportunity_score <= 42:
        trend             = "BEARISH"
        opportunity_label = "KAÇIN"
    else:
        trend             = "NEUTRAL"
        opportunity_label = "NÖTR / İZLE"

    # En iyi semboller (skora göre)
    top = sorted(valid, key=lambda x: (x.score or 0) + x.news_delta, reverse=True)[:3]
    top_symbols = [s.symbol for s in top]

    advice = _build_advice(
        sector_key=sector_key,
        name_tr=defn["name_tr"],
        market=market,
        opportunity_score=opportunity_score,
        trend=trend,
        top_symbols=top_symbols,
        avg_news_delta=avg_news_delta,
        bull_ratio=bull_ratio,
    )

    return SectorResult(
        sector            = sector_key,
        name_tr           = defn["name_tr"],
        icon              = defn.get("icon", "📊"),
        description       = defn.get("description", ""),
        market            = market,
        opportunity_score = opportunity_score,
        trend             = trend,
        opportunity_label = opportunity_label,
        avg_technical     = round(avg_technical, 1),
        avg_news_delta    = round(avg_news_delta, 2),
        avg_change_pct    = round(avg_change, 2),
        bullish_count     = len(bullish),
        total_count       = len(valid),
        top_symbols       = top_symbols,
        symbols           = snapshots,
        advice            = advice,
        risk              = defn.get("risk", "MEDIUM"),
    )


def _build_advice(
    sector_key: str,
    name_tr: str,
    market: str,
    opportunity_score: float,
    trend: str,
    top_symbols: List[str],
    avg_news_delta: float,
    bull_ratio: float,
) -> str:
    market_label = {"TR": "BIST", "US": "ABD"}.get(market, market)
    top_str      = ", ".join(top_symbols) if top_symbols else "-"

    if trend == "STRONG_BULL":
        return (
            f"{name_tr} sektörü {market_label} borsasında GÜÇLÜ yükseliş sinyali veriyor "
            f"(fırsat skoru: {opportunity_score:.0f}/100). "
            f"Bu sektörde değerlendirilebilecek hisseler: {top_str}. "
            f"Haber akışı {'olumlu' if avg_news_delta > 0 else 'karışık'} "
            f"({avg_news_delta:+.1f} haber katkısı). Pozisyon büyütmeyi düşünün."
        )
    elif trend == "BULLISH":
        return (
            f"{name_tr} sektörü {market_label} borsasında yükseliş eğiliminde "
            f"(fırsat skoru: {opportunity_score:.0f}/100). "
            f"Takip edilebilecek hisseler: {top_str}. "
            f"Pozisyon açmadan önce bireysel hisse analizini yapın."
        )
    elif trend == "STRONG_BEAR":
        return (
            f"{name_tr} sektörü {market_label} borsasında GÜÇLÜ düşüş baskısı altında "
            f"(fırsat skoru: {opportunity_score:.0f}/100). "
            f"Bu sektörden kaçının veya mevcut pozisyonları azaltın. "
            f"Haber akışı olumsuz ({avg_news_delta:+.1f})."
        )
    elif trend == "BEARISH":
        return (
            f"{name_tr} sektörü {market_label} borsasında zayıf görünüm. "
            f"Yeni pozisyon açmaktan kaçının, mevcut pozisyonları izleyin."
        )
    else:
        return (
            f"{name_tr} sektörü {market_label} borsasında karışık sinyaller. "
            f"Bireysel hisse seçimine odaklanın: {top_str}"
        )


def _empty_sector(sector_key: str, defn: Dict, market: str) -> SectorResult:
    return SectorResult(
        sector=sector_key, name_tr=defn["name_tr"],
        icon=defn.get("icon", "📊"), description=defn.get("description", ""),
        market=market, opportunity_score=50, trend="NEUTRAL",
        opportunity_label="VERİ YOK", avg_technical=50,
        avg_news_delta=0, avg_change_pct=0, bullish_count=0,
        total_count=0, top_symbols=[], advice="Bu sektör için yeterli veri yok.",
        risk=defn.get("risk", "MEDIUM"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Tüm Sektörler Özet (Dashboard için)
# ─────────────────────────────────────────────────────────────────────────────

def get_sector_overview(
    market: str = "US",
    max_workers: int = 6,
    use_cache: bool = True,
) -> List[SectorResult]:
    """
    Piyasadaki tüm sektörleri analiz et, fırsat skoruna göre sırala.
    Yüksek fırsat → ilk sırada.
    """
    # Sembolü olan sektörleri filtrele
    sym_key = "tr_symbols" if market == "TR" else "us_symbols"
    active_sectors = [
        k for k, v in SECTOR_DEFINITIONS.items()
        if v.get(sym_key)
    ]

    results: List[SectorResult] = []
    for sector_key in active_sectors:
        try:
            r = analyze_sector(sector_key, market=market,
                               max_workers=max_workers, use_cache=use_cache)
            results.append(r)
        except Exception as e:
            logger.warning(f"Sektör analiz hatası {sector_key}: {e}")

    # Fırsat skoruna göre sırala (yüksek = önce)
    results.sort(key=lambda x: x.opportunity_score, reverse=True)
    return results


def get_top_opportunity(
    market: str = "US",
    use_cache: bool = True,
) -> Optional[SectorResult]:
    """En yüksek fırsat skoruna sahip sektörü döndür."""
    overview = get_sector_overview(market=market, use_cache=use_cache)
    return overview[0] if overview else None


def sector_overview_to_dict(results: List[SectorResult]) -> List[Dict]:
    """API için sözlük listesine çevir (symbols dahil değil — hafif)."""
    out = []
    for r in results:
        out.append({
            "sector":            r.sector,
            "name_tr":           r.name_tr,
            "icon":              r.icon,
            "description":       r.description,
            "market":            r.market,
            "opportunity_score": r.opportunity_score,
            "trend":             r.trend,
            "opportunity_label": r.opportunity_label,
            "avg_technical":     r.avg_technical,
            "avg_news_delta":    r.avg_news_delta,
            "avg_change_pct":    r.avg_change_pct,
            "bullish_count":     r.bullish_count,
            "total_count":       r.total_count,
            "top_symbols":       r.top_symbols,
            "advice":            r.advice,
            "risk":              r.risk,
        })
    return out


def sector_detail_to_dict(r: SectorResult) -> Dict:
    """API için tek sektör detaylı sözlük (semboller dahil)."""
    base = sector_overview_to_dict([r])[0]
    base["symbols"] = [
        {
            "symbol":        s.symbol,
            "price":         s.price,
            "change_pct":    s.change_pct,
            "rsi":           s.rsi,
            "score":         s.score,
            "decision_code": s.decision_code,
            "news_delta":    s.news_delta,
            "error":         s.error,
        }
        for s in sorted(r.symbols,
                        key=lambda x: (x.score or 0) + x.news_delta,
                        reverse=True)
    ]
    return base
