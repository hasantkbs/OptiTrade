import numpy as np
from transformers import pipeline
import logging
from typing import Dict, Any

from .base_model import BaseModel
from ..utils.data_fetcher import DataFetcher

# Loglama yapılandırması
logger = logging.getLogger(__name__)

class SocialSentimentModel(BaseModel):
    """
    Sosyal medya (Reddit) gönderileri üzerinden duyarlılık analizi yaparak bir skor üretir ve detaylı bilgi döndürür.
    """
    def __init__(self, data_fetcher: DataFetcher):
        super().__init__(data_fetcher)
        try:
            logger.info("Duyarlılık analizi modeli (ProsusAI/finbert) Sosyal Medya için yükleniyor...")
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
        logger.info(f"'{query}' için Reddit gönderileri çekiliyor ve analiz ediliyor...")

        try:
            posts = self.data_fetcher.get_reddit_posts(query=query, limit=25)
            if not posts:
                logger.warning(f"'{query}' için Reddit gönderisi bulunamadı.")
                return {"score": 0.0, "details": "Reddit gönderisi bulunamadı."}

            scores = [self._calculate_sentiment_score(post) for post in posts]
            average_score = np.mean(scores) if scores else 0.0
            
            sentiment_direction = "Nötr"
            if average_score > 0.1: sentiment_direction = "Pozitif"
            elif average_score < -0.1: sentiment_direction = "Negatif"

            details = f"{len(posts)} Reddit gönderisi analiz edildi. Genel duyarlılık: {sentiment_direction}"
            logger.info(f"Sosyal Medya Duyarlılık Analizi Sonucu: Sembol='{symbol}', Ortalama Skor={average_score:.4f}, Detay: {details}")
            return {"score": float(average_score), "details": details}

        except Exception as e:
            logger.error(f"Sosyal medya duyarlılık tahmini sırasında genel bir hata oluştu: {e}", exc_info=True)
            return {"score": 0.0, "details": "Hata oluştu."}

# Örnek Kullanım
if __name__ == '__main__':
    logger.info("--- SocialSentimentModel Test Başlatıldı ---")
    try:
        fetcher = DataFetcher()
        model = SocialSentimentModel(data_fetcher=fetcher)
        prediction = model.predict(symbol="Bitcoin", interval="1d") # interval parametresini ekle
        print("--- Test Sonucu ---")
        print(f"Model Adı: {model.name}")
        print(f"Tahmin: {prediction}")
    except Exception as e:
        logger.error(f"Test sırasında bir hata oluştu: {e}", exc_info=True)
    logger.info("--- SocialSentimentModel Test Tamamlandı ---")