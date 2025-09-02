import numpy as np
from transformers import pipeline
import logging
from typing import List, Dict, Any

from .base_model import BaseModel
from ..utils.data_fetcher import DataFetcher
from .. import config

# Loglama yapılandırması
logger = logging.getLogger(__name__)

class NewsSentimentModel(BaseModel):
    """
    Haber başlıkları üzerinden duyarlılık analizi yaparak bir alım-satım sinyali skoru üretir ve detaylı bilgi döndürür.
    """
    def __init__(self, data_fetcher: DataFetcher):
        super().__init__(data_fetcher)
        try:
            logger.info("Duyarlılık analizi modeli (ProsusAI/finbert) yükleniyor...")
            self.sentiment_pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert")
            logger.info("Duyarlılık analizi modeli başarıyla yüklendi.")
        except Exception as e:
            logger.error(f"Hugging Face pipeline yüklenirken hata oluştu: {e}")
            self.sentiment_pipeline = None

    def _calculate_sentiment_score(self, text: str) -> float:
        if not self.sentiment_pipeline or not isinstance(text, str) or not text.strip():
            return 0.0

        try:
            truncated_text = text[:512]
            result = self.sentiment_pipeline(truncated_text)[0]
            label = result['label']
            score = result['score']

            if label == 'positive':
                return float(score)
            elif label == 'negative':
                return float(-score)
            else: # neutral
                return 0.0
        except Exception as e:
            logger.warning(f"Metin analizi sırasında bir hata oluştu: '{text[:50]}...'. Hata: {e}")
            return 0.0

    def predict(self, symbol: str, interval: str = "1d", **kwargs) -> Dict[str, Any]: # interval parametresini ekle
        if not self.sentiment_pipeline:
            logger.error("Duyarlılık analizi modeli yüklenemediği için tahmin yapılamıyor.")
            return {"score": 0.0, "details": "Model yüklenemedi."}

        query = symbol.split('-')[0]
        logger.info(f"'{query}' için haberler çekiliyor ve duyarlılık analizi yapılıyor...")

        try:
            # Haber çekme işlemi interval'den doğrudan etkilenmese de, tutarlılık için parametreyi ekleyebiliriz
            news_data = self.data_fetcher.get_news(query=query) # interval burada kullanılmıyor
            if not news_data or not news_data.get('articles'):
                logger.warning(f"'{query}' için haber bulunamadı.")
                return {"score": 0.0, "details": "Haber bulunamadı."}

            headlines = [article['title'] for article in news_data['articles'] if article.get('title')]
            if not headlines:
                logger.warning("Analiz edilecek haber başlığı bulunamadı.")
                return {"score": 0.0, "details": "Haber başlığı bulunamadı."}

            scores = [self._calculate_sentiment_score(h) for h in headlines]
            average_score = np.mean(scores) if scores else 0.0
            
            sentiment_direction = "Nötr"
            if average_score > 0.1: sentiment_direction = "Pozitif"
            elif average_score < -0.1: sentiment_direction = "Negatif"

            details = f"{len(headlines)} haber analiz edildi. Genel duyarlılık: {sentiment_direction}"
            logger.info(f"Haber Duyarlılık Analizi Sonucu: Sembol='{symbol}', Ortalama Skor={average_score:.4f}, Detay: {details}")
            return {"score": float(average_score), "details": details}

        except Exception as e:
            logger.error(f"Haber duyarlılık tahmini sırasında genel bir hata oluştu: {e}", exc_info=True)
            return {"score": 0.0, "details": "Hata oluştu."}

# Örnek Kullanım
if __name__ == '__main__':
    logger.info("--- NewsSentimentModel Test Başlatıldı ---")
    try:
        fetcher = DataFetcher()
        news_model = NewsSentimentModel(data_fetcher=fetcher)
        prediction = news_model.predict(symbol="BTC-USD", interval="1d") # interval parametresini ekle
        print("--- Test Sonucu ---")
        print(f"Model Adı: {news_model.name}")
        print(f"Tahmin: {prediction}")
    except Exception as e:
        logger.error(f"Test sırasında bir hata oluştu: {e}", exc_info=True)
    logger.info("--- NewsSentimentModel Test Tamamlandı ---")