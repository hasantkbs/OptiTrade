class SocialSentimentModel:
    """
    Sosyal medya mesajlarından duygu analizi yapan sınıf.
    Şimdilik her zaman nötr (0.0) döner.
    """
    def __init__(self):
        """
        Modeli başlatır. Duygu analizi her zaman nötr (0.0) dönecek şekilde ayarlanmıştır.
        """
        pass # Duygu analizi pipeline'ı veya RedditFetcher başlatmaya gerek yok

    def analyze_sentiment_for_text(self, social_media_text: str) -> float:
        """
        Verilen tek bir sosyal medya metninin duygu skorunu hesaplar.
        Şimdilik her zaman nötr (0.0) döner.

        Args:
            social_media_text (str): Analiz edilecek sosyal medya metni.

        Returns:
            float: Her zaman 0.0 (nötr).
        """
        return 0.0

    def analyze_sentiment(self, social_media_messages: list[str]) -> float:
        """
        Verilen sosyal medya mesajları listesinin ortalama duygu skorunu hesaplar.
        Şimdilik her zaman nötr (0.0) döner.

        Args:
            social_media_messages (list[str]): Analiz edilecek sosyal medya mesajları listesi.

        Returns:
            float: Her zaman 0.0 (nötr).
        """
        return 0.0

    def analyze_reddit_sentiment(self, subreddit_name: str, limit: int = 10) -> float:
        """
        Reddit duygu analizi şimdilik devre dışı bırakılmıştır ve her zaman nötr (0.0) döner.

        Args:
            subreddit_name (str): Reddit subreddit'inin adı (örn: "wallstreetbets").
            limit (int): Çekilecek gönderi sayısı.

        Returns:
            float: Her zaman 0.0 (nötr).
        """
        print(f"Reddit duygu analizi geçici olarak devre dışı bırakıldı. Nötr skor (0.0) dönüyor.")
        return 0.0

if __name__ == '__main__':
    print("🔍 Sosyal Medya Duygu Analizi Başlatılıyor (Geçici Olarak Nötr)...")

    model = SocialSentimentModel()

    # Simüle edilmiş sosyal medya verisi için örnek kullanım
    social_media_messages = [
        "Bu harika bir gün!",
        "Piyasa biraz durgun.",
        "Her şey kötüye gidiyor."
    ]

    print(f"\n--- Simüle Sosyal Medya Duygu Analizi ---")
    average_score = model.analyze_sentiment(social_media_messages)
    print(f"Ortalama Skor: {average_score:.2f} (Her zaman 0.0 olmalı)")

    # Reddit duygu analizi için örnek kullanım
    reddit_subreddit = "wallstreetbets"
    reddit_sentiment_score = model.analyze_reddit_sentiment(reddit_subreddit, limit=5)
    print(f"Ortalama Reddit Duygu Skoru (r/{reddit_subreddit}): {reddit_sentiment_score:.2f} (Her zaman 0.0 olmalı)")
