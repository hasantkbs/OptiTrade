
import logging
import pandas as pd
import ta.volatility
from typing import Dict, Any

from .base_model import BaseModel
from .. import config

logger = logging.getLogger(__name__)

class BollingerBandsModel(BaseModel):
    """
    Bollinger Bands (BB) göstergesini analiz ederek bir ticaret sinyali üretir.
    """
    def __init__(self, **kwargs):
        super().__init__()
        self.window = kwargs.get('window', config.BB_WINDOW)
        self.window_dev = kwargs.get('window_dev', config.BB_WINDOW_DEV)
        self.required_data_points = self.window

    def predict(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """
        Verilen veri setine göre Bollinger Bands sinyalini hesaplar.

        Returns:
            Dict[str, Any]: 'signal' (Overbought, Oversold, Neutral), 'details', ve 'values' içeren bir sözlük.
        """
        logger.info(f"Running '{self.name}' model...")

        if data.empty or len(data) < self.required_data_points:
            logger.warning(f"'{self.name}': Yeterli veri yok. {self.required_data_points} adet gerekirken {len(data)} adet var.")
            return {'signal': 'Neutral', 'details': 'Yetersiz veri', 'values': {}}

        try:
            data = data.copy()

            # Bollinger Bands hesaplamaları
            indicator_bb = ta.volatility.BollingerBands(close=data["Close"], window=self.window, window_dev=self.window_dev)
            
            data['bb_high'] = indicator_bb.bollinger_hband()
            data['bb_low'] = indicator_bb.bollinger_lband()
            data['bb_mid'] = indicator_bb.bollinger_mavg()

            if data['bb_high'].isnull().all():
                return {'signal': 'Neutral', 'details': 'Bollinger Bands hesaplanamadı', 'values': {}}

            # Son değerleri al
            last_close = data['Close'].iloc[-1]
            last_high_band = data['bb_high'].iloc[-1]
            last_low_band = data['bb_low'].iloc[-1]

            signal = 'Neutral'
            details = f"Fiyat: {last_close:.2f}, Üst Band: {last_high_band:.2f}, Alt Band: {last_low_band:.2f}"

            # Sinyalleri kontrol et
            if last_close > last_high_band:
                signal = 'Overbought' # Aşırı Alım
                details = f"Aşırı Alım Sinyali: Fiyat ({last_close:.2f}) üst bandı ({last_high_band:.2f}) aştı."
            elif last_close < last_low_band:
                signal = 'Oversold' # Aşırı Satım
                details = f"Aşırı Satım Sinyali: Fiyat ({last_close:.2f}) alt bandın ({last_low_band:.2f}) altına düştü."

            logger.info(f"'{self.name}' model result: {signal} - {details}")

            return {
                'signal': signal,
                'details': details,
                'values': {
                    'high_band': last_high_band,
                    'low_band': last_low_band,
                    'middle_band': data['bb_mid'].iloc[-1]
                }
            }

        except Exception as e:
            logger.error(f"'{self.name}' modeli çalışırken hata oluştu: {e}", exc_info=True)
            return {'signal': 'Neutral', 'details': f"Model hatası: {e}", 'values': {}}
