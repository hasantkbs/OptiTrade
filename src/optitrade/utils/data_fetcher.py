
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
import tweepy

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

    def _get_cache_filepath(self, asset_type: str, symbol: str, period: str, interval: str) -> str:
        """Önbellek dosyasının yolunu oluşturur."""
        return os.path.join(self.cache_dir, f"{asset_type}_{symbol.replace('-', '_')}_market_{period}_{interval}.csv")

    def _is_cache_valid(self, filepath: str) -> bool:
        """Önbellek dosyasının geçerli olup olmadığını kontrol eder."""
        if not os.path.exists(filepath):
            return False
        file_mod_time = datetime.fromtimestamp(os.path.getmtime(filepath))
        return (datetime.now() - file_mod_time) <= timedelta(days=self.cache_expiry_days)

    def fetch_data(self, asset_type: str, symbol: str, period: str, interval: str) -> pd.DataFrame:
        """Piyasa verilerini çeker, önbelleği kontrol eder ve gerekirse günceller."""
        cache_filepath = self._get_cache_filepath(asset_type, symbol, period, interval)

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

    def _get_financial_cache_filepath(self, symbol: str, statement_type: str) -> str:
        """Finansal tablo için önbellek dosyasının yolunu oluşturur."""
        return os.path.join(self.cache_dir, f"stock_{symbol.replace('-', '_')}_{statement_type}.json")

    def _get_info_cache_filepath(self, symbol: str) -> str:
        """Ticker info için önbellek dosyasının yolunu oluşturur."""
        return os.path.join(self.cache_dir, f"stock_{symbol.replace('-', '_')}_info.json")

    def _get_risk_free_rate_cache_filepath(self) -> str:
        """Risksiz faiz oranı için önbellek dosyasının yolunu oluşturur."""
        return os.path.join(self.cache_dir, "risk_free_rate.json")

    def fetch_financial_statement(self, symbol: str, statement_type: str) -> Union[Dict, None]:
        """
        Hisse senedi için finansal tablo verilerini (gelir tablosu, bilanço, nakit akışı) çeker.
        Veriyi JSON olarak önbelleğe alır.
        """
        cache_filepath = self._get_financial_cache_filepath(symbol, statement_type)

        if self._is_cache_valid(cache_filepath):
            logger.info(f"Finansal tablo verisi önbellekten okunuyor: {cache_filepath}")
            with open(cache_filepath, 'r') as f:
                return json.load(f)

        logger.info(f"Yeni finansal tablo verisi çekiliyor: {symbol} (Tablo: {statement_type})""")
        try:
            ticker = yf.Ticker(symbol)
            data = None
            if statement_type == "financials":
                data = ticker.financials
            elif statement_type == "balance_sheet":
                data = ticker.balance_sheet
            elif statement_type == "cashflow":
                data = ticker.cashflow
            
            if data is not None and not data.empty:
                # DataFrame'i JSON'a çevir
                data_json = json.loads(data.to_json(orient="index"))
                with open(cache_filepath, 'w') as f:
                    json.dump(data_json, f)
                logger.info(f"Finansal tablo verisi önbelleğe alındı: {cache_filepath}")
                return data_json
            return None
        except Exception as e:
            logger.error(f"yfinance ile finansal tablo verisi çekilirken hata oluştu: {e}")
            return None

    def fetch_ticker_info(self, symbol: str) -> Union[Dict, None]:
        """
        Hisse senedi için genel bilgileri (info) çeker.
        Veriyi JSON olarak önbelleğe alır.
        """
        cache_filepath = self._get_info_cache_filepath(symbol)

        if self._is_cache_valid(cache_filepath):
            logger.info(f"Ticker bilgisi önbellekten okunuyor: {cache_filepath}")
            with open(cache_filepath, 'r') as f:
                return json.load(f)

        logger.info(f"Yeni ticker bilgisi çekiliyor: {symbol}")
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            if info:
                with open(cache_filepath, 'w') as f:
                    json.dump(info, f)
                logger.info(f"Ticker bilgisi önbelleğe alındı: {cache_filepath}")
                return info
            return None
        except Exception as e:
            logger.error(f"yfinance ile ticker bilgisi çekilirken hata oluştu: {e}")
            return None

    def fetch_risk_free_rate(self) -> Union[float, None]:
        """
        Risksiz faiz oranını (10 yıllık ABD Hazine tahvili getirisi) çeker.
        Veriyi JSON olarak önbelleğe alır.
        """
        cache_filepath = self._get_risk_free_rate_cache_filepath()

        if self._is_cache_valid(cache_filepath):
            logger.info(f"Risksiz faiz oranı önbellekten okunuyor: {cache_filepath}")
            with open(cache_filepath, 'r') as f:
                return json.load().get('rate')

        logger.info("Yeni risksiz faiz oranı çekiliyor (^TNX)")
        try:
            tnx = yf.Ticker("^TNX")
            # Son bir günün verisini çek ve en son kapanış fiyatını al
            history = tnx.history(period="1d")
            if not history.empty:
                rate = history['Close'].iloc[-1] / 100 # Yüzdeye çevir
                with open(cache_filepath, 'w') as f:
                    json.dump({'rate': rate, 'timestamp': datetime.now().isoformat()}, f)
                logger.info(f"Risksiz faiz oranı önbelleğe alındı: {rate:.4f}")
                return rate
            return None
        except Exception as e:
            logger.error(f"yfinance ile risksiz faiz oranı çekilirken hata oluştu: {e}")
            return None

