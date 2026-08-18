"""
OptiTrade — News Sentiment Analysis Engine
==========================================
Haber çekme + finansal duygu analizi + piyasa/sektör filtresi.

Katmanlar:
  1. yfinance ticker news  — sembol bazlı haberler
  2. Financial Lexicon     — kurulum gerektirmeyen özel kelime sözlüğü
  3. Market Filter         — TR / US / CRYPTO ayrımı
  4. Sector Filter         — sektöre göre ağırlıklandırma
  5. Score Delta           — final ±15 skor katkısı

Önbellek: 30 dakika.
"""
from __future__ import annotations

import re
import logging
import math
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

from core.cache_manager import TTLCache

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Finansal Duygu Sözlüğü (kurulum gerektirmez)
# ─────────────────────────────────────────────────────────────────────────────

# Her kelime: (puan) — pozitif yüksek, negatif düşük, [-3, +3]
_FINANCIAL_LEXICON: Dict[str, float] = {
    # ── Güçlü Pozitif (+3) ──────────────────────────────────────────────────
    "surge": 3.0, "soar": 3.0, "skyrocket": 3.0, "breakout": 2.5,
    "record high": 3.0, "all-time high": 3.0, "beat expectations": 3.0,
    "massive growth": 3.0, "explosive": 2.5, "blowout earnings": 3.0,
    "landmark deal": 2.5, "blockbuster": 2.5, "milestone": 2.0,
    "ceasefire": 2.5, "peace deal": 2.5, "sanctions lifted": 2.5,
    "trade agreement": 2.0, "diplomatic resolution": 2.5, "deal signed": 2.0,
    "tariff reduction": 2.0, "economic cooperation": 1.5, "imf support": 1.5,

    # ── Orta Pozitif (+2) ────────────────────────────────────────────────────
    "rally": 2.0, "rise": 1.5, "gain": 1.5, "climb": 1.5, "jump": 2.0,
    "boost": 1.5, "recovery": 2.0, "rebound": 2.0, "upside": 1.5,
    "strong earnings": 2.0, "beat": 1.5, "outperform": 2.0, "upgrade": 1.5,
    "buyback": 1.5, "dividend increase": 2.0, "acquisition": 1.0,
    "partnership": 1.0, "contract win": 2.0, "approval": 2.0,
    "expansion": 1.5, "growth": 1.5, "profit": 1.5, "revenue beat": 2.0,
    "demand surge": 2.0, "strong demand": 2.0, "supply cut": 1.5,
    "rate cut": 2.0, "dovish": 2.0, "stimulus": 2.0, "bullish": 2.5,
    "fda approved": 2.5, "positive outlook": 1.5, "raised guidance": 2.0,
    "esg investment": 1.0, "ipo success": 2.0, "merger": 1.0,

    # ── Hafif Pozitif (+1) ───────────────────────────────────────────────────
    "positive": 1.0, "optimistic": 1.0, "progress": 1.0, "steady": 0.5,
    "higher": 0.5, "up": 0.3, "above": 0.3, "better than expected": 1.0,
    "resilient": 1.0, "solid": 0.8, "in line": 0.3, "stable": 0.5,
    "confident": 0.8, "opportunity": 0.8, "favorable": 1.0,

    # ── Hafif Negatif (-1) ───────────────────────────────────────────────────
    "concern": -0.8, "uncertainty": -0.8, "mixed": -0.3, "lower": -0.5,
    "below": -0.5, "disappointing": -1.0, "miss": -0.8, "risk": -0.5,
    "caution": -0.8, "warning": -0.8, "pressure": -0.8, "challenging": -0.8,
    "headwinds": -1.0, "weakness": -0.8, "slowdown": -0.8, "cut guidance": -1.5,

    # ── Orta Negatif (-2) ────────────────────────────────────────────────────
    "fall": -1.5, "drop": -1.5, "decline": -1.5, "selloff": -2.0,
    "tumble": -2.0, "plunge": -2.5, "crash": -3.0, "slump": -2.0,
    "downgrade": -1.5, "miss expectations": -2.0, "loss": -1.5,
    "write-off": -2.0, "impairment": -1.5, "default": -2.5,
    "bankruptcy": -3.0, "layoffs": -1.5, "restructuring": -1.0,
    "investigation": -1.5, "lawsuit": -1.5, "fine": -1.5, "penalty": -1.5,
    "rate hike": -2.0, "hawkish": -2.0, "inflation": -1.0, "recession": -2.5,
    "bearish": -2.5, "sell": -1.0, "short": -0.8, "overvalued": -1.0,
    "supply disruption": -1.5, "shortage": -1.0, "sanction": -2.0,
    "trade war": -2.0, "tariff": -1.0, "ban": -1.5, "blocked": -1.5,

    # ── Güçlü Negatif (-3) ──────────────────────────────────────────────────
    "collapse": -3.0, "crisis": -3.0, "failure": -2.5, "fraud": -3.0,
    "hack": -2.5, "breach": -2.0, "explosion": -2.5, "attack": -2.0,
    "war": -2.5, "conflict": -2.0, "closed": -1.5, "shutdown": -2.0,
    "embargo": -2.5, "blockade": -2.5, "seized": -2.5,
}

