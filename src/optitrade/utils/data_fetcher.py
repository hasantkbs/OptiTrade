import os
import json
import argparse
from datetime import datetime
import requests
from dotenv import load_dotenv
from typing import Union, List
import praw

# .env dosyasındaki değişkenleri yükle
load_dotenv()

# API anahtarlarını ortam değişkenlerinden al
CRYPTO_PANIC_API_KEY = os.getenv("CRYPTO_PANIC_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY") # NewsAPI.org için yeni anahtar
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "OptiTrade_App/1.0") # Varsayılan User-Agent

# CryptoPanic API'nin desteklediği filtre seçenekleri
CRYPTO_PANIC_FILTER_OPTIONS = [
    "rising", "hot", "bullish", "bearish", "important", "saved", "lol"
]

class RedditFetcher:
    """
    Reddit API'den veri çekmek için bir sınıf.
    """
    def __init__(self, client_id: str, client_secret: str, user_agent: str):
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )

    def fetch_subreddit_posts(self, subreddit_name: str, limit: int = 10) -> List[str]:
        """
        Belirtilen subreddit'ten gönderileri çeker.

        Args:
            subreddit_name (str): Çekilecek subreddit'in adı.
            limit (int): Çekilecek gönderi sayısı.

        Returns:
            List[str]: Gönderi başlıklarının ve metinlerinin bir listesi.
        """
        posts_content = []
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            for submission in subreddit.hot(limit=limit):
                content = f"{submission.title}. {submission.selftext}"
                posts_content.append(content)
        except Exception as e:
            print(f"❌ Reddit'ten veri çekilirken hata oluştu: {e}")
        return posts_content
    
    def fetch_reddit_comments(self, query: str, limit: int = 10) -> List[str]:
        """
        Belirli bir sorguya göre Reddit genelinde gönderileri arar ve içerikleri döndürür.

        Args:
            query (str): Aranacak anahtar kelime (örn: "Bitcoin").
            limit (int): Maksimum gönderi sayısı.

        Returns:
            List[str]: Gönderi başlıklarının ve içeriklerinin listesi.
        """
        results = []
        try:
            search_results = self.reddit.subreddit("all").search(query=query, limit=limit, sort='relevance')
            for post in search_results:
                content = f"{post.title}. {post.selftext}"
                results.append(content)
        except Exception as e:
            print(f"❌ Reddit arama hatası: {e}")
        return results


class NewsFetcher:
    """
    Çeşitli API'lerden haber verilerini çekmek ve yönetmek için bir sınıf.
    """
    def __init__(self, output_dir: str = "data/raw_news"):
        """
        Fetcher'ı başlatır.

        Args:
            output_dir (str): JSON dosyalarının kaydedileceği dizin.
        """
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def fetch_cryptopanic_news(self, api_key: str, currencies: str = None, news_filter: str = None) -> 'Union[dict, None]':
        """
        CryptoPanic API'sinden belirtilen para birimleri veya filtreye göre haberleri çeker.

        Args:
            api_key (str): CryptoPanic API anahtarı.
            currencies (str, optional): Virgülle ayrılmış para birimi kodları (örn: "BTC,ETH").
            news_filter (str, optional): Uygulanacak filtre (örn: "rising", "bullish").

        Returns:
            dict | None: API'den gelen yanıt verisi veya hata durumunda None.
        """
        if not api_key:
            print("❌ CryptoPanic API anahtarı bulunamadı.")
            return None

        base_url = "https://cryptopanic.com/api/developer/v2/posts/"
        params = {"auth_token": api_key}
        if currencies:
            params["currencies"] = currencies
        if news_filter:
            if news_filter not in CRYPTO_PANIC_FILTER_OPTIONS:
                print(f"❌ Geçersiz CryptoPanic filtresi: {news_filter}. Kullanılabilir seçenekler: {CRYPTO_PANIC_FILTER_OPTIONS}")
                return None
            params["filter"] = news_filter

        try:
            response = requests.get(base_url, params=params)
            response.raise_for_status()  # HTTP hata kodları için bir istisna fırlatır
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ CryptoPanic API Hatası: {e}")
            return None

    def fetch_news_from_newsapi(self, api_key: str, query: str, language: str = 'en', sort_by: str = 'relevancy') -> 'Union[dict, None]':
        """
        NewsAPI.org'dan haberleri çeker.

        Args:
            api_key (str): NewsAPI.org API anahtarı.
            query (str): Arama sorgusu (örn: "Bitcoin").
            language (str, optional): Haber dili (örn: 'en', 'tr'). Varsayılan: 'en'.
            sort_by (str, optional): Sıralama ölçütü (relevancy, popularity, publishedAt). Varsayılan: 'relevancy'.

        Returns:
            dict | None: API'den gelen yanıt verisi veya hata durumunda None.
        """
        if not api_key:
            print("❌ NewsAPI.org API anahtarı bulunamadı.")
            return None

        base_url = "https://newsapi.org/v2/everything"
        params = {
            "q": query,
            "apiKey": api_key,
            "language": language,
            "sortBy": sort_by
        }
        try:
            response = requests.get(base_url, params=params)
            response.raise_for_status() # HTTP hataları için istisna fırlat
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ NewsAPI.org API Hatası: {e}")
            return None

    def fetch_simulated_social_media_data(self, query: str) -> List[str]:
        """
        Simüle edilmiş sosyal medya verilerini döndürür.
        Gerçek bir uygulamada bu veriler Twitter, Reddit vb. API'lerden çekilmelidir.
        """
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
        
        # Sorguya göre filtrele
        if query and query.lower() != "all":
            filtered_messages = [msg for msg in all_messages if query.lower() in msg.lower()]
            return filtered_messages
        return all_messages

    def save_to_json(self, data: dict, request_type: str, source: str) -> 'Union[str, None]':
        """
        Gelen veriyi zaman damgalı bir JSON dosyasına kaydeder.

        Args:
            data (dict): Kaydedilecek veri.
            request_type (str): Dosya adını belirlemek için kullanılan istek türü (örn: "BTC,ETH" veya "rising").
            source (str): Veri kaynağı (örn: "cryptopanic", "newsapi").

        Returns:
            str | None: Kaydedilen dosyanın tam yolu veya hata durumunda None.
        """
        if not data or ("posts" not in data and "articles" not in data):
            print("❌ Kaydedilecek haber bulunamadı.")
            return None

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"news_{source}_{request_type.replace(',', '_')}_{timestamp}.json"
        filepath = os.path.join(self.output_dir, filename)

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            print(f"✅ Veri başarıyla {filepath} dosyasına kaydedildi.")
            return filepath
        except IOError as e:
            print(f"❌ Dosyaya yazma hatası: {e}")
            return None