class NewsDataHandler:
    """Çeşitli API'lerden haber verilerini çekmek için bir sınıf."""
    def __init__(self, news_api_key: str = config.NEWS_API_KEY, guardian_api_key: str = config.GUARDIAN_API_KEY):
        self.news_api_key = news_api_key
        self.guardian_api_key = guardian_api_key

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

    def fetch_guardian_news(self, query: str) -> Union[Dict, None]:
        """The Guardian API'sinden haberleri çeker."""
        if not self.guardian_api_key:
            logger.error("The Guardian için API anahtarı gerekli.")
            return None
        
        base_url = "https://content.guardianapis.com/search"
        params = {"q": query, "api-key": self.guardian_api_key}
        try:
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"The Guardian API Hatası: {e}")
            return None

class SocialMediaDataHandler:
    """Reddit gibi sosyal medya platformlarından veri çeker."""
    def __init__(self, client_id: str = config.REDDIT_CLIENT_ID, client_secret: str = config.REDDIT_CLIENT_SECRET, user_agent: str = config.REDDIT_USER_AGENT, twitter_api_key: str = config.TWITTER_API_KEY, twitter_api_secret_key: str = config.TWITTER_API_SECRET_KEY, twitter_access_token: str = config.TWITTER_ACCESS_TOKEN, twitter_access_token_secret: str = config.TWITTER_ACCESS_TOKEN_SECRET):
        if not all([client_id, client_secret, user_agent]):
            logger.warning("Reddit API kimlik bilgileri eksik. Sosyal medya verileri çekilemeyecek.")
            self.reddit = None
        else:
            self.reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent
            )
        
        if not all([twitter_api_key, twitter_api_secret_key, twitter_access_token, twitter_access_token_secret]):
            logger.warning("Twitter API kimlik bilgileri eksik. Tweetler çekilemeyecek.")
            self.twitter_client = None
        else:
            self.twitter_client = tweepy.Client(bearer_token=None, consumer_key=twitter_api_key, consumer_secret=twitter_api_secret_key, access_token=twitter_access_token, access_token_secret=twitter_access_token_secret)

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

    def fetch_tweets(self, query: str, limit: int = 25) -> List[str]:
        """Belirli bir sorguya göre Twitter'da tweetleri arar."""
        if not self.twitter_client:
            return []
        
        results = []
        try:
            tweets = self.twitter_client.search_recent_tweets(query=query, max_results=limit)
            if tweets.data:
                for tweet in tweets.data:
                    results.append(tweet.text)
        except Exception as e:
            logger.error(f"Twitter arama hatası: {e}")
        return results