# Olumsuzlama kelimeleri (ardından gelen skor tersine döner)
_NEGATION_WORDS = {
    "not", "no", "never", "without", "against", "fail", "failed",
    "unlike", "despite", "however", "but", "although", "except",
}

# Güçlendirici kelimeler (sonraki puanı ×1.5 yapar)
_INTENSIFIERS = {
    "very", "extremely", "highly", "significantly", "sharply",
    "massively", "dramatically", "strongly", "major", "massive",
    "severe", "critical", "unprecedented",
}


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Haber Veri Yapısı
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class NewsItem:
    title:           str
    summary:         str
    published_at:    datetime
    source:          str
    sentiment_score: float        # [-1, +1]
    sentiment_label: str          # "POSITIVE" | "NEGATIVE" | "NEUTRAL"
    confidence:      float        # [0, 1]
    matched_keywords: List[str]   = field(default_factory=list)
    sector_relevance: float       = 1.0   # sektöre özgü ağırlık [0, 1.5]
    age_weight:       float       = 1.0   # yaş cezası [0.1, 1.0]
    weighted_score:   float       = 0.0   # final: sentiment × sector × age

    @property
    def text(self) -> str:
        return f"{self.title}. {self.summary}"


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Önbellek
# ─────────────────────────────────────────────────────────────────────────────

_NEWS_CACHE: TTLCache = TTLCache(ttl_seconds=1800)  # 30 dakika


def _cache_key(symbol: str, market: str) -> str:
    return f"{symbol.upper()}:{market.upper()}"


@dataclass
class NewsAnalysisResult:
    symbol:             str
    sector:             str
    total_news:         int
    analyzed_news:      int
    sentiment_score:    float      # [-1, +1] — tüm haberlerin ağırlıklı ortalaması
    sentiment_label:    str        # "POSITIVE" | "SLIGHTLY_POSITIVE" | "NEUTRAL" | "SLIGHTLY_NEGATIVE" | "NEGATIVE"
    score_delta:        int        # Skorlamaya katkı: -15 ile +15
    news_items:         List[NewsItem] = field(default_factory=list)
    signals:            List[str]  = field(default_factory=list)
    positive_count:     int        = 0
    negative_count:     int        = 0
    neutral_count:      int        = 0
    top_positive_title: Optional[str] = None
    top_negative_title: Optional[str] = None
    fetched_at:         str        = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error:              Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Duygu Analizi Motoru
# ─────────────────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> List[str]:
    """Metni küçük harfe çevir, noktalama kaldır, tokenize et."""
    return re.findall(r"[a-z0-9\-']+", text.lower())


