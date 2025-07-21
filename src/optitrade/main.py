import pandas as pd
import numpy as np
import yfinance as yf
import argparse
import requests
import os
from datetime import datetime
from dotenv import load_dotenv

# Modelleri içe aktar
from optitrade.models.price_trend_model import PriceTrendModel
from optitrade.models.volume_surge_model import VolumeSurgeModel
from optitrade.models.news_sentiment_model import NewsSentimentModel
from optitrade.models.social_sentiment_model import SocialSentimentModel
from optitrade.models.support_resistance_model import SupportResistanceModel
from optitrade.models.divergence_detection_model import DivergenceDetectionModel
from optitrade.models.event_impact_model import EventImpactModel
from optitrade.models.market_condition_classifier import MarketConditionClassifier
from optitrade.scoring.scoring_engine import ScoringEngine
from optitrade.alerting.alert_system import AlertSystem
from optitrade.utils.data_fetcher import NewsFetcher, NEWS_API_KEY

# .env dosyasındaki değişkenleri yükle
load_dotenv()

# Alpha Vantage için API anahtarı (eğer .env'de varsa)
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")

def _fetch_data_alpha_vantage(symbol: str, api_key: str, outputsize: str = 'full') -> pd.DataFrame:
    """
    Alpha Vantage API'sinden hisse senedi verilerini çeker.
    outputsize: 'compact' (son 100 gün) veya 'full' (20 yıla kadar).
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
        response.raise_for_status() # HTTP hataları için istisna fırlat
        data = response.json()

        if "Time Series (Daily)" not in data:
            print(f"Hata: Alpha Vantage'dan veri çekilemedi veya geçersiz sembol: {symbol}. Hata: {data.get('Note', data)}")
            return pd.DataFrame()

        df = pd.DataFrame.from_dict(data["Time Series (Daily)"], orient="index")
        df = df.rename(columns={
            "1. open": "Open",
            "2. high": "High",
            "3. low": "Low",
            "4. close": "Close",
            "5. adjusted close": "Adj Close",
            "6. volume": "Volume"
        })
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        df = df.astype(float) # Tüm sütunları float'a dönüştür
        return df
    except requests.exceptions.RequestException as e:
        print(f"Alpha Vantage API hatası: {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"Alpha Vantage verisi işlenirken hata oluştu: {e}")
        return pd.DataFrame()

def run_analysis(symbol: str, period: str, interval: str, data_source: str, av_api_key: str, news_query: str, news_lang: str):
    print(f"\n--- OptiTrade Analiz Motoru Başlatılıyor ({symbol}) ---")

    # 1. Piyasa Verilerini Çekme
    market_data = pd.DataFrame()
    if data_source == 'yfinance':
        try:
            ticker = yf.Ticker(symbol)
            market_data = ticker.history(period=period, interval=interval)
            print(f"✅ {symbol} için yfinance verileri çekildi.")
        except Exception as e:
            print(f"❌ yfinance ile veri çekilirken hata oluştu: {e}")
    elif data_source == 'alpha_vantage':
        if not av_api_key:
            print("❌ Alpha Vantage için API anahtarı gerekli (--av_api_key veya .env).")
        else:
            outputsize = 'full' # veya 'compact'
            market_data = _fetch_data_alpha_vantage(symbol, av_api_key, outputsize=outputsize)
            if not market_data.empty:
                print(f"✅ {symbol} için Alpha Vantage verileri çekildi.")

    if market_data.empty:
        print("❌ Piyasa verileri çekilemedi. Analiz yapılamıyor.")
        return

    # 2. Haber Verilerini Çekme (NewsAPI.org)
    news_headlines = []
    fetcher = NewsFetcher() # NewsFetcher burada başlatılmalı
    if NEWS_API_KEY:
        news_data = fetcher.fetch_news_from_newsapi(NEWS_API_KEY, query=news_query, language=news_lang)
        if news_data and news_data.get('articles'):
            news_headlines = [article.get('title', '') for article in news_data['articles'] if article.get('title')]
            print(f"✅ NewsAPI.org'dan {len(news_headlines)} adet haber başlığı çekildi.")
        else:
            print("❌ NewsAPI.org'dan haber çekilemedi veya haber bulunamadı.")
    else:
        print("❌ NEWS_API_KEY .env dosyasında ayarlanmamış. Haber duygu analizi atlanıyor.")

    # 3. Modelleri Başlatma
    price_trend_model = PriceTrendModel()
    volume_surge_model = VolumeSurgeModel()
    news_sentiment_model = NewsSentimentModel()
    social_sentiment_model = SocialSentimentModel()
    support_resistance_model = SupportResistanceModel()
    divergence_detection_model = DivergenceDetectionModel()
    event_impact_model = EventImpactModel()
    market_condition_classifier = MarketConditionClassifier()
    scoring_engine = ScoringEngine()
    alert_system = AlertSystem()

    # 4. Skorları Hesaplama
    model_scores = {}
    
    print("📊 market_data tipi:", type(market_data))
    print("📊 market_data kolonları:", market_data.columns if hasattr(market_data, 'columns') else "Yok")

    # PriceTrendModel için sadece 'Close' sütununu kullan
    if isinstance(market_data, pd.DataFrame) and 'Close' in market_data.columns:
        price_series = market_data['Close']

        try:
            model_scores['price_trend_score'] = price_trend_model.generate_score(price_series)
            print(f"✅ Fiyat Trend Skoru başarıyla hesaplandı: {model_scores['price_trend_score']:.2f}")
        except Exception as e:
            print("❌ Fiyat Trend Skoru hesaplanırken hata oluştu:", str(e))
            model_scores['price_trend_score'] = 0.0  # veya None
    else:
        print("❌ 'market_data' DataFrame değil ya da 'Close' sütunu bulunamadı.")
        model_scores['price_trend_score'] = 0.0  # veya hata yönetimine göre başka bir şey


    # VolumeSurgeModel
    volume_score, impact_score = volume_surge_model.generate_score(market_data)
    model_scores['volume_surge_score'] = volume_score # Sadece hacim skorunu kullanıyorum
    print(f"  - Hacim Skoru: {model_scores['volume_surge_score']:.2f}")
    # Volatiliteyle normalize edilmiş etkiyi ayrı olarak tutabiliriz veya ScoringEngine'e ekleyebiliriz.
    # Şimdilik sadece hacim skorunu nihai skora dahil ediyorum.

    # NewsSentimentModel
    if news_headlines:
        model_scores['news_sentiment_score'] = news_sentiment_model.analyze_sentiment(news_headlines)
    else:
        model_scores['news_sentiment_score'] = 0.0 # Haber yoksa nötr
    print(f"  - Haber Duygu Skoru: {model_scores['news_sentiment_score']:.2f}")

    # SocialSentimentModel
    # Simüle edilmiş sosyal medya verilerini çek
    social_media_messages = fetcher.fetch_simulated_social_media_data(query=symbol) # Sembole göre filtrele
    if social_media_messages:
        social_sentiment_scores = [social_sentiment_model.analyze_sentiment_for_text(msg) for msg in social_media_messages]
        if social_sentiment_scores:
            model_scores['social_sentiment_score'] = np.mean(social_sentiment_scores)
        else:
            model_scores['social_sentiment_score'] = 0.0
    else:
        model_scores['social_sentiment_score'] = 0.0 # Mesaj yoksa nötr
    print(f"  - Sosyal Duygu Skoru: {model_scores['social_sentiment_score']:.2f}")

    # SupportResistanceModel
    model_scores['support_resistance_score'] = support_resistance_model.generate_proximity_score(market_data)
    print(f"  - Destek-Direnç Yakınlık Skoru: {model_scores['support_resistance_score']:.2f}")

    # DivergenceDetectionModel
    # RSI uyumsuzluğunu kontrol edelim
    divergence_result = divergence_detection_model.detect_divergence(market_data, indicator_type='rsi')
    model_scores['divergence_score'] = divergence_result['score']
    print(f"  - Uyumsuzluk Skoru: {model_scores['divergence_score']:.2f}")

    # EventImpactModel
    model_scores['event_impact_score'] = event_impact_model.calculate_impact(datetime.now())
    print(f"  - Olay Etki Skoru: {model_scores['event_impact_score']:.2f}")

    # MarketConditionClassifier
    # VIX verisini çek
    vix_val = None
    try:
        vix_data = yf.download('^VIX', period='5d', interval='1d', auto_adjust=True)
        if not vix_data.empty:
            vix_val = float(vix_data['Close'].iloc[-1].item())
    except Exception as e:
        print(f"❌ VIX verisi çekilirken hata oluştu: {e}. Varsayılan 20.0 kullanılıyor.")
        vix_val = 20.0
    
    # BTC Dominance ve Total Market Cap için varsayılan değerler (gerçek uygulamada API'den çekilmeli)
    btc_dom_val = 0.50 # %50
    mcap_val = 1_500_000_000_000 # 1.5 Trilyon USD

    market_condition = market_condition_classifier.classify_market_condition(vix_val, btc_dom_val, mcap_val)
    model_scores['market_condition_score'] = market_condition
    print(f"  - Piyasa Koşulu: {market_condition.upper()}")

    # 5. Nihai Skoru Hesaplama
    final_prediction_score = scoring_engine.generate_final_score(model_scores)
    print(f"\n--- Nihai Tahmin Sonucu ---")
    print(f"Nihai Tahmin Skoru: {final_prediction_score:.2f}")

    # 6. Uyarı Sistemi
    alert_message = alert_system.check_for_alert(final_prediction_score)
    print(f"Uyarı: {alert_message}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='OptiTrade Analiz Motoru: Çeşitli modelleri kullanarak piyasa analizi yapar.')
    parser.add_argument('--symbol', type=str, default='BTC-USD', help='Hisse senedi/kripto para sembolü (örn: BTC-USD, AAPL). Varsayılan: BTC-USD')
    parser.add_argument('--period', type=str, default='1y', help='Veri çekme periyodu (yfinance için: 1y, 6mo, 1mo). Varsayılan: 1y')
    parser.add_argument('--interval', type=str, default='1d', help='Veri çekme aralığı (yfinance için: 1d, 1wk, 1mo). Varsayılan: 1d')
    parser.add_argument('--data_source', type=str, default='yfinance', choices=['yfinance', 'alpha_vantage'], help='Piyasa verisi kaynağı (yfinance veya alpha_vantage). Varsayılan: yfinance')
    parser.add_argument('--av_api_key', type=str, default=ALPHA_VANTAGE_API_KEY, help='Alpha Vantage API anahtarı (data_source alpha_vantage ise gerekli).')
    parser.add_argument('--news_query', type=str, default='Bitcoin', help='NewsAPI.org için haber arama sorgusu. Varsayılan: Bitcoin')
    parser.add_argument('--news_lang', type=str, default='en', help='NewsAPI.org için haber dili. Varsayılan: en')

    args = parser.parse_args()

    # run_analysis fonksiyonunu doğrudan çağır
    run_analysis(args.symbol, args.period, args.interval, args.data_source, args.av_api_key, args.news_query, args.news_lang)