
import logging
import pandas as pd
import ta.trend
from typing import Dict, Any

from .base_model import BaseModel
from .. import config

logger = logging.getLogger(__name__)

class MACDModel(BaseModel):
    """
    MACD (Moving Average Convergence Divergence) göstergesini analiz ederek bir ticaret sinyali üretir.
    """
    def __init__(self, **kwargs):
        super().__init__()
        self.fast_period = kwargs.get('fast_period', config.MACD_FAST_PERIOD)
        self.slow_period = kwargs.get('slow_period', config.MACD_SLOW_PERIOD)
        self.signal_period = kwargs.get('signal_period', config.MACD_SIGNAL_PERIOD)
        self.required_data_points = self.slow_period + self.signal_period

    def predict(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """
        Verilen veri setine göre MACD sinyalini hesaplar.

        Returns:
            Dict[str, Any]: 'signal' (Bullish, Bearish, Neutral), 'details', ve 'values' içeren bir sözlük.
        """
        logger.info(f"Running '{self.name}' model...")
        
        if data.empty or len(data) < self.required_data_points:
            logger.warning(f"'{self.name}': Yeterli veri yok. {self.required_data_points} adet gerekirken {len(data)} adet var.")
            return {'signal': 'Neutral', 'details': 'Yetersiz veri', 'values': {}}

        try:
            data = data.copy()

            # MACD hesaplamaları
            macd_line = ta.trend.macd(data['Close'], window_slow=self.slow_period, window_fast=self.fast_period)
            signal_line = ta.trend.macd_signal(data['Close'], window_slow=self.slow_period, window_fast=self.fast_period, window_sign=self.signal_period)
            
            if macd_line is None or signal_line is None or macd_line.isnull().all() or signal_line.isnull().all():
                return {'signal': 'Neutral', 'details': 'MACD hesaplanamadı', 'values': {}}

            # Son iki periyottaki değerleri al
            last_macd = macd_line.iloc[-1]
            prev_macd = macd_line.iloc[-2]
            last_signal = signal_line.iloc[-1]
            prev_signal = signal_line.iloc[-2]

            signal = 'Neutral'
            details = f"MACD: {last_macd:.2f}, Signal: {last_signal:.2f}"

            # Kesişimleri kontrol et
            if prev_macd < prev_signal and last_macd > last_signal:
                signal = 'Bullish'
                details = f"Yükseliş Sinyali: MACD ({last_macd:.2f}) sinyal çizgisini ({last_signal:.2f}) yukarı kesti."
            elif prev_macd > prev_signal and last_macd < last_signal:
                signal = 'Bearish'
                details = f"Düşüş Sinyali: MACD ({last_macd:.2f}) sinyal çizgisini ({last_signal:.2f}) aşağı kesti."

            logger.info(f"'{self.name}' model result: {signal} - {details}")
            
            return {
                'signal': signal, 
                'details': details,
                'values': {
                    'macd': last_macd,
                    'signal_line': last_signal
                }
            }

        except Exception as e:
            logger.error(f"'{self.name}' modeli çalışırken hata oluştu: {e}", exc_info=True)
            return {'signal': 'Neutral', 'details': f"Model hatası: {e}", 'values': {}}
