import pandas as pd
from transformers import pipeline

class SocialSentimentModel:
    """
    Twitter, Reddit gibi kaynaklardan halk algısını çıkaran model.
    Kullanır: Hugging Face Transformers kütüphanesi (BERT tabanlı, çok dilli).
    Girdi: Tweet ve forum mesajları.
    Çıktı: Sosyal medya pozitiflik skoru ([-1.0, +1.0] arası).
    """
    def __init__(self):
        """
        Modeli başlatır ve Hugging Face duygu analizi pipeline'ını yükler.
        Çok dilli duygu analizi için özel olarak eğitilmiş bir model kullanılır.
        """
        self.sentiment_pipeline = pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

    def analyze_sentiment(self, social_media_text: str) -> float:
        """
        Verilen sosyal medya metninin duygu skorunu hesaplar.

        Args:
            social_media_text (str): Analiz edilecek sosyal medya metni.

        Returns:
            float: [-1.0, +1.0] arası pozitif/negatif skor.
                   Pozitif için 0 ile 1, Negatif için -1 ile 0 arası.
        """
        if not isinstance(social_media_text, str):
            raise TypeError("Sosyal medya metni bir string olmalıdır.")
        if not social_media_text.strip():
            return 0.0 # Boş metin için nötr skor

        result = self.sentiment_pipeline(social_media_text)[0]
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
    model = SocialSentimentModel()

    social_media_messages = [
        "🚀 Bitcoin to the moon! Best investment ever! #crypto #bullish",
        "Market is crashing, losing all my money. This is terrible. 📉",
        "Just bought some more ETH. Feeling good about the future. ✨",
        "Another boring day in the market. Nothing happening.",
        "Scam alert! Don't trust this project. Very suspicious. 🚨",
        "Bu kripto para birimi harika bir yatırım!", # Türkçe örnek
        "Piyasa çok kötü, her şey düşüyor.", # Türkçe örnek
        "Bugün piyasada pek bir hareket yok.", # Türkçe örnek
    ]

    print("--- Sosyal Medya Duygu Analizi (Transformers) ---")
    for i, message in enumerate(social_media_messages):
        score = model.analyze_sentiment(message)
        sentiment = "Nötr"
        if score > 0.1:
            sentiment = "Pozitif"
        elif score < -0.1:
            sentiment = "Negatif"
        print(f"Mesaj {i+1}: '{message}'\n  Skor: {score:.2f}, Duygu: {sentiment}\n")

    # Boş metin testi
    empty_text_score = model.analyze_sentiment("")
    print(f"Boş metin skoru: {empty_text_score:.2f}\n")