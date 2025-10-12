
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

    def predict(self, symbol: str, interval: str = "1d", **kwargs) -> Dict[str, Any]:
        logger.info(f"Running '{self.name}' model for {symbol} {interval}...")

        data = kwargs.get('data')
        if not isinstance(data, pd.DataFrame) or data.empty:
            raise ValueError("SupportResistanceModel requires a non-empty pandas DataFrame in 'data' kwarg.")

        # Update parameters if provided in kwargs
        self.order = kwargs.get('order', self.order)
        self.tolerance = kwargs.get('tolerance', self.tolerance)
        self.atr_tolerance_multiplier = kwargs.get('atr_tolerance_multiplier', self.atr_tolerance_multiplier)
        self.required_data_points = self.order * 2 + 5

        if len(data) < self.required_data_points:
            logger.warning(f"'{self.name}': Not enough data ({len(data)}/{self.required_data_points}). Returning neutral score.")
            return {'score': 0.0, 'details': f"Not enough data. Need {self.required_data_points} data points, but got {len(data)}."}

        atr = kwargs.get('atr') # ATR might be passed from another model or calculated internally
        dynamic_tolerance = self.tolerance # Varsayılan olarak yüzde tabanlı tolerans
        if atr is not None and atr > 0 and not data['close'].empty:
            # ATR tabanlı dinamik tolerans hesapla
            dynamic_tolerance = (atr * self.atr_tolerance_multiplier) / data['close'].iloc[-1]
            logger.debug(f"SupportResistanceModel: ATR tabanlı dinamik tolerans: {dynamic_tolerance:.4f}")

        result = self._calculate_score_and_levels(data['close'], self.order, dynamic_tolerance)
        logger.info(f"'{self.name}' model result for {symbol} {interval}: Score={result['score']:.4f}")
        return result

    def _find_levels(self, price_series: pd.Series, order: int) -> Tuple[List[float], List[float]]:
        local_min_indices = argrelextrema(price_series.values, np.less_equal, order=order)[0]
        local_max_indices = argrelextrema(price_series.values, np.greater_equal, order=order)[0]
        
        supports = price_series.iloc[local_min_indices].tolist()
        resistances = price_series.iloc[local_max_indices].tolist()
        return supports, resistances

    def _cluster_levels(self, levels: List[float], tolerance: float) -> List[Dict[str, Any]]:
        if not levels:
            return []

        levels.sort()
        clusters = []
        current_cluster = [levels[0]]

        for level in levels[1:]:
            if (level - current_cluster[-1]) / current_cluster[-1] < tolerance:
                current_cluster.append(level)
            else:
                clusters.append({
                    "zone_start": min(current_cluster),
                    "zone_end": max(current_cluster),
                    "strength": len(current_cluster)
                })
                current_cluster = [level]
        
        clusters.append({
            "zone_start": min(current_cluster),
            "zone_end": max(current_cluster),
            "strength": len(current_cluster)
        })

        return clusters

    def _calculate_score_and_levels(self, price_series: pd.Series, order: int, tolerance: float) -> Dict[str, Any]:
        current_price = price_series.iloc[-1]
        supports, resistances = self._find_levels(price_series, order)

        support_clusters = self._cluster_levels(supports, tolerance)
        resistance_clusters = self._cluster_levels(resistances, tolerance)

        logger.debug(f"SupportResistanceModel: Current Price: {current_price:.2f}")
        logger.debug(f"SupportResistanceModel: Detected Support Zones: {support_clusters}")
        logger.debug(f"SupportResistanceModel: Detected Resistance Zones: {resistance_clusters}")
        logger.debug(f"SupportResistanceModel: Effective Tolerance: {tolerance:.4f}")

        if not support_clusters and not resistance_clusters:
            logger.debug("SupportResistanceModel: No support or resistance zones found.")
            return {
                "score": 0.0, 
                "details": "Support/Resistance zones not found.",
                "support_zones": [],
                "resistance_zones": []
            }

        closest_support_zone = min(support_clusters, key=lambda x: abs(x['zone_end'] - current_price)) if support_clusters else None
        closest_resistance_zone = min(resistance_clusters, key=lambda x: abs(x['zone_start'] - current_price)) if resistance_clusters else None

        logger.debug(f"SupportResistanceModel: Closest Support Zone: {closest_support_zone}")
        logger.debug(f"SupportResistanceModel: Closest Resistance Zone: {closest_resistance_zone}")

        support_score = 0.0
        resistance_score = 0.0
        details = []

        if closest_support_zone:
            distance_to_support = abs(current_price - closest_support_zone['zone_end']) / current_price
            if distance_to_support < tolerance * 3:
                strength_factor = np.log1p(closest_support_zone['strength']) # Log of strength to avoid extreme values
                support_score = (1 - (distance_to_support / (tolerance * 3))) * 0.9 * strength_factor
                details.append(f"Near support zone ({closest_support_zone['zone_start']:.2f} - {closest_support_zone['zone_end']:.2f}) with strength {closest_support_zone['strength']}")
        logger.debug(f"SupportResistanceModel: Support Score: {support_score:.4f}")

        if closest_resistance_zone:
            distance_to_resistance = abs(current_price - closest_resistance_zone['zone_start']) / current_price
            if distance_to_resistance < tolerance * 3:
                strength_factor = np.log1p(closest_resistance_zone['strength'])
                resistance_score = -(1 - (distance_to_resistance / (tolerance * 3))) * 0.9 * strength_factor
                details.append(f"Near resistance zone ({closest_resistance_zone['zone_start']:.2f} - {closest_resistance_zone['zone_end']:.2f}) with strength {closest_resistance_zone['strength']}")
        logger.debug(f"SupportResistanceModel: Resistance Score: {resistance_score:.4f}")

        final_score = support_score + resistance_score
        final_details = ", ".join(details) if details else "Neutral support/resistance signal."
        
        return {
            "score": final_score,
            "details": final_details,
            "support_zones": support_clusters,
            "resistance_zones": resistance_clusters
        }