class MacroDataHandler:
    """Alpha Vantage gibi kaynaklardan makroekonomik verileri çeker."""
    def __init__(self, api_key: str = config.ALPHA_VANTAGE_API_KEY):
        self.api_key = api_key
        self.base_url = "https://www.alphavantage.co/query"

    def fetch_federal_fund_rate(self) -> Union[Dict, None]:
        """Alpha Vantage'dan aylık Federal Fon Oranı verilerini çeker."""
        if not self.api_key:
            logger.error("Alpha Vantage için API anahtarı gerekli.")
            return None

        params = {
            "function": "FEDERAL_FUNDS_RATE",
            "interval": "monthly",
            "apikey": self.api_key
        }
        try:
            response = requests.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()
            if "data" in data:
                logger.info("Federal Fon Oranı verisi başarıyla çekildi.")
                return data
            else:
                logger.warning(f"Alpha Vantage'dan veri alınamadı. Yanıt: {data}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Alpha Vantage API Hatası: {e}")
            return None

class OnChainDataHandler:
    """Blockchain.com gibi kaynaklardan zincir üstü verileri çeker."""
    def __init__(self):
        self.base_url = "https://api.blockchain.info/charts"

    def fetch_btc_transaction_data(self, timespan: str = "1year") -> Union[Dict, None]:
        """Blockchain.com'dan günlük BTC işlem sayısı verisini çeker."""
        url = f"{self.base_url}/n-transactions"
        params = {"timespan": timespan, "format": "json"}
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            logger.info("BTC işlem sayısı verisi başarıyla çekildi.")
            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Blockchain.com API Hatası: {e}")
            return None
        except Exception as e:
            logger.error(f"Zincir üstü veri işlenirken hata: {e}")
            return None

