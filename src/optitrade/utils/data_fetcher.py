import os
import json
import argparse
from datetime import datetime, timedelta
import requests
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv
from typing import Union, List
import praw
import logging

# .env dosyasındaki değişkenleri yükle
load_dotenv()

# API anahtarlarını ve yapılandırmayı içe aktar
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

# CryptoPanic API'nin desteklediği filtre seçenekleri
CRYPTO_PANIC_FILTER_OPTIONS = [
    "rising", "hot", "bullish", "bearish", "important", "saved", "lol"
]

# Veri önbellekleme için dizin
CACHE_DIR = "data/raw"


class MarketDataFetcher:
    """
    yfinance ve Alpha Vantage gibi kaynaklardan piyasa verilerini çeker ve önbelleğe alır.
    """
    def __init__(self, cache_dir: str = CACHE_DIR, cache_expiry_days: int = 1):
        """
        Fetcher'ı başlatır.

        Args:
            cache_dir (str): CSV dosyalarının önbelleğe alınacağı dizin.
            cache_expiry_days (int): Önbelleğin kaç gün sonra geçersiz sayılacağı.
        """
        self.cache_dir = cache_dir
        self.cache_expiry_days = cache_expiry_days
        os.makedirs(self.cache_dir, exist_ok=True)

    def _get_cache_filepath(self, symbol: str, source: str, period: str, interval: str) -> str:
        """Önbellek dosyasının yolunu oluşturur."""
        return os.path.join(self.cache_dir, f"{symbol.replace('-', '_')}_{source}_{period}_{interval}.csv")

    def _is_cache_valid(self, filepath: str) -> bool:
        """Önbellek dosyasının geçerli olup olmadığını kontrol eder."""
        if not os.path.exists(filepath):
            return False
        
        file_mod_time = datetime.fromtimestamp(os.path.getmtime(filepath))
        if datetime.now() - file_mod_time > timedelta(days=self.cache_expiry_days):
            return False
            
        return True

    def fetch_market_data(
        self, 
        symbol: str, 
        period: str, 
        interval: str, 
        data_source: str = 'yfinance',
        av_api_key: str = config.ALPHA_VANTAGE_API_KEY
    ) -> pd.DataFrame:
        """
        Piyasa verilerini çeker, önbelleği kontrol eder ve gerekirse günceller.

        Args:
            symbol (str): Hisse senedi/kripto para sembolü.
            period (str): yfinance için veri çekme periyodu.
            interval (str): yfinance için veri çekme aralığı.
            data_source (str): Veri kaynağı ('yfinance' veya 'alpha_vantage').
            av_api_key (str): Alpha Vantage API anahtarı.

        Returns:
            pd.DataFrame: Piyasa verilerini içeren DataFrame.
        """
        cache_filepath = self._get_cache_filepath(symbol, data_source, period, interval)

        if self._is_cache_valid(cache_filepath):
            logger.info(f"Önbellekten okunuyor: {cache_filepath}")
            market_data = pd.read_csv(cache_filepath, index_col='Date', parse_dates=True)
            logger.info(f"Önbellekten çekilen veri boyutu: {len(market_data)} satır.")
            return market_data

        logger.info(f"Veri çekiliyor: {symbol} (Kaynak: {data_source}, Periyot: {period}, Aralık: {interval}) - Önbellek bulunamadı veya süresi doldu.")
        market_data = pd.DataFrame()
        if data_source == 'yfinance':
            try:
                ticker = yf.Ticker(symbol)
                market_data = ticker.history(period=period, interval=interval)
            except Exception as e:
                logger.error(f"yfinance ile veri çekilirken hata oluştu: {e}")
        elif data_source == 'alpha_vantage':
            if not av_api_key:
                logger.error("Alpha Vantage için API anahtarı gerekli.")
            else:
                market_data = self._fetch_data_alpha_vantage(symbol, av_api_key)

        if not market_data.empty:
            # Tarih sütununu indekse taşı ve adını 'Date' yap
            if not isinstance(market_data.index, pd.DatetimeIndex):
                 market_data.index = pd.to_datetime(market_data.index)
            market_data.index.name = 'Date'
            market_data.to_csv(cache_filepath)
            logger.info(f"Veri önbelleğe alındı: {cache_filepath} ({len(market_data)} satır).")

        return market_data

    def _fetch_data_alpha_vantage(self, symbol: str, api_key: str, outputsize: str = 'full') -> pd.DataFrame:
        """
        Alpha Vantage API'sinden hisse senedi verilerini çeker.
        """
        base_url = "https://www.alphavantage.co/query"
        params = {
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": symbol,
            "outputsize": outputsize,
            "apikey": api_key
        }
        try:
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()

            if "Time Series (Daily)" not in data:
                logger.error(f"Hata: Alpha Vantage'dan veri çekilemedi: {data.get('Note', data)}")
                return pd.DataFrame()

            df = pd.DataFrame.from_dict(data["Time Series (Daily)"], orient="index")
            df = df.rename(columns={
                "1. open": "Open", "2. high": "High", "3. low": "Low",
                "4. close": "Close", "5. adjusted close": "Adj Close", "6. volume": "Volume"
            })
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()
            df = df.astype(float)
            return df
        except requests.exceptions.RequestException as e:
            logger.error(f"Alpha Vantage API hatası: {e}")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Alpha Vantage verisi işlenirken hata oluştu: {e}")
            return pd.DataFrame()


