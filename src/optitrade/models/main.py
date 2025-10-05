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

def calculate_all_model_scores(historical_data: pd.DataFrame, models: dict, news_headlines: list = [], social_media_query: str = None, interval: str = '1d') -> pd.DataFrame:
    """
    Verilen geçmiş veriler ve başlatılmış modelleri kullanarak tüm model skorlarını hesaplar.

    Args:
        historical_data (pd.DataFrame): Analiz edilecek piyasa verileri.
        models (dict): Başlatılmış model nesnelerini içeren sözlük.
        news_headlines (list, optional): Analiz edilecek haber başlıkları.
        social_media_query (str, optional): Sosyal medya verilerini filtrelemek için sorgu.

    Returns:
        pd.DataFrame: Her model için hesaplanmış skorları içeren bir DataFrame.
    """
    all_model_scores = pd.DataFrame(index=historical_data.index)

    # MarketConditionClassifier
    if 'market_condition_classifier' in models:
        try:
            market_regimes = models['market_condition_classifier'].generate_score(
                data=historical_data
            )
            all_model_scores['market_condition_classifier_regime'] = market_regimes
        except Exception as e:
            logger.error(f"Piyasa Durumu Sınıflandırıcı rejimi hesaplanırken hata: {e}")
            all_model_scores['market_condition_classifier_regime'] = "Unknown" # Assign a Series of "Unknown"

    # PriceTrendModel
    try:
        price_trend_scores = models['price_trend'].generate_score(
            data=historical_data  # Pass the full DataFrame
        )
        all_model_scores['price_trend_score'] = price_trend_scores
    except Exception as e:
        logger.error(f"Fiyat Trend Skoru hesaplanırken hata: {e}")
        all_model_scores['price_trend_score'] = 0.0 # Assign a Series of zeros

    logger.info(f"--- Model Skorları Hesaplanıyor ---")
    # Log the last score for brevity, or average/min/max
    if 'price_trend_score' in all_model_scores and not all_model_scores['price_trend_score'].empty:
        logger.info(f"  - Price Trend Score (latest): {all_model_scores['price_trend_score'].iloc[-1]:.2f}")
    if 'market_condition_classifier_regime' in all_model_scores and not all_model_scores['market_condition_classifier_regime'].empty:
        logger.info(f"  - Market Condition Regime (latest): {all_model_scores['market_condition_classifier_regime'].iloc[-1]}")
    else:
        logger.info(f"  - Price Trend Score: Not available")


    return all_model_scores
