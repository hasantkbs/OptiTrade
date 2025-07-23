import sys
import os

# Add the project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))


import argparse
import logging
from datetime import datetime

# OptiTrade modüllerini içe aktar
from optitrade import config
from optitrade.models.registry import initialize_models
from optitrade.models.main import calculate_all_model_scores
from optitrade.scoring.scoring_engine import ScoringEngine
from optitrade.alerting.alert_system import AlertSystem
from optitrade.utils.data_fetcher import MarketDataFetcher, NewsFetcher

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

def run_analysis(symbol: str, period: str, interval: str, data_source: str, news_query: str, news_lang: str):
    logger.info(f"--- OptiTrade Analiz Motoru Başlatılıyor ({symbol}) ---")

    # 1. Veri Çekme
    market_fetcher = MarketDataFetcher()
    market_data = market_fetcher.fetch_market_data(
        symbol=symbol, period=period, interval=interval, data_source=data_source
    )
    if market_data.empty:
        logger.error("Piyasa verileri çekilemedi. Analiz yapılamıyor.")
        return
    logger.info(f"{symbol} için piyasa verileri başarıyla çekildi veya önbellekten okundu.")

    news_fetcher = NewsFetcher()
    news_headlines = []
    if config.NEWS_API_KEY:
        news_data = news_fetcher.fetch_news_from_newsapi(config.NEWS_API_KEY, query=news_query, language=news_lang)
        if news_data and news_data.get('articles'):
            news_headlines = [article.get('title', '') for article in news_data['articles'] if article.get('title')]
            logger.info(f"NewsAPI.org'dan {len(news_headlines)} adet haber başlığı çekildi.")
    else:
        logger.warning("NEWS_API_KEY ayarlanmamış. Haber duygu analizi atlanıyor.")

    # 2. Modelleri ve Sistemleri Başlatma
    models = initialize_models()
    scoring_engine = ScoringEngine()
    alert_system = AlertSystem()

    # 3. Merkezi Fonksiyon ile Skorları Hesaplama
    model_scores = calculate_all_model_scores(
        historical_data=market_data, 
        models=models, 
        news_headlines=news_headlines,
        social_media_query=symbol
    )

    # 4. Nihai Skoru Hesaplama
    final_prediction_score = scoring_engine.generate_final_score(model_scores)
    logger.info(f"--- Nihai Tahmin Sonucu ---")
    logger.info(f"Nihai Tahmin Skoru: {final_prediction_score:.2f}")

    # 5. Uyarı Sistemi
    alert_message = alert_system.check_for_alert(final_prediction_score)
    logger.info(f"Uyarı: {alert_message}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='OptiTrade Analiz Motoru: Çeşitli modelleri kullanarak piyasa analizi yapar.')
    parser.add_argument('--symbol', type=str, default='BTC-USD', help='Hisse senedi/kripto para sembolü (örn: BTC-USD, AAPL). Varsayılan: BTC-USD')
    parser.add_argument('--period', type=str, default='1y', help='Veri çekme periyodu (yfinance için: 1y, 6mo, 1mo). Varsayılan: 1y')
    parser.add_argument('--interval', type=str, default='1d', choices=['1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo'], help='Veri çekme aralığı (yfinance için: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo). Varsayılan: 1d')
    parser.add_argument('--data_source', type=str, default='yfinance', choices=['yfinance', 'alpha_vantage'], help='Piyasa verisi kaynağı (yfinance veya alpha_vantage). Varsayılan: yfinance')
    parser.add_argument('--av_api_key', type=str, help='Alpha Vantage API anahtarı (data_source alpha_vantage ise gerekli).')
    parser.add_argument('--news_query', type=str, default='Bitcoin', help='NewsAPI.org için haber arama sorgusu. Varsayılan: Bitcoin')
    parser.add_argument('--news_lang', type=str, default='en', help='NewsAPI.org için haber dili. Varsayılan: en')

    args = parser.parse_args()

    # run_analysis fonksiyonunu doğrudan çağır
    run_analysis(args.symbol, args.period, args.interval, args.data_source, args.news_query, args.news_lang)