def analyze_sentiment(text: str) -> Tuple[float, List[str]]:
    """
    Finansal lexicon ile metin duygusu analiz et.

    Algoritma:
      1. Metin tokenize edilir
      2. Çok kelimeli ifadeler (bigram, trigram) önce aranır
      3. Tek kelimeler aranır
      4. Olumsuzlama (negation) kontrolü: pencere ±3
      5. Güçlendirici (intensifier) çarpanı uygulanır
      6. Tüm puanlar tanh ile [-1, +1]'e normalize edilir

    Döndürür: (score [-1,+1], eşleşen_anahtar_kelimeler)
    """
    if not text or len(text.strip()) < 5:
        return 0.0, []

    lower = text.lower()
    tokens = _tokenize(lower)
    n = len(tokens)

    scores: List[float] = []
    matched: List[str]  = []

    # 1. Çok kelimeli ifadeleri önce kontrol et (en uzundan başla)
    multi_found_spans: List[Tuple[int, int]] = []
    sorted_phrases = sorted(_FINANCIAL_LEXICON.keys(), key=len, reverse=True)

    for phrase in sorted_phrases:
        if " " not in phrase:
            continue
        if phrase in lower:
            # Pozisyonu bul
            idx = lower.find(phrase)
            char_start = idx
            char_end   = idx + len(phrase)
            # Önceki negation kontrolü
            prefix = lower[max(0, char_start - 50): char_start]
            negated = any(neg in prefix.split()[-5:] for neg in _NEGATION_WORDS)
            intensified = any(i in prefix.split()[-3:] for i in _INTENSIFIERS)
            raw_score = _FINANCIAL_LEXICON[phrase]
            if negated:
                raw_score = -raw_score * 0.7
            if intensified:
                raw_score *= 1.5
            scores.append(raw_score)
            matched.append(phrase)

    # 2. Tek kelimeleri tara
    for i, token in enumerate(tokens):
        if token not in _FINANCIAL_LEXICON:
            continue
        raw_score = _FINANCIAL_LEXICON[token]

        # Olumsuzlama penceresi: [-3, 0) token
        window = tokens[max(0, i - 3): i]
        negated = any(w in _NEGATION_WORDS for w in window)
        if negated:
            raw_score = -raw_score * 0.7

        # Güçlendirici penceresi: [-2, 0) token
        intensified = any(w in _INTENSIFIERS for w in tokens[max(0, i - 2): i])
        if intensified:
            raw_score *= 1.5

        scores.append(raw_score)
        if token not in matched:
            matched.append(token)

    if not scores:
        return 0.0, []

    # 3. Ağırlıklı ortalama (güçlü sinyallere daha fazla ağırlık)
    abs_scores = [abs(s) for s in scores]
    total_weight = sum(abs_scores) or 1
    weighted_avg = sum(s * abs(s) / total_weight for s in scores)

    # 4. tanh ile sınırla
    final = math.tanh(weighted_avg / 2)
    return round(final, 4), matched[:10]


def _age_weight(published_at: datetime, now: Optional[datetime] = None) -> float:
    """
    Haber yaşına göre ağırlık:
      < 6 saat   → 1.0
      < 24 saat  → 0.8
      < 3 gün    → 0.5
      < 7 gün    → 0.3
      > 7 gün    → 0.1
    """
    if now is None:
        now = datetime.now(timezone.utc)
    # Timezone-aware yap
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    age_hours = (now - published_at).total_seconds() / 3600

    if age_hours < 6:
        return 1.0
    elif age_hours < 24:
        return 0.8
    elif age_hours < 72:
        return 0.5
    elif age_hours < 168:
        return 0.3
    return 0.1


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Sektör Filtresi
# ─────────────────────────────────────────────────────────────────────────────

