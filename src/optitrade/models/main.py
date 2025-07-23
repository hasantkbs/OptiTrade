# src/optitrade/models/main.py

"""
Bu modül, tüm modelleri çalıştıran ve skorları hesaplayan merkezi mantığı içerir.
"""

import pandas as pd
import numpy as np
from datetime import datetime
import yfinance as yf # yfinance eklendi
import logging
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

def calculate_all_model_scores(historical_data: pd.DataFrame, models: dict, news_headlines: list = [], social_media_query: str = None, interval: str = '1d') -> dict:
    """
    Verilen geçmiş veriler ve başlatılmış modelleri kullanarak tüm model skorlarını hesaplar.

    Args:
        historical_data (pd.DataFrame): Analiz edilecek piyasa verileri.
        models (dict): Başlatılmış model nesnelerini içeren sözlük.
        news_headlines (list, optional): Analiz edilecek haber başlıkları.
        social_media_query (str, optional): Sosyal medya verilerini filtrelemek için sorgu.

    Returns:
        dict: Her model için hesaplanmış skorları içeren bir sözlük.
    """
    model_scores = {}

    # PriceTrendModel
    try:
        model_scores['price_trend_score'] = models["price_trend"].generate_score(historical_data['Close'], interval=interval)
    except Exception as e:
        logger.error(f"Fiyat Trend Skoru hesaplanırken hata: {e}")
        model_scores['price_trend_score'] = 0.0

    # VolumeSurgeModel
    try:
        volume_score, _ = models["volume_surge"].generate_score(historical_data, interval=interval)
        model_scores['volume_surge_score'] = volume_score
    except Exception as e:
        logger.error(f"Hacim Skoru hesaplanırken hata: {e}")
        model_scores['volume_surge_score'] = 0.0

    # NewsSentimentModel
    if news_headlines:
        model_scores['news_sentiment_score'] = models["news_sentiment"].analyze_sentiment(news_headlines)
    else:
        model_scores['news_sentiment_score'] = 0.0

    # SocialSentimentModel (simüle edilmiş)
    # Gerçek uygulamada, bu kısım bir data_fetcher çağrısı içermelidir.
    # Şimdilik, basitlik adına burada bırakıyoruz.
    social_media_messages = ["Simulated positive message for testing.", "Simulated negative message."]
    if social_media_messages:
        social_sent_scores = [models["social_sentiment"].analyze_sentiment_for_text(msg) for msg in social_media_messages]
        model_scores['social_sentiment_score'] = np.mean(social_sent_scores) if social_sent_scores else 0.0
    else:
        model_scores['social_sentiment_score'] = 0.0

    # SupportResistanceModel
    try:
        model_scores['support_resistance_score'] = models["support_resistance"].generate_proximity_score(historical_data, interval=interval)
    except Exception as e:
        logger.error(f"Destek-Direnç Skoru hesaplanırken hata: {e}")
        model_scores['support_resistance_score'] = 0.0

    # DivergenceDetectionModel
    try:
        divergence_result = models["divergence_detection"].detect_divergence(historical_data, indicator_type='rsi', interval=interval)
        model_scores['divergence_score'] = divergence_result['score']
    except Exception as e:
        logger.error(f"Uyumsuzluk Skoru hesaplanırken hata: {e}")
        model_scores['divergence_score'] = 0.0

    # EventImpactModel
    model_scores['event_impact_score'] = models["event_impact"].calculate_impact(datetime.now())

    # ScalpingModel
    try:
        model_scores['scalping_score'] = models["scalping"].generate_score(historical_data, interval=interval)
    except Exception as e:
        logger.error(f"Scalping Skoru hesaplanırken hata: {e}")
        model_scores['scalping_score'] = 0.0

    # MarketConditionClassifier
    # VIX verisini çek
    vix_val = None
    try:
        vix_data = yf.download('^VIX', period='5d', interval='1d', auto_adjust=True)
        if not vix_data.empty:
            vix_val = float(vix_data['Close'].iloc[-1].item())
    except Exception as e:
        logger.error(f"VIX verisi çekilirken hata oluştu: {e}. Varsayılan 20.0 kullanılıyor.")
        vix_val = 20.0
    
    # BTC Dominance ve Total Market Cap için varsayılan değerler (gerçek uygulamada API'den çekilmeli)
    btc_dom_val = 0.50 # %50
    mcap_val = 1_500_000_000_000 # 1.5 Trilyon USD

    market_condition = models["market_condition"].classify_market_condition(vix_val, btc_dom_val, mcap_val)
    model_scores['market_condition_score'] = market_condition

    # Hesaplanan skorları yazdırma
    logger.info("--- Model Skorları Hesaplanıyor ---")
    for name, score in model_scores.items():
        if isinstance(score, float):
            logger.info(f"  - {name.replace('_', ' ').title()}: {score:.2f}")
        else:
            logger.info(f"  - {name.replace('_', ' ').title()}: {score}")
            
    return model_scores
