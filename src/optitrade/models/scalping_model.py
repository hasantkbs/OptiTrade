import pandas as pd
import numpy as np
import ta.momentum
import ta.trend
import logging
from .. import config
from typing import Dict, Any

logger = logging.getLogger(__name__)

from .base_model import BaseModel

class ScalpingModel(BaseModel):
    """
    Scalping stratejisi için hızlı tepki veren bir model.
    Kısa vadeli hareketli ortalamalar ve RSI gibi göstergeleri kullanır.
    """
    def __init__(self,
                 fast_ma_window: int = 5,
                 slow_ma_window: int = 13,
                 rsi_window: int = 7,
                 rsi_overbought: int = 70,
                 rsi_oversold: int = 30, **kwargs):
        super().__init__(**kwargs)
        self.fast_ma_window = fast_ma_window
        self.slow_ma_window = slow_ma_window
        self.rsi_window = rsi_window
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold

    def predict(self, symbol: str, interval: str = '1m', **kwargs) -> Dict[str, Any]:
        logger.debug(f"ScalpingModel: predict called with interval: {interval}")

        # Interval'e göre pencere boyutlarını ayarla
        if interval == '1m':
            fast_ma_window = 3
            slow_ma_window = 8
            rsi_window = 5
        elif interval == '5m':
            fast_ma_window = 5
            slow_ma_window = 13
            rsi_window = 7
        elif interval == '15m':
            fast_ma_window = 8
            slow_ma_window = 21
            rsi_window = 9
        elif interval == '30m' or interval == '60m' or interval == '1h':
            fast_ma_window = 13
            slow_ma_window = 34
            rsi_window = 14
        else: # 1d, 1wk, 1mo ve diğerleri için varsayılan değerler
            fast_ma_window = self.fast_ma_window
            slow_ma_window = self.slow_ma_window
            rsi_window = self.rsi_window

        try:
            data = self.data_fetcher.get_historical_data(symbol, interval, limit=max(fast_ma_window, slow_ma_window, rsi_window) + 5)
            if data.empty or len(data) < max(fast_ma_window, slow_ma_window, rsi_window):
                logger.warning("ScalpingModel: Yeterli veri yok. Nötr skor döndürülüyor.")
                return {'score': 0.0, 'details': 'Not enough data.'}

            close_prices = data['close']

            # Kısa vadeli hareketli ortalamalar
            fast_ma = ta.trend.sma_indicator(close_prices, window=fast_ma_window)
            slow_ma = ta.trend.sma_indicator(close_prices, window=slow_ma_window)

            # RSI
            rsi = ta.momentum.rsi(close_prices, window=rsi_window)

            score = 0.0

            # MA Kesişimleri
            if not fast_ma.empty and not slow_ma.empty and \
               not pd.isna(fast_ma.iloc[-1]) and not pd.isna(slow_ma.iloc[-1]) and \
               not pd.isna(fast_ma.iloc[-2]) and not pd.isna(slow_ma.iloc[-2]):
                
                # Altın Kesişim (Golden Cross) - Alım sinyali
                if fast_ma.iloc[-1] > slow_ma.iloc[-1] and fast_ma.iloc[-2] <= slow_ma.iloc[-2]:
                    score += 0.5
                # Ölüm Kesişimi (Death Cross) - Satış sinyali
                elif fast_ma.iloc[-1] < slow_ma.iloc[-1] and fast_ma.iloc[-2] >= slow_ma.iloc[-2]:
                    score -= 0.5

            # RSI Aşırı Alım/Satım
            if not rsi.empty and not pd.isna(rsi.iloc[-1]):
                if rsi.iloc[-1] > self.rsi_overbought:
                    score -= 0.3 # Aşırı alım, satış baskısı
                elif rsi.iloc[-1] < self.rsi_oversold:
                    score += 0.3 # Aşırı satım, alış baskısı

            # Skoru -1.0 ile 1.0 arasına normalize et
            return {'score': float(np.tanh(score)), 'details': f'Scalping score: {float(np.tanh(score)):.2f}'}
        except Exception as e:
            logger.error(f"An error occurred while running the '{self.name}' model: {e}", exc_info=True)
            return {'score': 0.0, 'details': f"Error during model execution: {e}"}

