
import pandas as pd
import numpy as np
import ta.volume
import ta.volatility
import logging
from typing import Dict, Any, Tuple

from .base_model import BaseModel
from .. import config

# Loglama yapılandırması
logger = logging.getLogger(__name__)

class VolumeSurgeModel(BaseModel):
    """
    Analyzes volume anomalies and their price impact to generate a score.
    """
    def __init__(self, **kwargs):
        super().__init__()
        self.volume_ma_window = kwargs.get('volume_ma_window', config.VOLUME_SURGE_MA_WINDOW)
        self.deviation_scale = kwargs.get('deviation_scale', config.VOLUME_SURGE_DEVIATION_SCALE)
        self.obv_influence = kwargs.get('obv_influence', config.VOLUME_SURGE_OBV_INFLUENCE)
        self.required_data_points = self.volume_ma_window + 5

    def predict(self, symbol: str, interval: str = "1d", **kwargs) -> Dict[str, Any]:
        logger.info(f"Running '{self.name}' model...")

        # Update parameters if provided in kwargs
        self.volume_ma_window = kwargs.get('volume_ma_window', self.volume_ma_window)
        self.deviation_scale = kwargs.get('deviation_scale', self.deviation_scale)
        self.obv_influence = kwargs.get('obv_influence', self.obv_influence)
        self.required_data_points = self.volume_ma_window + 5

        try:
            data = self.data_fetcher.get_historical_data(symbol, interval, limit=self.required_data_points)
            if data.empty or len(data) < self.required_data_points:
                logger.warning(f"'{self.name}': Not enough data. Returning neutral score.")
                return {'score': 0.0, 'details': f"Not enough data. Need {self.required_data_points} data points, but got {len(data)}."}

            score, details = self._calculate_score(data, self.volume_ma_window)
            logger.info(f"'{self.name}' model result: Score={score:.4f}")
            return {'score': score, 'details': details}
        except Exception as e:
            logger.error(f"An error occurred while running the '{self.name}' model: {e}", exc_info=True)
            return {'score': 0.0, 'details': f"Error during model execution: {e}"}
    def _calculate_score(self, data: pd.DataFrame, volume_ma_window: int) -> Tuple[float, str]:
        data = data.copy()
        details = []
        
        required_columns = ['Close', 'Volume']
        if not all(col in data.columns for col in required_columns):
            return 0.0, "Missing required columns."

        # --- Volume Deviation Score ---
        volume_ma = data['Volume'].rolling(window=volume_ma_window).mean()
        last_volume = data['Volume'].iloc[-1]
        last_volume_ma = volume_ma.iloc[-1]
        
        volume_deviation = 0.0
        if last_volume_ma > 0:
            volume_deviation = (last_volume - last_volume_ma) / last_volume_ma
        
        volume_deviation_score = np.tanh(volume_deviation * self.deviation_scale)
        if volume_deviation > 0.2: details.append(f"Volume Surge ({volume_deviation:.2f})")
        elif volume_deviation < -0.2: details.append(f"Volume Decrease ({volume_deviation:.2f})")

        # --- OBV (On-Balance Volume) Score ---
        obv = ta.volume.on_balance_volume(data['Close'], data['Volume'])
        obv_score = 0.0
        if len(obv) > 1:
            obv_change = np.sign(obv.iloc[-1] - obv.iloc[-2])
            obv_score = obv_change * self.obv_influence
            if obv_change > 0: details.append("OBV Uptrend")
            elif obv_change < 0: details.append("OBV Downtrend")

        # --- Price Change Score ---
        price_change_score = 0.0
        if len(data['Close']) > 1:
            price_change = (data['Close'].iloc[-1] - data['Close'].iloc[-2]) / data['Close'].iloc[-2]
            price_change_score = np.tanh(price_change * 10)

        # --- Final Score ---
        final_score = (volume_deviation_score * 0.5) + (obv_score * 0.5)
        if np.sign(final_score) == np.sign(price_change_score):
            final_score = (final_score + price_change_score) / 2
        
        final_score = float(np.tanh(final_score))
        final_details = ", ".join(details) if details else "Neutral volume signal."
        return final_score, final_details
