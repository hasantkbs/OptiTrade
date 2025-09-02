
import os
import json
from datetime import datetime, timedelta
import requests
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv
from typing import Union, List, Dict
import praw
import logging

# .env dosyasındaki değişkenleri yükle
load_dotenv()

# Proje yapılandırmasını içe aktar
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

# Sabitler
CACHE_DIR = "data/raw"
CRYPTO_PANIC_FILTER_OPTIONS = ["rising", "hot", "bullish", "bearish", "important", "saved", "lol"]

class MarketDataHandler:
    """yfinance gibi kaynaklardan piyasa verilerini çeker ve önbelleğe alır."""
    def __init__(self, cache_dir: str = CACHE_DIR, cache_expiry_days: int = 1):
        self.cache_dir = cache_dir
        self.cache_expiry_days = cache_expiry_days
        os.makedirs(self.cache_dir, exist_ok=True)

    def _get_cache_filepath(self, symbol: str, period: str, interval: str) -> str:
        """Önbellek dosyasının yolunu oluşturur."""
        return os.path.join(self.cache_dir, f"{symbol.replace('-', '_')}_market_{period}_{interval}.csv")

    def _is_cache_valid(self, filepath: str) -> bool:
        """Önbellek dosyasının geçerli olup olmadığını kontrol eder."""
        if not os.path.exists(filepath):
            return False
        file_mod_time = datetime.fromtimestamp(os.path.getmtime(filepath))
        return (datetime.now() - file_mod_time) <= timedelta(days=self.cache_expiry_days)

    def fetch_data(self, symbol: str, period: str, interval: str) -> pd.DataFrame:
        """Piyasa verilerini çeker, önbelleği kontrol eder ve gerekirse günceller."""
        cache_filepath = self._get_cache_filepath(symbol, period, interval)

        if self._is_cache_valid(cache_filepath):
            logger.info(f"Piyasa verisi önbellekten okunuyor: {cache_filepath}")
            return pd.read_csv(cache_filepath, index_col='Date', parse_dates=True)

        logger.info(f"Yeni piyasa verisi çekiliyor: {symbol} (Periyot: {period}, Aralık: {interval})")
        try:
            ticker = yf.Ticker(symbol)
            market_data = ticker.history(period=period, interval=interval)
            if not market_data.empty:
                market_data.index.name = 'Date'
                market_data.to_csv(cache_filepath)
                logger.info(f"Piyasa verisi önbelleğe alındı: {cache_filepath}")
            return market_data
        except Exception as e:
            logger.error(f"yfinance ile veri çekilirken hata oluştu: {e}")
            return pd.DataFrame()

class NewsDataHandler:
    """Çeşitli API'lerden haber verilerini çekmek için bir sınıf."""
    def __init__(self, news_api_key: str = config.NEWS_API_KEY):
        self.news_api_key = news_api_key

    def fetch_news(self, query: str, language: str = 'en', sort_by: str = 'relevancy') -> Union[Dict, None]:
        """NewsAPI.org'dan haberleri çeker."""
        if not self.news_api_key:
            logger.error("NewsAPI.org için API anahtarı gerekli.")
            return None
        
        base_url = "https://newsapi.org/v2/everything"
        params = {"q": query, "apiKey": self.news_api_key, "language": language, "sortBy": sort_by}
        try:
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"NewsAPI.org API Hatası: {e}")
            return None

class SocialMediaDataHandler:
    """Reddit gibi sosyal medya platformlarından veri çeker."""
    def __init__(self, client_id: str = config.REDDIT_CLIENT_ID, client_secret: str = config.REDDIT_CLIENT_SECRET, user_agent: str = config.REDDIT_USER_AGENT):
        if not all([client_id, client_secret, user_agent]):
            logger.warning("Reddit API kimlik bilgileri eksik. Sosyal medya verileri çekilemeyecek.")
            self.reddit = None
        else:
            self.reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent
            )

    def fetch_reddit_posts(self, query: str, limit: int = 25) -> List[str]:
        """Belirli bir sorguya göre Reddit genelinde gönderileri arar."""
        if not self.reddit:
            return []
        
        results = []
        try:
            search_results = self.reddit.subreddit("all").search(query=query, limit=limit, sort='relevance')
            for post in search_results:
                results.append(f"{post.title}. {post.selftext}")
        except Exception as e:
            logger.error(f"Reddit arama hatası: {e}")
        return results

