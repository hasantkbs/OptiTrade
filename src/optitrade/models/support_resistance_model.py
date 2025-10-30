
import logging
import pandas as pd
from scipy.signal import argrelextrema
import numpy as np
from typing import Dict, Any

from .base_model import BaseModel
from .. import config

logger = logging.getLogger(__name__)

class SupportResistanceModel(BaseModel):
    """
    Calculates support and resistance levels based on recent fractals.
    """
    def __init__(self, **kwargs):
        super().__init__()
        self.fractal_window = kwargs.get('fractal_window', config.SUPPORT_RESISTANCE_FRACTAL_WINDOW)

    def predict(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        logger.info(f"Running '{self.name}' model...")
        
        if data.empty or len(data) < self.fractal_window * 2 + 1:
            return {'score': 0.0, 'details': 'Not enough data for fractal analysis.'}

        # Find local minima and maxima
        local_min = argrelextrema(data['Low'].values, np.less_equal, order=self.fractal_window)[0]
        local_max = argrelextrema(data['High'].values, np.greater_equal, order=self.fractal_window)[0]

        if len(local_min) == 0 or len(local_max) == 0:
            return {'score': 0.0, 'details': 'No support/resistance levels found.'}

        # Get the most recent significant support and resistance
        support = data['Low'][local_min[-1]]
        resistance = data['High'][local_max[-1]]
        last_close = data['Close'].iloc[-1]

        # Simple scoring logic
        score = 0.0
        if last_close < support:
            score = 0.3  # Potential bounce
        elif last_close > resistance:
            score = -0.3 # Potential rejection
        else:
            # Score based on proximity to levels
            if resistance > support:
                score = -1 * (2 * (last_close - support) / (resistance - support) - 1)

        details = f"Support: {support:.2f}, Resistance: {resistance:.2f}"
        logger.info(f"'{self.name}' model result: {details}")
        return {'score': score, 'details': details, 'support': support, 'resistance': resistance}
