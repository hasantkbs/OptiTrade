import pandas as pd
from transformers import pipeline
import os
from dotenv import load_dotenv

# Import from data_fetcher
from optitrade.utils.data_fetcher import NewsFetcher, NEWS_API_KEY

# .env dosyasındaki değişkenleri yükle
load_dotenv()

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
        # Türkçe metinlerde daha iyi performans için çok dilli bir model kullanılıyor.
        # Alternatif olarak, Türkçe'ye özel eğitilmiş bir model de kullanılabilir.
        self.sentiment_pipeline = pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

    def analyze_sentiment(self, news_text: str) -> float:
        """
        Verilen haber metninin duygu skorunu hesaplar.

        Args:
            news_text (str): Analiz edilecek haber metni veya başlığı.

        Returns:
            float: [-1.0, +1.0] arası pozitif/negatif skor.
                   Pozitif için 0 ile 1, Negatif için -1 ile 0 arası.
        """
        if not isinstance(news_text, str):
            raise TypeError("Haber metni bir string olmalıdır.")
        if not news_text.strip():
            return 0.0 # Boş metin için nötr skor

        result = self.sentiment_pipeline(news_text)[0]
        label = result['label']
        score = result['score']

        # nlptown/bert-base-multilingual-uncased-sentiment modeli '1 star'dan '5 stars'a kadar etiketler döndürür.
        # Bu etiketleri -1.0 ile +1.0 arasına dönüştürelim.
        # 1 star: -1.0 (çok negatif)
        # 2 stars: -0.5
        # 3 stars: 0.0 (nötr)
        # 4 stars: 0.5
        # 5 stars: 1.0 (çok pozitif)
        if label == '1 star':
            return float(-1.0 * score)
        elif label == '2 stars':
            return float(-0.5 * score)
        elif label == '3 stars':
            return float(0.0)
        elif label == '4 stars':
            return float(0.5 * score)
        elif label == '5 stars':
            return float(1.0 * score)
        else:
            return 0.0 # Bilinmeyen etiketler için nötr

if __name__ == '__main__':
    # Örnek kullanım
    model = NewsSentimentModel()
    fetcher = NewsFetcher()

    # NewsAPI.org'dan haber çek
    query = "Bitcoin"
    news_api_key = NEWS_API_KEY # .env dosyasından çekilen anahtar

    if not news_api_key:
        print("Hata: NEWS_API_KEY .env dosyasında ayarlanmamış. Lütfen NewsAPI.org API anahtarınızı ekleyin.")
    else:
        print(f"\n--- NewsAPI.org'dan '{query}' haberleri çekiliyor ---")
        news_data = fetcher.fetch_news_from_newsapi(news_api_key, query=query, language='en')

        if news_data and news_data.get('articles'):
            print(f"{len(news_data['articles'])} adet haber bulundu.")
            total_score = 0.0
            analyzed_count = 0
            
            print("\n--- Haber Duygu Analizi (NewsAPI.org Verileri) ---")
            for i, article in enumerate(news_data['articles']):
                title = article.get('title', '')
                description = article.get('description', '')
                
                text_to_analyze = title
                if not text_to_analyze and description:
                    text_to_analyze = description

                if text_to_analyze:
                    score = model.analyze_sentiment(text_to_analyze)
                    sentiment = "Nötr"
                    if score > 0.1:
                        sentiment = "Pozitif"
                    elif score < -0.1:
                        sentiment = "Negatif"
                    print(f"Haber {i+1}: '{text_to_analyze[:70]}...'\n  Skor: {score:.2f}, Duygu: {sentiment}\n")
                    total_score += score
                    analyzed_count += 1
            
            if analyzed_count > 0:
                average_score = total_score / analyzed_count
                avg_sentiment = "Nötr"
                if average_score > 0.1:
                    avg_sentiment = "Pozitif"
                elif average_score < -0.1:
                    avg_sentiment = "Negatif"
                print(f"\n--- Ortalama Duygu Skoru ({query}) ---")
                print(f"Ortalama Skor: {average_score:.2f}, Ortalama Duygu: {avg_sentiment}")
            else:
                print("Analiz edilecek haber metni bulunamadı.")
        else:
            print("NewsAPI.org'dan haber çekilemedi veya haber bulunamadı.")

    # Boş metin testi (eski örnek)
    # empty_text_score = model.analyze_sentiment("")
    # print(f"Boş metin skoru: {empty_text_score:.2f}\n")