def main():
    """
    Komut satırından haber verilerini çekmek için ana fonksiyon.
    """
    parser = argparse.ArgumentParser(description="Çeşitli API'lerden haber verilerini çeker.")
    parser.add_argument('--source', type=str, choices=['cryptopanic', 'newsapi', 'social_media_sim'], required=True, help='Kullanılacak haber kaynağı.')

    # CryptoPanic argümanları
    cryptopanic_group = parser.add_argument_group('CryptoPanic Argümanları')
    cryptopanic_group.add_argument('--currencies', '-c', type=str, help='CryptoPanic için virgülle ayrılmış para birimi kodları (örn: "BTC,ETH").')
    cryptopanic_group.add_argument('--filter', '-f', type=str, choices=CRYPTO_PANIC_FILTER_OPTIONS, help='CryptoPanic için uygulanacak filtre.')

    # NewsAPI argümanları
    newsapi_group = parser.add_argument_group('NewsAPI Argümanları')
    newsapi_group.add_argument('--query', '-q', type=str, help='NewsAPI için arama sorgusu (örn: "Bitcoin").')
    newsapi_group.add_argument('--language', '-l', type=str, default='en', help="NewsAPI için haber dili (örn: 'en', 'tr'). Varsayılan: 'en'.")
    newsapi_group.add_argument('--sort_by', '-s', type=str, default='relevancy', help="NewsAPI için sıralama ölçütü (relevancy, popularity, publishedAt). Varsayılan: 'relevancy'.")

    # Simüle Sosyal Medya argümanları
    social_media_group = parser.add_argument_group('Simüle Sosyal Medya Argümanları')
    social_media_group.add_argument('--social_query', type=str, help='Simüle sosyal medya için arama sorgusu (örn: "Bitcoin").')

    args = parser.parse_args()

    fetcher = NewsFetcher()
    news_data = None
    request_identifier = ""

    if args.source == 'cryptopanic':
        if not CRYPTO_PANIC_API_KEY:
            print("❌ Lütfen .env dosyasında CRYPTO_PANIC_API_KEY değerini ayarlayın.")
            return
        if not args.currencies and not args.filter:
            print("❌ CryptoPanic için --currencies veya --filter argümanlarından biri gerekli.")
            return
        
        request_identifier = args.currencies if args.currencies else args.filter
        print(f"📰 CryptoPanic'ten haberler çekiliyor ({request_identifier})...")
        news_data = fetcher.fetch_cryptopanic_news(CRYPTO_PANIC_API_KEY, currencies=args.currencies, news_filter=args.filter)
        
        if news_data:
            fetcher.save_to_json(news_data, request_identifier, source='cryptopanic')
            if news_data.get("posts"):
                print("\n--- İlk Haberin Önizlemesi (CryptoPanic) ---")
                print(json.dumps(news_data["posts"][0], indent=4))
                print("--------------------------")

    elif args.source == 'newsapi':
        if not NEWS_API_KEY:
            print("❌ Lütfen .env dosyasında NEWS_API_KEY değerini ayarlayın.")
            return
        if not args.query:
            print("❌ NewsAPI için --query argümanı gerekli.")
            return

        request_identifier = args.query
        print(f"📰 NewsAPI.org'dan haberler çekiliyor ('{request_identifier}')...")
        news_data = fetcher.fetch_news_from_newsapi(NEWS_API_KEY, query=args.query, language=args.language, sort_by=args.sort_by)

        if news_data:
            fetcher.save_to_json(news_data, request_identifier, source='newsapi')
            if news_data.get("articles"):
                print("\n--- İlk Haberin Önizlemesi (NewsAPI.org) ---")
                print(json.dumps(news_data["articles"][0], indent=4))
                print("--------------------------")

    elif args.source == 'social_media_sim':
        if not args.social_query:
            print("❌ Simüle sosyal medya için --social_query argümanı gerekli.")
            return
        request_identifier = args.social_query
        print(f"💬 Simüle sosyal medya verileri çekiliyor ('{request_identifier}')...")
        social_media_messages = fetcher.fetch_simulated_social_media_data(query=args.social_query)
        if social_media_messages:
            print(f"✅ {len(social_media_messages)} adet simüle sosyal medya mesajı bulundu.")
            # Simüle veriyi kaydetmek için bir mekanizma ekleyebilirsiniz
            # fetcher.save_to_json({'messages': social_media_messages}, request_identifier, source='social_media_sim')
            print("\n--- İlk Simüle Mesajın Önizlemesi ---")
            print(social_media_messages[0])
            print("--------------------------")
        else:
            print("❌ Simüle sosyal medya mesajı bulunamadı.")


if __name__ == "__main__":
    main()
