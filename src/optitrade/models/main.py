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
        model_scores['price_trend_score'] = models['price_trend'].generate_score(
            data=historical_data  # Pass the full DataFrame
        )
    except Exception as e:
        logger.error(f"Fiyat Trend Skoru hesaplanırken hata: {e}")
        model_scores['price_trend_score'] = 0.0

    logger.info(f"--- Model Skorları Hesaplanıyor ---")
    logger.info(f"  - Price Trend Score: {model_scores.get('price_trend_score', 0.0):.2f}")

    return model_scores