class DataFetcher:
    """
    Tüm veri kaynakları için merkezi bir arayüz.
    Modellerin veri ihtiyacını karşılamak için bu sınıfı kullanır.
    """
    def __init__(self):
        """Tüm veri işleyicilerini (handler) başlatır."""
        self.market_handler = MarketDataHandler()
        self.news_handler = NewsDataHandler(news_api_key=config.NEWS_API_KEY, guardian_api_key=config.GUARDIAN_API_KEY)
        self.social_media_handler = SocialMediaDataHandler(client_id=config.REDDIT_CLIENT_ID, client_secret=config.REDDIT_CLIENT_SECRET, user_agent=config.REDDIT_USER_AGENT, twitter_api_key=config.TWITTER_API_KEY, twitter_api_secret_key=config.TWITTER_API_SECRET_KEY, twitter_access_token=config.TWITTER_ACCESS_TOKEN, twitter_access_token_secret=config.TWITTER_ACCESS_TOKEN_SECRET)
        self.macro_handler = MacroDataHandler()
        self.onchain_handler = OnChainDataHandler()
        logger.info("DataFetcher servisi başlatıldı.")

    def get_market_data(self, asset_type: str, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        """
        Belirtilen sembol için piyasa verilerini (OHLCV) çeker.

        Args:
            asset_type (str): Varlık tipi (crypto veya stock).
            symbol (str): Hisse senedi/kripto para sembolü (örn: "BTC-USD").
            period (str): Veri çekme periyodu (örn: "1y", "6mo", "max").
            interval (str): Veri çekme aralığı (örn: "1d", "1h", "15m").

        Returns:
            pd.DataFrame: Piyasa verilerini içeren DataFrame.
        """
        return self.market_handler.fetch_data(asset_type, symbol, period, interval)

    def get_financial_statement(self, symbol: str, statement_type: str) -> Union[Dict, None]:
        """
        Belirtilen hisse senedi için finansal tablo verilerini çeker.

        Args:
            symbol (str): Hisse senedi sembolü (örn: "AAPL").
            statement_type (str): Tablo tipi ("financials", "balance_sheet", "cashflow").

        Returns:
            dict: Finansal tablo verilerini içeren bir sözlük.
        """
        return self.market_handler.fetch_financial_statement(symbol, statement_type)

    def get_ticker_info(self, symbol: str) -> Union[Dict, None]:
        """
        Belirtilen hisse senedi için genel bilgileri (info) çeker.

        Args:
            symbol (str): Hisse senedi sembolü (örn: "AAPL").

        Returns:
            dict: Ticker bilgilerini içeren bir sözlük.
        """
        return self.market_handler.fetch_ticker_info(symbol)

    def get_risk_free_rate(self) -> Union[float, None]:
        """
        Risksiz faiz oranını (10 yıllık ABD Hazine tahvili getirisi) çeker.

        Returns:
            float: Risksiz faiz oranı.
        """
        return self.market_handler.fetch_risk_free_rate()

    def get_news(self, query: str) -> Union[Dict, None]:
        """
        Belirtilen sorgu ile ilgili haberleri çeker.

        Args:
            query (str): Aranacak anahtar kelime (örn: "Bitcoin").

        Returns:
            dict: Haber verilerini içeren bir sözlük.
        """
        return self.news_handler.fetch_news(query)

    def get_guardian_news(self, query: str) -> Union[Dict, None]:
        """
        Belirtilen sorgu ile ilgili The Guardian haberlerini çeker.

        Args:
            query (str): Aranacak anahtar kelime (örn: "Bitcoin").

        Returns:
            dict: Haber verilerini içeren bir sözlük.
        """
        return self.news_handler.fetch_guardian_news(query)

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

    def get_tweets(self, query: str, limit: int = 25) -> List[str]:
        """
        Belirtilen sorgu ile ilgili tweetleri çeker.

        Args:
            query (str): Aranacak anahtar kelime (örn: "#Bitcoin").
            limit (int): Çekilecek maksimum tweet sayısı.

        Returns:
            List[str]: Tweet metinlerini içeren bir liste.
        """
        return self.social_media_handler.fetch_tweets(query, limit)

    def get_federal_fund_rate(self) -> Union[Dict, None]:
        """
        Aylık Federal Fon Oranı verilerini çeker.

        Returns:
            dict: Faiz oranı verilerini içeren bir sözlük.
        """
        return self.macro_handler.fetch_federal_fund_rate()

    def get_btc_transaction_data(self, timespan: str = "1year") -> Union[Dict, None]:
        """
        Günlük BTC işlem sayısı verisini çeker.

        Args:
            timespan (str): Veri çekme periyodu (örn: "1year", "30days").

        Returns:
            dict: İşlem sayısı verilerini içeren bir sözlük.
        """
        return self.onchain_handler.fetch_btc_transaction_data(timespan)

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

    # 4. The Guardian Haber Verisi Çekme Testi
    guardian_news = fetcher.get_guardian_news("Bitcoin")
    if guardian_news and guardian_news.get('response', {}).get('results'):
        logger.info(f"The Guardian'dan {len(guardian_news['response']['results'])} adet Bitcoin haberi bulundu.")
        # İlk makalenin başlığını yazdır
        print(f"İlk The Guardian Haberi: {guardian_news['response']['results'][0]['webTitle']}")
    else:
        logger.warning("The Guardian haberi çekilemedi veya bulunamadı.")

    # 5. Twitter Verisi Çekme Testi
    tweets = fetcher.get_tweets("#Bitcoin", limit=5)
    if tweets:
        logger.info(f"{len(tweets)} adet tweet bulundu.")
        # İlk tweeti yazdır
        print(f"İlk Tweet: {tweets[0][:100]}...")
    else:
        logger.warning("Tweet çekilemedi veya bulunamadı.")
