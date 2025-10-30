import os
import json
from datetime import datetime, timedelta
import requests
import pandas as pd
import yfinance as yf
import redis

from dotenv import load_dotenv
from typing import Union, List, Dict, Optional
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
# CACHE_DIR = "data/raw" # Redis kullanıldığı için dosya tabanlı önbellek artık gerekli değil
CRYPTO_PANIC_FILTER_OPTIONS = ["rising", "hot", "bullish", "bearish", "important", "saved", "lol"]

class MarketDataHandler:
    """Piyasa verilerini çeker ve Redis veya dosya sisteminde önbelleğe alır."""
    def __init__(self, redis_client: Optional[redis.Redis] = None, cache_expiry_seconds: int = 3600):
        self.redis_client = redis_client
        self.cache_expiry_seconds = cache_expiry_seconds # Varsayılan 1 saat

    def _get_cache_key(self, symbol: str, asset_type: str, period: str, interval: str) -> str:
        """
        Redis önbellek anahtarını oluşturur.
        """
        return f"market_data:{asset_type}:{symbol.replace('-', '_').replace('.','_')}:{period}:{interval}"

    def fetch_data(self, symbol: str, asset_type: str, period: str, interval: str) -> pd.DataFrame:
        """Piyasa verilerini çeker, Redis'i kontrol eder ve gerekirse günceller."""
        cache_key = self._get_cache_key(symbol, asset_type, period, interval)

        if self.redis_client:
            try:
                cached_data = self.redis_client.get(cache_key)
                if cached_data:
                    logger.info(f"Piyasa verisi Redis önbellekten okunuyor: {cache_key}")
                    # Redis'ten gelen JSON string'i DataFrame'e dönüştür
                    df = pd.read_json(cached_data.decode('utf-8'))
                    # Tarih sütununu index olarak ayarla ve datetime objesine dönüştür
                    df['Date'] = pd.to_datetime(df['Date'])
                    df.set_index('Date', inplace=True)
                    return df
            except Exception as e:
                logger.error(f"Redis'ten veri okunurken hata oluştu: {e}", exc_info=True)

        logger.info(f"Yeni piyasa verisi çekiliyor: {symbol} (Varlık Tipi: {asset_type}, Periyot: {period}, Aralık: {interval})")
        
        try:
            market_data = pd.DataFrame()
            if asset_type == 'stock':
                logger.info(f"Hisse senedi olarak algılandı. yfinance kullanılıyor: {symbol}")
                ticker = yf.Ticker(symbol)
                market_data = ticker.history(period=period, interval=interval)
                if market_data.empty:
                    logger.warning(f"yfinance'den {symbol} için veri bulunamadı.")
                    return pd.DataFrame()
                market_data.rename(columns={
                    'Open': 'Open',
                    'High': 'High',
                    'Low': 'Low',
                    'Close': 'Close',
                    'Volume': 'Volume'
                }, inplace=True)
                market_data = market_data[['Open', 'High', 'Low', 'Close', 'Volume']]

            elif asset_type == 'crypto':
                logger.info(f"Kripto para olarak algılandı. CoinGecko kullanılıyor: {symbol}")
                coin_map = {
                    "BTC-USD": "bitcoin",
                    "ETH-USD": "ethereum",
                }
                coin_id = coin_map.get(symbol, symbol.lower().replace('-usd', ''))
                if not coin_id:
                    raise ValueError(f"Invalid symbol for CoinGecko API: {symbol}")

                if period.endswith('d'): days = int(period[:-1])
                elif period.endswith('mo'): days = int(period[:-2]) * 30
                elif period.endswith('y'): days = int(period[:-1]) * 365
                else: days = "max"

                coingecko_url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
                response = requests.get(coingecko_url, params={"vs_currency": "usd", "days": days})
                response.raise_for_status()
                data_json = response.json()

                if not data_json:
                    logger.warning(f"CoinGecko'dan {symbol} için OHLC verisi bulunamadı.")
                    return pd.DataFrame()

                market_data = pd.DataFrame(data_json, columns=['timestamp', 'Open', 'High', 'Low', 'Close'])
                market_data['Date'] = pd.to_datetime(market_data['timestamp'], unit='ms')
                market_data.set_index('Date', inplace=True)
                market_data.drop('timestamp', axis=1, inplace=True)
                
                volume_url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
                volume_response = requests.get(volume_url, params={"vs_currency": "usd", "days": days})
                volume_response.raise_for_status()
                volume_data = volume_response.json()
                if 'total_volumes' in volume_data:
                    df_total_volumes = pd.DataFrame(volume_data['total_volumes'], columns=['timestamp', 'Volume'])
                    df_total_volumes['Date'] = pd.to_datetime(df_total_volumes['timestamp'], unit='ms').dt.date
                    df_total_volumes.set_index(pd.to_datetime(df_total_volumes['Date']), inplace=True)
                    df_total_volumes.drop(['timestamp', 'Date'], axis=1, inplace=True)
                    market_data = market_data.join(df_total_volumes, how='left')
                else:
                    market_data['Volume'] = np.nan # Hacim verisi yoksa NaN ata

            else:
                logger.error(f"Bilinmeyen varlık tipi: {asset_type}")
                return pd.DataFrame()

            market_data.index.name = 'Date'

            if self.redis_client and not market_data.empty:
                # DataFrame'i JSON formatına dönüştürüp Redis'e kaydet
                self.redis_client.setex(cache_key, self.cache_expiry_seconds, market_data.to_json())
                logger.info(f"Piyasa verisi Redis önbelleğe alındı: {cache_key}")
            
            return market_data

        except Exception as e:
            logger.error(f"Veri çekme ve işleme sırasında hata oluştu: {e}", exc_info=True)
            return pd.DataFrame()


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

        try:

            self.redis_client = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, db=config.REDIS_DB, password=config.REDIS_PASSWORD)

            self.redis_client.ping() # Bağlantıyı test et

            logger.info("Redis bağlantısı başarılı.")

        except redis.exceptions.ConnectionError as e:

            logger.error(f"Redis bağlantı hatası: {e}. Redis önbellekleme devre dışı bırakıldı.")

            self.redis_client = None



        self.market_handler = MarketDataHandler(redis_client=self.redis_client)

        self.news_handler = NewsDataHandler(news_api_key=config.NEWS_API_KEY, guardian_api_key=config.GUARDIAN_API_KEY)

        self.social_media_handler = SocialMediaDataHandler(client_id=config.REDDIT_CLIENT_ID, client_secret=config.REDDIT_CLIENT_SECRET, user_agent=config.REDDIT_USER_AGENT, twitter_api_key=config.TWITTER_API_KEY, twitter_api_secret_key=config.TWITTER_API_SECRET_KEY, twitter_access_token=config.TWITTER_ACCESS_TOKEN, twitter_access_token_secret=config.TWITTER_ACCESS_TOKEN_SECRET)

        self.macro_handler = MacroDataHandler()

        self.onchain_handler = OnChainDataHandler()

        logger.info("DataFetcher servisi başlatıldı.")



    def get_market_data(self, symbol: str, asset_type: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:

        """

        Belirtilen sembol için piyasa verilerini (OHLCV) çeker.



        Args:

            symbol (str): Hisse senedi/kripto para sembolü (örn: "BTC-USD").

            asset_type (str): Varlık tipi (örn: "crypto" veya "stock").

            period (str): Veri çekme periyodu (örn: "1y", "6mo", "max").

            interval (str): Veri çekme aralığı (örn: "1d", "1h", "15m").



        Returns:

            pd.DataFrame: Piyasa verilerini içeren DataFrame.

        """

        return self.market_handler.fetch_data(symbol, asset_type, period, interval)







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