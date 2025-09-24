
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
import logging
from typing import Dict, List, Any, Tuple

from .base_model import BaseModel
from .. import config

# Loglama yapılandırması
logger = logging.getLogger(__name__)

class SupportResistanceModel(BaseModel):
    """
    Analyzes support and resistance levels in price data to generate a score.
    """
    def __init__(self):
        super().__init__()
        self.order = config.SUPPORT_RESISTANCE_FRACTAL_WINDOW
        self.tolerance = 0.01 # 1%
        self.required_data_points = self.order * 2 + 5

    def generate_score(self, data: pd.DataFrame) -> float:
        logger.info(f"Running '{self.name}' model...")

        if data.empty or len(data) < self.required_data_points:
            logger.warning(f"'{self.name}': Not enough data. Returning neutral score (0.0).")
            return 0.0

        try:
            result = self._calculate_score_and_levels(data['Close'], self.order)
            logger.info(f"'{self.name}' model result: Score={result['score']:.4f}")
            return result['score']
        except Exception as e:
            logger.error(f"An error occurred while running the '{self.name}' model: {e}", exc_info=True)
            return 0.0

    def _find_levels(self, price_series: pd.Series, order: int) -> Tuple[List[float], List[float]]:
        local_min_indices = argrelextrema(price_series.values, np.less_equal, order=order)[0]
        local_max_indices = argrelextrema(price_series.values, np.greater_equal, order=order)[0]
        
        supports = price_series.iloc[local_min_indices].tolist()
        resistances = price_series.iloc[local_max_indices].tolist()
        return supports, resistances

    def _calculate_score_and_levels(self, price_series: pd.Series, order: int) -> Dict[str, Any]:
        current_price = price_series.iloc[-1]
        supports, resistances = self._find_levels(price_series, order)

        if not supports and not resistances:
            return {
                "score": 0.0, 
                "details": "Support/Resistance levels not found.",
                "closest_support": None,
                "closest_resistance": None
            }

        closest_support = min(supports, key=lambda x: abs(x - current_price)) if supports else None
        closest_resistance = min(resistances, key=lambda x: abs(x - current_price)) if resistances else None

        support_score = 0.0
        resistance_score = 0.0
        details = []

        if closest_support:
            distance_to_support = abs(current_price - closest_support) / current_price
            if distance_to_support < self.tolerance:
                support_score = (1 - (distance_to_support / self.tolerance)) * 0.9
                details.append(f"Near support level ({closest_support:.2f})")

        if closest_resistance:
            distance_to_resistance = abs(current_price - closest_resistance) / current_price
            if distance_to_resistance < self.tolerance:
                resistance_score = -(1 - (distance_to_resistance / self.tolerance)) * 0.9
                details.append(f"Near resistance level ({closest_resistance:.2f})")

        final_score = support_score + resistance_score
        final_details = ", ".join(details) if details else "Neutral support/resistance signal."
        
        return {
            "score": final_score,
            "details": final_details,
            "closest_support": closest_support,
            "closest_resistance": closest_resistance
        }
