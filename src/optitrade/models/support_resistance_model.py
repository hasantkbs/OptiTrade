
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
    def __init__(self, **kwargs):
        super().__init__()
        self.order = kwargs.get('order', config.SUPPORT_RESISTANCE_FRACTAL_WINDOW)
        self.tolerance = kwargs.get('tolerance', 0.01) # Yüzde tabanlı tolerans
        self.atr_tolerance_multiplier = kwargs.get('atr_tolerance_multiplier', 1.5) # ATR'nin kaç katı tolerans kullanılacak
        self.required_data_points = self.order * 2 + 5

    def generate_score(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        logger.info(f"Running '{self.name}' model...")

        # Update parameters if provided in kwargs
        self.order = kwargs.get('order', self.order)
        self.tolerance = kwargs.get('tolerance', self.tolerance)
        self.atr_tolerance_multiplier = kwargs.get('atr_tolerance_multiplier', self.atr_tolerance_multiplier)
        self.required_data_points = self.order * 2 + 5

        if data.empty or len(data) < self.required_data_points:
            logger.warning(f"'{self.name}': Not enough data. Returning neutral score.")
            return {'score': 0.0, 'details': f"Not enough data. Need {self.required_data_points} data points, but got {len(data)}."}

        atr = kwargs.get('atr')
        dynamic_tolerance = self.tolerance # Varsayılan olarak yüzde tabanlı tolerans
        if atr is not None and atr > 0 and not data['Close'].empty:
            # ATR tabanlı dinamik tolerans hesapla
            dynamic_tolerance = (atr * self.atr_tolerance_multiplier) / data['Close'].iloc[-1]
            logger.debug(f"SupportResistanceModel: ATR tabanlı dinamik tolerans: {dynamic_tolerance:.4f}")

        try:
            result = self._calculate_score_and_levels(data['Close'], self.order, dynamic_tolerance)
            logger.info(f"'{self.name}' model result: Score={result['score']:.4f}")
            return result
        except Exception as e:
            logger.error(f"An error occurred while running the '{self.name}' model: {e}", exc_info=True)
            return {'score': 0.0, 'details': f"Error during model execution: {e}"}

    def _find_levels(self, price_series: pd.Series, order: int) -> Tuple[List[float], List[float]]:
        local_min_indices = argrelextrema(price_series.values, np.less_equal, order=order)[0]
        local_max_indices = argrelextrema(price_series.values, np.greater_equal, order=order)[0]
        
        supports = price_series.iloc[local_min_indices].tolist()
        resistances = price_series.iloc[local_max_indices].tolist()
        return supports, resistances

    def _calculate_score_and_levels(self, price_series: pd.Series, order: int, tolerance: float) -> Dict[str, Any]:
        current_price = price_series.iloc[-1]
        supports, resistances = self._find_levels(price_series, order)

        logger.debug(f"SupportResistanceModel: Current Price: {current_price:.2f}")
        logger.debug(f"SupportResistanceModel: Detected Supports: {supports}")
        logger.debug(f"SupportResistanceModel: Detected Resistances: {resistances}")
        logger.debug(f"SupportResistanceModel: Effective Tolerance: {tolerance:.4f}")

        if not supports and not resistances:
            logger.debug("SupportResistanceModel: No support or resistance levels found.")
            return {
                "score": 0.0, 
                "details": "Support/Resistance levels not found.",
                "closest_support": None,
                "closest_resistance": None
            }

        closest_support = min(supports, key=lambda x: abs(x - current_price)) if supports else None
        closest_resistance = min(resistances, key=lambda x: abs(x - current_price)) if resistances else None

        logger.debug(f"SupportResistanceModel: Closest Support: {f'{closest_support:.2f}' if closest_support is not None else 'N/A'}")
        logger.debug(f"SupportResistanceModel: Closest Resistance: {f'{closest_resistance:.2f}' if closest_resistance is not None else 'N/A'}")

        support_score = 0.0
        resistance_score = 0.0
        details = []

        if closest_support:
            distance_to_support = abs(current_price - closest_support) / current_price
            logger.debug(f"SupportResistanceModel: Distance to Support: {distance_to_support:.4f} vs Tolerance*3: {tolerance * 3:.4f}")
            if distance_to_support < tolerance * 3: # Dinamik toleransı kullan
                support_score = (1 - (distance_to_support / (tolerance * 3))) * 0.9
                details.append(f"Near support level ({closest_support:.2f})")
        logger.debug(f"SupportResistanceModel: Support Score: {support_score:.4f}")

        if closest_resistance:
            distance_to_resistance = abs(current_price - closest_resistance) / current_price
            logger.debug(f"SupportResistanceModel: Distance to Resistance: {distance_to_resistance:.4f} vs Tolerance*3: {tolerance * 3:.4f}")
            if distance_to_resistance < tolerance * 3: # Dinamik toleransı kullan
                resistance_score = -(1 - (distance_to_resistance / (tolerance * 3))) * 0.9
                details.append(f"Near resistance level ({closest_resistance:.2f})")
        logger.debug(f"SupportResistanceModel: Resistance Score: {resistance_score:.4f}")

        final_score = support_score + resistance_score
        final_details = ", ".join(details) if details else "Neutral support/resistance signal."
        
        return {
            "score": final_score,
            "details": final_details,
            "closest_support": closest_support,
            "closest_resistance": closest_resistance
        }
