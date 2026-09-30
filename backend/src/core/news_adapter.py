"""
OptiTrade — Haber Duygusu Adaptörü (News Sentiment Adapter)
==============================================================
``AITraderPersona.generate_recommendation``'ın beklediği ``news_sentiment``
sözlüğünü üretmek için mevcut, kapsamlı ``core/news_analyzer.py`` motorunu
sarmalar. Toplam duygu skoru + öne çıkan başlıkların yanı sıra, haberlerin
etki seviyesini (``impact_level``) ve kategorisini (``news_category``) de
üretir.

Bu sınıflandırma bilerek ek bir LLM çağrısı YAPMIYOR:
- ``impact_level``, zaten hesaplanmış ``sentiment_score``'un ([-1, +1])
  büyüklüğünden türetiliyor — ekstra hesaplama/istek gerektirmiyor.
- ``news_category``, başlık+özet metinlerinde anahtar kelime eşleştirmesiyle
  belirleniyor.
Gerekçe: bu iki alan zaten mevcut veriden (news_analyzer'ın ürettiği
skor + ham metin) güvenilir şekilde türetilebiliyor; her sembol analizine
üçüncü bir Groq çağrısı eklemek gecikmeyi/rate-limit tüketimini artırırdı.
Kalite yetersiz kalırsa ``_classify_category`` tek bir LLM çağrısıyla
değiştirilebilir — arayüz (``get_sentiment`` dönüş şekli) aynı kalır.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.news_analyzer import NewsAnalysisResult, NewsItem, analyze_news

logger = logging.getLogger(__name__)

# Kategori başına anahtar kelimeler (İngilizce + Türkçe, küçük harfe
# normalize edilmiş metinle karşılaştırılır). Eşleşme sayısı en yüksek
# kategori seçilir; hiç eşleşme yoksa "GENERAL".
_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "EARNINGS": [
        "earnings", "revenue", "profit", "quarterly", "q1", "q2", "q3", "q4",
        "eps", "guidance", "bilanço", "kâr", "kar ", "gelir", "ciro",
    ],
    "REGULATORY": [
        "sec ", "regulation", "regulatory", "lawsuit", "fine", "antitrust",
        "investigation", "sanction", "ban", "compliance", "yasal",
        "soruşturma", "dava", "ceza", "düzenleme", "yaptırım",
    ],
    "PARTNERSHIP": [
        "partnership", "merger", "acquisition", "acquire", "deal",
        "collaborat", "joint venture", "ortaklık", "birleşme",
        "satın alma", "anlaşma", "işbirliği",
    ],
    "MACRO": [
        "fed", "interest rate", "inflation", "gdp", "unemployment",
        "recession", "central bank", "tariff", "trade war", "faiz",
        "enflasyon", "resesyon", "merkez bankası", "işsizlik", "gümrük",
    ],
}


class NewsSentimentAdapter:
    """``core/news_analyzer.py``'ı çağırıp AI için kompakt bir haber özeti üretir.

    ``news_analyzer`` zaten kendi içinde 30 dakikalık bir cache uyguladığı
    için burada ayrıca bir cache katmanı eklenmez — ``use_cache`` doğrudan
    ``analyze_news``'a iletilir. Dönen sözlük, LLM promptunu şişirmemek için
    her haberin tam detayını değil (``news_items``), sadece toplulaştırılmış
    skor/etiket, etki seviyesi, kategori ve öne çıkan başlıkları içerir.
    """

    def __init__(self, market: str = "AUTO", max_news: int = 10, use_cache: bool = True) -> None:
        self.market = market
        self.max_news = max_news
        self.use_cache = use_cache

    def get_sentiment(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Sembol için kompakt haber duygu özetini döner; haber yoksa veya hata olursa None."""
        try:
            result: NewsAnalysisResult = analyze_news(
                symbol,
                market=self.market,
                use_cache=self.use_cache,
                max_news=self.max_news,
            )
        except Exception as exc:
            logger.warning(f"{symbol}: haber duygu analizi başarısız: {exc}")
            return None

        if result.error or result.total_news == 0:
            return None

        return {
            "sentiment_score": result.sentiment_score,
            "sentiment_label": result.sentiment_label,
            "impact_level": self._classify_impact(result.sentiment_score),
            "news_category": self._classify_category(result.news_items),
            "total_news": result.total_news,
            "positive_count": result.positive_count,
            "negative_count": result.negative_count,
            "neutral_count": result.neutral_count,
            "top_positive_title": result.top_positive_title,
            "top_negative_title": result.top_negative_title,
            "signals": result.signals,
        }

    @staticmethod
    def _classify_impact(sentiment_score: float) -> str:
        """``[-1, +1]`` aralığındaki toplam duygu skorunun büyüklüğünden etki seviyesi türetir."""
        magnitude = abs(sentiment_score)
        if magnitude >= 0.6:
            return "HIGH"
        if magnitude >= 0.25:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _classify_category(news_items: List[NewsItem]) -> str:
        """Başlık+özet metinlerindeki anahtar kelimelere göre baskın haber kategorisini belirler."""
        scores: Dict[str, int] = {category: 0 for category in _CATEGORY_KEYWORDS}

        for item in news_items:
            text = item.text.lower()
            for category, keywords in _CATEGORY_KEYWORDS.items():
                scores[category] += sum(1 for kw in keywords if kw in text)

        best_category = max(scores, key=scores.get)
        return best_category if scores[best_category] > 0 else "GENERAL"