class RedditFetcher:
    """
    Reddit API'den veri çekmek için bir sınıf.
    """
    def __init__(self, client_id: str, client_secret: str, user_agent: str):
        if not all([client_id, client_secret, user_agent]):
            raise ValueError("Reddit API kimlik bilgileri eksik.")
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )

    def fetch_subreddit_posts(self, subreddit_name: str, limit: int = 10) -> List[str]:
        """
        Belirtilen subreddit'ten gönderileri çeker.
        """
        posts_content = []
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            for submission in subreddit.hot(limit=limit):
                content = f"{submission.title}. {submission.selftext}"
                posts_content.append(content)
        except Exception as e:
            logger.error(f"Reddit'ten veri çekilirken hata oluştu: {e}")
        return posts_content
    
    def fetch_reddit_comments(self, query: str, limit: int = 10) -> List[str]:
        """
        Belirli bir sorguya göre Reddit genelinde gönderileri arar.
        """
        results = []
        try:
            search_results = self.reddit.subreddit("all").search(query=query, limit=limit, sort='relevance')
            for post in search_results:
                content = f"{post.title}. {post.selftext}"
                results.append(content)
        except Exception as e:
            logger.error(f"Reddit arama hatası: {e}")
        return results


class NewsFetcher:
    """
    Çeşitli API'lerden haber verilerini çekmek ve yönetmek için bir sınıf.
    """
    def __init__(self, output_dir: str = "data/raw_news"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def fetch_cryptopanic_news(self, api_key: str, currencies: str = None, news_filter: str = None) -> Union[dict, None]:
        """
        CryptoPanic API'sinden haberleri çeker.
        """
        if not api_key:
            logger.error("CryptoPanic API anahtarı bulunamadı.")
            return None

        base_url = "https://cryptopanic.com/api/developer/v2/posts/"
        params = {"auth_token": api_key}
        if currencies:
            params["currencies"] = currencies
        if news_filter and news_filter in CRYPTO_PANIC_FILTER_OPTIONS:
            params["filter"] = news_filter

        try:
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"CryptoPanic API Hatası: {e}")
            return None

    def fetch_news_from_newsapi(self, api_key: str, query: str, language: str = 'en', sort_by: str = 'relevancy') -> Union[dict, None]:
        """
        NewsAPI.org'dan haberleri çeker.
        """
        if not api_key:
            logger.error("NewsAPI.org API anahtarı bulunamadı.")
            return None

        base_url = "https://newsapi.org/v2/everything"
        params = {"q": query, "apiKey": api_key, "language": language, "sortBy": sort_by}
        try:
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"NewsAPI.org API Hatası: {e}")
            return None

    def fetch_simulated_social_media_data(self, query: str) -> List[str]:
        """
        Simüle edilmiş sosyal medya verilerini döndürür.
        """
        # ... (içerik aynı kalır)
        all_messages = [
            "🚀 Bitcoin to the moon! Best investment ever! #crypto #bullish",
            "Market is crashing, losing all my money. This is terrible. 📉",
            "Just bought some more ETH. Feeling good about the future. ✨",
            "Another boring day in the market. Nothing happening.",
            "Scam alert! Don't trust this project. Very suspicious. 🚨",
            "Bitcoin halving is coming soon, huge potential!",
            "Ethereum merge will revolutionize the blockchain space.",
            "Dogecoin is a joke, stay away from meme coins.",
            "Regulatory uncertainty is hurting the crypto market.",
            "New partnership announced, bullish for this altcoin!",
            "Global inflation concerns driving demand for decentralized assets.",
            "Central banks tightening, risk assets under pressure.",
            "Just sold all my crypto, too much volatility.",
            "Holding strong, believe in the long-term vision of blockchain.",
            "This project has strong fundamentals and a great team.",
            "Beware of pump and dump schemes in the crypto space.",
            "NFT market is dead, don't waste your money.",
            "DeFi is the future of finance, embracing innovation.",
            "Government cracking down on crypto, bad news for the industry.",
            "Excited about the new developments in Web3."
        ]
        if query and query.lower() != "all":
            return [msg for msg in all_messages if query.lower() in msg.lower()]
        return all_messages

    def save_to_json(self, data: dict, request_type: str, source: str) -> Union[str, None]:
        """
        Gelen veriyi zaman damgalı bir JSON dosyasına kaydeder.
        """
        if not data or not isinstance(data, dict):
            logger.error("Kaydedilecek veri bulunamadı veya formatı yanlış.")
            return None

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"news_{source}_{request_type.replace(',', '_')}_{timestamp}.json"
        filepath = os.path.join(self.output_dir, filename)

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            logger.info(f"Veri başarıyla {filepath} dosyasına kaydedildi.")
            return filepath
        except IOError as e:
            logger.error(f"Dosyaya yazma hatası: {e}")
            return None


def main():
    """
    Komut satırından veri çekmek için ana fonksiyon.
    """
    parser = argparse.ArgumentParser(description="Çeşitli kaynaklardan finansal verileri çeker.")
    parser.add_argument('--source', type=str, choices=['market', 'cryptopanic', 'newsapi', 'social_media_sim', 'reddit'], required=True, help='Kullanılacak veri kaynağı.')
    
    # ... (diğer argümanlar aynı kalır)

    args = parser.parse_args()

    if args.source == 'market':
        # Market data fetching logic here
        pass
    # ... (diğer kaynaklar için mantık aynı kalır)


if __name__ == "__main__":
    main()