def _sector_relevance(
    text: str,
    positive_kw: List[str],
    negative_kw: List[str],
) -> Tuple[float, float]:
    """
    Metnin belirli bir sektörle ne kadar ilgili olduğunu puanlar.
    Döndürür: (sector_weight, sector_bias)
      sector_weight : [0.5, 1.5] — genel ilgi ağırlığı
      sector_bias   : [-1, +1]   — sektör-spesifik yönsel etki
    """
    lower = text.lower()
    pos_hits = sum(1 for kw in positive_kw if kw in lower)
    neg_hits = sum(1 for kw in negative_kw if kw in lower)
    total_hits = pos_hits + neg_hits

    if total_hits == 0:
        return 0.5, 0.0  # ilgisiz haber — düşük ağırlık

    # Ne kadar sektöre özgü
    weight = min(1.5, 0.5 + total_hits * 0.3)
    bias   = math.tanh((pos_hits - neg_hits) * 0.5)
    return weight, bias


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Haber Çekme
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_yfinance_news(symbol: str, max_news: int = 15) -> List[Dict]:
    """yfinance'dan haber çek, standart dict listesi döndür."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        raw    = ticker.news or []
        items  = []
        for n in raw[:max_news]:
            content = n.get("content", {})
            title   = content.get("title", "")
            summary = content.get("summary", "") or content.get("description", "")
            pub_str = content.get("pubDate", "")
            source  = content.get("provider", {}).get("displayName", "Yahoo Finance")

            try:
                pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
            except Exception:
                pub_dt = datetime.now(timezone.utc)

            if title:
                items.append({
                    "title":  title,
                    "summary": summary,
                    "published_at": pub_dt,
                    "source": source,
                })
        return items
    except Exception as e:
        logger.warning(f"yfinance haber hatası {symbol}: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Ana Analiz Fonksiyonu
# ─────────────────────────────────────────────────────────────────────────────

def analyze_news(
    symbol: str,
    market: str = "AUTO",
    use_cache: bool = True,
    max_news: int = 15,
    max_age_days: int = 7,
) -> NewsAnalysisResult:
    """
    Sembol için haberleri çek ve piyasaya özgü duygu analizi yap.
    market: "TR" | "US" | "CRYPTO" | "AUTO"
    """
    from core.sector_mapper import get_sector, get_sector_keywords
    from core.market_config import get_market_for_symbol, MARKET_NEWS_KEYWORDS

    if market.upper() == "AUTO":
        market = get_market_for_symbol(symbol)
    market = market.upper()

    ck = _cache_key(symbol, market)
    if use_cache:
        cached_result = _NEWS_CACHE.get(ck)
        if cached_result is not None:
            return cached_result

    sector         = get_sector(symbol)
    pos_kw, neg_kw = get_sector_keywords(sector)

    market_kw  = MARKET_NEWS_KEYWORDS.get(market, {})
    market_pos = (market_kw.get("positive", []) +
                  market_kw.get("positive_en", []) +
                  market_kw.get("positive_tr", []))
    market_neg = (market_kw.get("negative", []) +
                  market_kw.get("negative_en", []) +
                  market_kw.get("negative_tr", []))

    from core.sector_mapper import SECTOR_KEYWORDS
    macro_pos = SECTOR_KEYWORDS.get("MACRO", {}).get("positive", [])
    macro_neg = SECTOR_KEYWORDS.get("MACRO", {}).get("negative", [])
    geo_pos   = SECTOR_KEYWORDS.get("GEOPOLITICAL", {}).get("positive", [])
    geo_neg   = SECTOR_KEYWORDS.get("GEOPOLITICAL", {}).get("negative", [])

    all_pos_kw = list(set(pos_kw + market_pos + macro_pos + geo_pos))
    all_neg_kw = list(set(neg_kw + market_neg + macro_neg + geo_neg))

    raw_news = _fetch_yfinance_news(symbol, max_news=max_news)

    if not raw_news:
        result = NewsAnalysisResult(
            symbol=symbol, sector=sector,
            total_news=0, analyzed_news=0,
            sentiment_score=0.0, sentiment_label="NEUTRAL",
            score_delta=0,
            signals=[f"Haber bulunamadı ({market} piyasası) — skor nötr"],
            error="Haber verisi alınamadı",
        )
        _NEWS_CACHE.set(ck, result)
        return result

    now    = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max_age_days)
    items: List[NewsItem] = []

    for raw in raw_news:
        pub_at = raw["published_at"]
        if pub_at.tzinfo is None:
            pub_at = pub_at.replace(tzinfo=timezone.utc)
        if pub_at < cutoff:
            continue
        text = f"{raw['title']}. {raw['summary']}"
        sentiment, keywords  = analyze_sentiment(text)
        sec_weight, sec_bias = _sector_relevance(text, all_pos_kw, all_neg_kw)
        mkt_weight, mkt_bias = _sector_relevance(text, market_pos, market_neg)
        combined_bias = sec_bias * 0.5 + mkt_bias * 0.5
        if abs(combined_bias) > 0.15:
            sentiment = math.tanh(sentiment + combined_bias * 0.4)
        age_w = _age_weight(pub_at, now)
        label = (
            "POSITIVE"          if sentiment >  0.15 else
            "SLIGHTLY_POSITIVE" if sentiment >  0.05 else
            "SLIGHTLY_NEGATIVE" if sentiment > -0.15 else
            "NEGATIVE"          if sentiment <= -0.15 else
            "NEUTRAL"
        )
        effective_weight = max(sec_weight, mkt_weight)
        item = NewsItem(
            title            = raw["title"],
            summary          = raw["summary"],
            published_at     = pub_at,
            source           = raw["source"],
            sentiment_score  = sentiment,
            sentiment_label  = label,
            confidence       = min(1.0, len(keywords) / 3),
            matched_keywords = keywords,
            sector_relevance = effective_weight,
            age_weight       = age_w,
            weighted_score   = sentiment * effective_weight * age_w,
        )
        items.append(item)

    if not items:
        result = NewsAnalysisResult(
            symbol=symbol, sector=sector,
            total_news=len(raw_news), analyzed_news=0,
            sentiment_score=0.0, sentiment_label="NEUTRAL",
            score_delta=0,
            signals=[f"Son {max_age_days} günde analiz edilebilir haber yok ({market})"],
        )
        _NEWS_CACHE.set(ck, result)
        return result

    total_weight = sum(abs(i.weighted_score) for i in items) or 1.0
    composite    = math.tanh(sum(
        i.weighted_score * abs(i.weighted_score) / total_weight for i in items
    ))

    pos_items = [i for i in items if i.sentiment_label in ("POSITIVE", "SLIGHTLY_POSITIVE")]
    neg_items = [i for i in items if i.sentiment_label in ("NEGATIVE", "SLIGHTLY_NEGATIVE")]
    neu_items = [i for i in items if i.sentiment_label == "NEUTRAL"]

    score_delta = int(round(max(-15, min(15, composite * 15))))

    if composite > 0.4:      label = "POSITIVE"
    elif composite > 0.1:    label = "SLIGHTLY_POSITIVE"
    elif composite < -0.4:   label = "NEGATIVE"
    elif composite < -0.1:   label = "SLIGHTLY_NEGATIVE"
    else:                    label = "NEUTRAL"

    signals = _build_signals(
        symbol=symbol, sector=sector, market=market,
        composite=composite, score_delta=score_delta,
        pos_items=pos_items, neg_items=neg_items, items=items,
    )

    top_pos = max(pos_items, key=lambda x: x.sentiment_score).title if pos_items else None
    top_neg = min(neg_items, key=lambda x: x.sentiment_score).title if neg_items else None

    result = NewsAnalysisResult(
        symbol           = symbol,
        sector           = sector,
        total_news       = len(raw_news),
        analyzed_news    = len(items),
        sentiment_score  = round(composite, 4),
        sentiment_label  = label,
        score_delta      = score_delta,
        news_items       = items,
        signals          = signals,
        positive_count   = len(pos_items),
        negative_count   = len(neg_items),
        neutral_count    = len(neu_items),
        top_positive_title = top_pos,
        top_negative_title = top_neg,
    )
    _NEWS_CACHE.set(ck, result)
    return result


def _build_signals(
    symbol: str,
    sector: str,
    composite: float,
    score_delta: int,
    pos_items: List[NewsItem],
    neg_items: List[NewsItem],
    items: List[NewsItem],
    market: str = "US",
) -> List[str]:
    msgs: List[str] = []
    n_total = len(items)
    n_pos   = len(pos_items)
    n_neg   = len(neg_items)

    SECTOR_TR = {
        "ENERGY": "Enerji", "TECH": "Teknoloji", "FINANCE": "Finans",
        "HEALTH": "Sağlık", "CONSUMER": "Tüketici", "INDUSTRIAL": "Sanayi",
        "MATERIALS": "Emtia", "CRYPTO": "Kripto", "GEOPOLITICAL": "Jeopolitik",
        "MACRO": "Makroekonomik", "FOREX": "Döviz",
    }
    MARKET_TR = {"TR": "BIST (Türkiye)", "US": "ABD", "CRYPTO": "Kripto"}

    sector_label = SECTOR_TR.get(sector, sector)
    market_label = MARKET_TR.get(market, market)

    if composite > 0.4:
        msgs.append(
            f"[{market_label}] {sector_label} sektöründe GÜÇLÜ OLUMLU haber akışı "
            f"({n_pos}/{n_total} pozitif) — yükseliş baskısı destekleniyor [+{score_delta}]"
        )
    elif composite > 0.1:
        msgs.append(
            f"[{market_label}] {sector_label} sektöründe hafif olumlu haberler "
            f"({n_pos}/{n_total} pozitif) [+{score_delta}]"
        )
    elif composite < -0.4:
        msgs.append(
            f"[{market_label}] {sector_label} sektöründe GÜÇLÜ OLUMSUZ haber akışı "
            f"({n_neg}/{n_total} negatif) — düşüş baskısı artıyor [{score_delta}]"
        )
    elif composite < -0.1:
        msgs.append(
            f"[{market_label}] {sector_label} sektöründe hafif olumsuz haberler "
            f"({n_neg}/{n_total} negatif) [{score_delta}]"
        )
    else:
        msgs.append(
            f"[{market_label}] {sector_label} sektöründe haberler karışık/nötr "
            f"({n_pos} pozitif, {n_neg} negatif / {n_total} toplam)"
        )

    if pos_items and composite > 0.1:
        top = max(pos_items, key=lambda x: x.weighted_score)
        msgs.append(f"Öne Çıkan Olumlu: \"{top.title[:80]}\"")

    if neg_items and composite < -0.1:
        top = min(neg_items, key=lambda x: x.weighted_score)
        msgs.append(f"Öne Çıkan Olumsuz: \"{top.title[:80]}\"")

    for event_msg in _find_sector_events(pos_items + neg_items)[:2]:
        msgs.append(event_msg)

    return msgs


def _find_sector_events(items: List[NewsItem]) -> List[str]:
    """Kritik sektör olaylarını tespit et (Hürmüz, jeopolitik vb.)."""
    msgs: List[str] = []
    critical_events = {
        # Enerji
        "hormuz": "Hürmüz Boğazı'na ilişkin haber — küresel enerji akışı risk altında",
        "strait of hormuz": "Hürmüz Boğazı haberi — enerji sektörü için kritik",
        "opec": "OPEC kararı — ham petrol fiyatlarında etki bekleniyor",
        "pipeline explosion": "Boru hattı patlaması — enerji arzında aksaklık riski",
        # Kripto
        "btc etf": "Bitcoin ETF haberi — kurumsal talep değişimi",
        "bitcoin halving": "Bitcoin Halving haberi — arz azalması yaklaşıyor",
        "exchange hack": "Kripto borsası saldırısı — güven kaybı riski",
        # Makro
        "federal reserve": "Fed kararı — tüm piyasalar için belirleyici",
        "cpi data": "CPI verisi — enflasyon beklentisi güncellenebilir",
        "nonfarm payroll": "İstihdam verisi — Fed politikası üzerinde belirleyici",
        # Jeopolitik
        "military strike": "Askeri saldırı haberi — risk iştahı düşüyor",
        "ceasefire": "Ateşkes haberi — jeopolitik risk azalıyor",
        "trade war": "Ticaret savaşı — tedarik zincirleri risk altında",
    }
    all_texts = " ".join(f"{i.title} {i.summary}".lower() for i in items)
    for key, msg in critical_events.items():
        if key in all_texts and msg not in msgs:
            msgs.append(f"⚠ Kritik Olay: {msg}")
    return msgs


def get_news_summary(symbol: str, market: str = "AUTO") -> Dict:
    """API endpoint için özet sözlük döndür."""
    result = analyze_news(symbol, market=market)
    return {
        "symbol":            result.symbol,
        "sector":            result.sector,
        "market":            market if market != "AUTO" else result.sector,
        "total_news":        result.total_news,
        "analyzed_news":     result.analyzed_news,
        "sentiment_score":   result.sentiment_score,
        "sentiment_label":   result.sentiment_label,
        "score_delta":       result.score_delta,
        "positive_count":    result.positive_count,
        "negative_count":    result.negative_count,
        "neutral_count":     result.neutral_count,
        "signals":           result.signals,
        "top_positive_title": result.top_positive_title,
        "top_negative_title": result.top_negative_title,
        "fetched_at":        result.fetched_at,
        "headlines": [
            {
                "title":        item.title,
                "sentiment":    item.sentiment_label,
                "score":        item.sentiment_score,
                "age_weight":   item.age_weight,
                "keywords":     item.matched_keywords[:5],
                "published_at": item.published_at.isoformat(),
            }
            for item in sorted(
                result.news_items,
                key=lambda x: abs(x.weighted_score),
                reverse=True,
            )[:8]
        ],
        "error": result.error,
    }
