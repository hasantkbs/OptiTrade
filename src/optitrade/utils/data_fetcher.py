
import os
import json
import argparse
from datetime import datetime
import requests
from dotenv import load_dotenv
from typing import Union

# .env dosyasındaki değişkenleri yükle
load_dotenv()

# API anahtarını ortam değişkenlerinden al
API_KEY = os.getenv("CRYPTO_PANIC_API_KEY")

# API'nin desteklediği filtre seçenekleri
FILTER_OPTIONS = [
    "rising", "hot", "bullish", "bearish", "important", "saved", "lol"
]

class NewsFetcher:
    """
    CryptoPanic API'sinden haber verilerini çekmek ve yönetmek için bir sınıf.
    """
    def __init__(self, api_key: str, output_dir: str = "data/raw_news"):
        """
        Fetcher'ı başlatır.

        Args:
            api_key (str): CryptoPanic API anahtarı.
            output_dir (str): JSON dosyalarının kaydedileceği dizin.
        """
        if not api_key:
            raise ValueError("API anahtarı bulunamadı. Lütfen .env dosyasında CRYPTO_PANIC_API_KEY değişkenini ayarlayın.")
        self.api_key = api_key
        self.base_url = "https://cryptopanic.com/api/developer/v2/posts/"
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def fetch_news(self, currencies: str = None, news_filter: str = None) -> 'Union[dict, None]':
        """
        Belirtilen para birimleri veya filtreye göre haberleri çeker.

        Args:
            currencies (str, optional): Virgülle ayrılmış para birimi kodları (örn: "BTC,ETH").
            news_filter (str, optional): Uygulanacak filtre (örn: "rising", "bullish").

        Returns:
            dict | None: API'den gelen yanıt verisi veya hata durumunda None.
        """
        params = {"auth_token": self.api_key}
        if currencies:
            params["currencies"] = currencies
        if news_filter:
            if news_filter not in FILTER_OPTIONS:
                print(f"❌ Geçersiz filtre: {news_filter}. Kullanılabilir seçenekler: {FILTER_OPTIONS}")
                return None
            params["filter"] = news_filter

        try:
            response = requests.get(self.base_url, params=params)
            response.raise_for_status()  # HTTP hata kodları için bir istisna fırlatır
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ API Hatası: {e}")
            return None

    def save_to_json(self, data: dict, request_type: str) -> 'Union[str, None]':
        """
        Gelen veriyi zaman damgalı bir JSON dosyasına kaydeder.

        Args:
            data (dict): Kaydedilecek veri.
            request_type (str): Dosya adını belirlemek için kullanılan istek türü (örn: "BTC,ETH" veya "rising").

        Returns:
            str | None: Kaydedilen dosyanın tam yolu veya hata durumunda None.
        """
        if not data or "results" not in data:
            print("❌ Kaydedilecek haber bulunamadı.")
            return None

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"news_{request_type.replace(',', '_')}_{timestamp}.json"
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
    parser = argparse.ArgumentParser(description="CryptoPanic API'sinden haber verilerini çeker.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--currencies', '-c', type=str, help='Virgülle ayrılmış para birimi kodları (örn: "BTC,ETH").')
    group.add_argument('--filter', '-f', type=str, choices=FILTER_OPTIONS, help='Uygulanacak haber filtresi.')

    args = parser.parse_args()

    if not API_KEY:
        print("❌ Lütfen projenin ana dizininde bir .env dosyası oluşturun ve CRYPTO_PANIC_API_KEY değerini ayarlayın.")
        return

    fetcher = NewsFetcher(api_key=API_KEY, output_dir="../../data/raw_news")
    
    request_identifier = ""
    news_data = None

    if args.currencies:
        print(f"📰 {args.currencies} için haberler çekiliyor...")
        request_identifier = args.currencies
        news_data = fetcher.fetch_news(currencies=args.currencies)
    elif args.filter:
        print(f"📰 '{args.filter}' filtresine göre haberler çekiliyor...")
        request_identifier = args.filter
        news_data = fetcher.fetch_news(news_filter=args.filter)

    if news_data:
        fetcher.save_to_json(news_data, request_identifier)
        # İlk haberin önizlemesini göster
        if news_data.get("results"):
            print("\n--- İlk Haberin Önizlemesi ---")
            print(json.dumps(news_data["results"][0], indent=4))
            print("--------------------------")


if __name__ == "__main__":
    main()