class DataFetcher:
    """
    Tüm veri kaynakları için merkezi bir arayüz.
    Modellerin veri ihtiyacını karşılamak için bu sınıfı kullanır.
    """
    def __init__(self):
        """Tüm veri işleyicilerini (handler) başlatır."""
        self.market_handler = MarketDataHandler()
        self.news_handler = NewsDataHandler()
        self.social_media_handler = SocialMediaDataHandler()
        logger.info("DataFetcher servisi başlatıldı.")

    def get_market_data(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        """
        Belirtilen sembol için piyasa verilerini (OHLCV) çeker.

        Args:
            symbol (str): Hisse senedi/kripto para sembolü (örn: "BTC-USD").
            period (str): Veri çekme periyodu (örn: "1y", "6mo", "max").
            interval (str): Veri çekme aralığı (örn: "1d", "1h", "15m").

        Returns:
            pd.DataFrame: Piyasa verilerini içeren DataFrame.
        """
        return self.market_handler.fetch_data(symbol, period, interval)

    def get_news(self, query: str) -> Union[Dict, None]:
        """
        Belirtilen sorgu ile ilgili haberleri çeker.

        Args:
            query (str): Aranacak anahtar kelime (örn: "Bitcoin").

        Returns:
            dict: Haber verilerini içeren bir sözlük.
        """
        return self.news_handler.fetch_news(query)

    def get_reddit_posts(self, query: str, limit: int = 25) -> List[str]:
        """
        Belirtilen sorgu ile ilgili Reddit gönderilerini çeker.

        Args:
            query (str): Aranacak anahtar kelime (örn: "BTC price").
            limit (int): Çekilecek maksimum gönderi sayısı.

        Returns:
            List[str]: Gönderi içeriklerini içeren bir liste.
        """
        return self.social_media_handler.fetch_reddit_posts(query, limit)

# Örnek Kullanım (Geliştirme ve test için)
if __name__ == '__main__':
    # Bu blok, modül doğrudan çalıştırıldığında çalışır.
    # Komut satırı arayüzü veya test kodları buraya eklenebilir.
    
    logger.info("DataFetcher test ediliyor...")
    fetcher = DataFetcher()

    # 1. Piyasa Verisi Çekme Testi
    btc_data = fetcher.get_market_data("BTC-USD", period="1mo", interval="1d")
    if not btc_data.empty:
        logger.info("BTC-USD Piyasa Verisi başarıyla çekildi.")
        print(btc_data.head())
    else:
        logger.error("BTC-USD Piyasa Verisi çekilemedi.")

    # 2. Haber Verisi Çekme Testi
    news = fetcher.get_news("Bitcoin")
    if news and news.get('articles'):
        logger.info(f"'{news['totalResults']}' adet Bitcoin haberi bulundu.")
        # İlk makalenin başlığını yazdır
        print(f"İlk Haber Başlığı: {news['articles'][0]['title']}")
    else:
        logger.warning("Haber verisi çekilemedi veya bulunamadı.")

    # 3. Sosyal Medya Verisi Çekme Testi
    reddit_posts = fetcher.get_reddit_posts("BTC price", limit=5)
    if reddit_posts:
        logger.info(f"{len(reddit_posts)} adet Reddit gönderisi bulundu.")
        # İlk gönderiyi yazdır
        print(f"İlk Reddit Gönderisi: {reddit_posts[0][:100]}...")
    else:
        logger.warning("Reddit gönderisi çekilemedi veya bulunamadı.")
