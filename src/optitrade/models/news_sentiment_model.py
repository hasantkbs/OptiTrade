import pandas as pd
import numpy as np
from transformers import pipeline
import os
from dotenv import load_dotenv
from typing import List
import logging
from .. import config

# Loglama yapılandırması
logging.basicConfig(
    level=config.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class NewsSentimentModel:
    """
    Günlük haber başlıkları üzerinden duygu analizi yapan model.
    Kullanır: Hugging Face Transformers kütüphanesi (BERT tabanlı).
    Girdi: Günlük haber başlıkları, içerikleri.
    Çıktı: [-1.0, +1.0] arası pozitif/negatif skor.
    """
    def __init__(self):
        """
        Modeli başlatır ve Hugging Face duygu analizi pipeline'ını yükler.
        Çok dilli bir model kullanılarak Türkçe metinlerde daha iyi performans hedeflenir.
        """
        self.sentiment_pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert")

    def _analyze_single_text_sentiment(self, news_text: str) -> float:
        """
        Verilen tek bir haber metninin duygu skorunu hesaplar.

        Args:
            news_text (str): Analiz edilecek haber metni veya başlığı.

        Returns:
            float: [-1.0, +1.0] arası pozitif/negatif skor.
        """
        if not isinstance(news_text, str):
            raise TypeError("Haber metni bir string olmalıdır.")
        if not news_text.strip():
            return 0.0 # Boş metin için nötr skor

        result = self.sentiment_pipeline(news_text)[0]
        label = result['label']
        score = result['score']

        # FinBERT genellikle 'positive', 'negative', 'neutral' etiketleri döndürür.
        # Bu etiketleri -1.0 ile +1.0 arasına dönüştürelim.
        if label == 'positive':
            return float(score)
        elif label == 'negative':
            return float(-score)
        elif label == 'neutral':
            return 0.0
        else:
            return 0.0 # Bilinmeyen etiketler için nötr

    def analyze_sentiment(self, news_texts: List[str]) -> float:
        """
        Verilen haber metinleri listesinin ortalama duygu skorunu hesaplar.

        Args:
            news_texts (List[str]): Analiz edilecek haber metinleri veya başlıkları listesi.

        Returns:
            float: [-1.0, +1.0] arası ortalama pozitif/negatif skor.
        """
        if not isinstance(news_texts, list):
            raise TypeError("Haber metinleri bir liste olmalıdır.")
        if not news_texts:
            return 0.0 # Boş liste için nötr skor

        scores = [self._analyze_single_text_sentiment(text) for text in news_texts if text.strip()]
        if scores:
            return float(np.mean(scores))
        else:
            return 0.0

if __name__ == '__main__':
    # Örnek kullanım
    # NewsFetcher ve NEWS_API_KEY sadece burada test amaçlı import ediliyor.
    # Normalde bu model, haber metinlerini doğrudan almalıdır.
    from ..utils.data_fetcher import NewsFetcher
    import os

    model = NewsSentimentModel()
    fetcher = NewsFetcher()

    # NewsAPI.org'dan haber çek
    query = "Bitcoin"
    news_api_key = os.getenv('NEWS_API_KEY') # .env dosyasından çekilen anahtar

    if not news_api_key:
        logger.error("Hata: NEWS_API_KEY .env dosyasında ayarlanmamış. Lütfen NewsAPI.org API anahtarınızı ekleyin.")
    else:
        logger.info(f"--- NewsAPI.org'dan '{query}' haberleri çekiliyor ---")
        news_data = fetcher.fetch_news_from_newsapi(news_api_key, query=query, language='en')

        if news_data and news_data.get('articles'):
            logger.info(f"{len(news_data['articles'])} adet haber bulundu.")
            news_headlines = [article.get('title', '') for article in news_data['articles'] if article.get('title')]
            
            average_score = model.analyze_sentiment(news_headlines)
            sentiment = "Nötr"
            if average_score > 0.1:
                sentiment = "Pozitif"
            elif average_score < -0.1:
                sentiment = "Negatif"
            logger.info(f"--- Ortalama Duygu Skoru ({query}) ---")
            logger.info(f"Ortalama Skor: {average_score:.2f}, Ortalama Duygu: {sentiment}")

            # Her bir haberin skorunu da gösterebiliriz (isteğe bağlı)
            # for i, headline in enumerate(news_headlines):
            #     score = model._analyze_single_text_sentiment(headline)
            #     logger.info(f"Haber {i+1}: '{headline[:70]}...\n  Skor: {score:.2f}'")
        else:
            logger.warning("Analiz edilecek haber metni bulunamadı.")
