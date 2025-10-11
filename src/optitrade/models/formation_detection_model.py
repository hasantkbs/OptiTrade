
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
import logging
from typing import Dict, List, Tuple, Any

from .base_model import BaseModel
from .. import config

# Loglama yapılandırması
logger = logging.getLogger(__name__)

class FormationDetectionModel(BaseModel):
    """
    Detects chart patterns in price data and returns a score.
    """
    def __init__(self, **kwargs):
        super().__init__()
        self.extrema_order = kwargs.get('extrema_order', 10)
        self.tolerance = kwargs.get('tolerance', 0.03)
        self.required_data_points = 150

    def predict(self, symbol: str, interval: str = "1d", **kwargs) -> Dict[str, Any]:
        logger.info(f"Running '{self.name}' model...")

        # Update parameters if provided in kwargs
        self.extrema_order = kwargs.get('extrema_order', self.extrema_order)
        self.tolerance = kwargs.get('tolerance', self.tolerance)

        try:
            data = self.data_fetcher.get_historical_data(symbol, interval, limit=self.required_data_points)
            if data.empty or len(data) < self.required_data_points:
                logger.warning(f"'{self.name}': Not enough data. Returning neutral score.")
                return {'score': 0.0, 'details': f"Not enough data. Need {self.required_data_points} data points, but got {len(data)}."}

            prices = data['Close']
            score, details, formation_info = self._detect_head_and_shoulders(prices)
            if score == 0.0:
                score, details, formation_info = self._detect_triangles(prices)
            if score == 0.0:
                score, details, formation_info = self._detect_double_top_bottom(prices)
            if score == 0.0:
                score, details, formation_info = self._detect_flags(prices)
            if score == 0.0:
                score, details, formation_info = self._detect_wedges(prices)
            if score == 0.0:
                score, details, formation_info = self._detect_rectangles(prices)
            
            logger.info(f"'{self.name}' model result: Score={score:.2f}, Details: {details}")
            return {'score': score, 'details': details, 'formation': formation_info}
        except Exception as e:
            logger.error(f"An error occurred while running the '{self.name}' model: {e}", exc_info=True)
            return {'score': 0.0, 'details': f"Error during model execution: {e}"}
    def _get_extrema(self, prices: pd.Series) -> Tuple[pd.Series, pd.Series]:
        highs = prices.iloc[argrelextrema(prices.values, np.greater_equal, order=self.extrema_order)[0]]
        lows = prices.iloc[argrelextrema(prices.values, np.less_equal, order=self.extrema_order)[0]]
        return highs, lows

    def _detect_triangles(self, prices: pd.Series) -> Tuple[float, str, Dict]:
        highs, lows = self._get_extrema(prices.tail(90))
        if len(lows) < 2 or len(highs) < 2:
            return 0.0, "Formation not found", {}

        lows_x = np.arange(len(lows))
        lows_slope, lows_intercept = np.polyfit(lows_x, lows.values, 1)
        highs_x = np.arange(len(highs))
        highs_slope, highs_intercept = np.polyfit(highs_x, highs.values, 1)
        current_price = prices.iloc[-1]

        if lows_slope > 0.05 and abs(highs_slope) < 0.05:
            resistance_level = highs.mean()
            if current_price > resistance_level:
                return 0.8, f"Ascending Triangle breakout confirmed ({resistance_level:.2f}).", {'type': 'ascending_triangle', 'resistance': resistance_level}
            else:
                return 0.0, f"Consolidation within Ascending Triangle formation (below {resistance_level:.2f}).", {}

        if highs_slope < -0.05 and abs(lows_slope) < 0.05:
            support_level = lows.mean()
            if current_price < support_level:
                return -0.8, f"Descending Triangle breakdown confirmed ({support_level:.2f}).", {'type': 'descending_triangle', 'support': support_level}
            else:
                return 0.0, f"Consolidation within Descending Triangle formation (above {support_level:.2f}).", {}

        if highs_slope < -0.05 and lows_slope > 0.05:
            return 0.0, "Symmetrical Triangle formation. Waiting for breakout.", {'type': 'symmetrical_triangle', 'upper_trendline': [highs_slope, highs_intercept], 'lower_trendline': [lows_slope, lows_intercept]}

        return 0.0, "Triangle formation not found", {}

    def _detect_head_and_shoulders(self, prices: pd.Series) -> Tuple[float, str, Dict]:
        highs, lows = self._get_extrema(prices)
        if len(highs) >= 3 and len(lows) >= 2:
            last_highs = highs.tail(3)
            shoulders_and_head_indices = last_highs.index
            relevant_lows = lows[(lows.index > shoulders_and_head_indices[0]) & (lows.index < shoulders_and_head_indices[2])]
            if len(relevant_lows) >= 2:
                left_shoulder, head, right_shoulder = last_highs.iloc[0], last_highs.iloc[1], last_highs.iloc[2]
                if (head > left_shoulder and head > right_shoulder and abs(left_shoulder - right_shoulder) / left_shoulder < 0.05):
                    neckline_break = min(relevant_lows.iloc[0], relevant_lows.iloc[1])
                    if prices.iloc[-1] < neckline_break:
                        return -0.9, f"Head and Shoulders (H&S) pattern confirmed (below {neckline_break:.2f}).", {'type': 'head_and_shoulders', 'neckline': neckline_break}
        if len(lows) >= 3 and len(highs) >= 2:
            last_lows = lows.tail(3)
            shoulders_and_head_indices = last_lows.index
            relevant_highs = highs[(highs.index > shoulders_and_head_indices[0]) & (highs.index < shoulders_and_head_indices[2])]
            if len(relevant_highs) >= 2:
                left_shoulder, head, right_shoulder = last_lows.iloc[0], last_lows.iloc[1], last_lows.iloc[2]
                if (head < left_shoulder and head < right_shoulder and abs(left_shoulder - right_shoulder) / left_shoulder < 0.05):
                    neckline_break = max(relevant_highs.iloc[0], relevant_highs.iloc[1])
                    if prices.iloc[-1] > neckline_break:
                        return 0.9, f"Inverse Head and Shoulders (iH&S) pattern confirmed (above {neckline_break:.2f}).", {'type': 'inverse_head_and_shoulders', 'neckline': neckline_break}
        return 0.0, "Formation not found", {}

    def _detect_double_top_bottom(self, prices: pd.Series) -> Tuple[float, str, Dict]:
        highs, lows = self._get_extrema(prices)
        if len(highs) >= 2:
            last_two_highs = highs.tail(2)
            price1, price2 = last_two_highs.iloc[0], last_two_highs.iloc[1]
            if abs(price1 - price2) / price1 <= self.tolerance:
                trough = prices[last_two_highs.index[0]:last_two_highs.index[1]].min()
                if prices.iloc[-1] < trough:
                    return -0.75, f"Double Top pattern confirmed (below {trough:.2f}).", {'type': 'double_top', 'neckline': trough}
        if len(lows) >= 2:
            last_two_lows = lows.tail(2)
            price1, price2 = last_two_lows.iloc[0], last_two_lows.iloc[1]
            if abs(price1 - price2) / price1 <= self.tolerance:
                peak = prices[last_two_lows.index[0]:last_two_lows.index[1]].max()
                if prices.iloc[-1] > peak:
                    return 0.75, f"Double Bottom pattern confirmed (above {peak:.2f}).", {'type': 'double_bottom', 'neckline': peak}
        return 0.0, "Formation not found", {}

    def _detect_flags(self, prices: pd.Series) -> Tuple[float, str, Dict]:
        if len(prices) < 50:
            return 0.0, "Not enough data for Flag pattern detection.", {}

        recent_change = (prices.iloc[-1] - prices.iloc[-10]) / prices.iloc[-10]

        if recent_change > 0.05:
            consolidation_prices = prices.iloc[-10:]
            if (consolidation_prices.iloc[-1] - consolidation_prices.iloc[0]) / consolidation_prices.iloc[0] < 0.02 and \
               (consolidation_prices.iloc[-1] - consolidation_prices.iloc[0]) / consolidation_prices.iloc[0] > -0.02:
                return 0.6, "Potential Bull Flag pattern.", {'type': 'bull_flag'}
        elif recent_change < -0.05:
            consolidation_prices = prices.iloc[-10:]
            if (consolidation_prices.iloc[-1] - consolidation_prices.iloc[0]) / consolidation_prices.iloc[0] > -0.02 and \
               (consolidation_prices.iloc[-1] - consolidation_prices.iloc[0]) / consolidation_prices.iloc[0] < 0.02:
                return -0.6, "Potential Bear Flag pattern.", {'type': 'bear_flag'}

        return 0.0, "Flag pattern not found", {}

    def _detect_wedges(self, prices: pd.Series) -> Tuple[float, str, Dict]:
        highs, lows = self._get_extrema(prices.tail(90))
        if len(lows) < 2 or len(highs) < 2:
            return 0.0, "Formation not found", {}

        lows_x = np.arange(len(lows))
        highs_x = np.arange(len(highs))

        lows_slope, _ = np.polyfit(lows_x, lows.values, 1)
        highs_slope, _ = np.polyfit(highs_x, highs.values, 1)

        if lows_slope > 0 and highs_slope > 0 and highs_slope > lows_slope:
            if (highs.iloc[-1] - lows.iloc[-1]) / prices.iloc[-1] < self.tolerance * 2:
                return -0.7, "Potential Rising Wedge pattern (bearish).", {'type': 'rising_wedge'}

        if lows_slope < 0 and highs_slope < 0 and lows_slope < highs_slope:
            if (highs.iloc[-1] - lows.iloc[-1]) / prices.iloc[-1] < self.tolerance * 2:
                return 0.7, "Potential Falling Wedge pattern (bullish).", {'type': 'falling_wedge'}

        return 0.0, "Wedge pattern not found", {}

    def _detect_rectangles(self, prices: pd.Series) -> Tuple[float, str, Dict]:
        highs, lows = self._get_extrema(prices.tail(90))
        if len(lows) < 2 or len(highs) < 2:
            return 0.0, "Formation not found", {}
        
        avg_high = highs.mean()
        avg_low = lows.mean()

        if highs.std() / avg_high < self.tolerance and lows.std() / avg_low < self.tolerance:
            if prices.iloc[-1] < avg_high and prices.iloc[-1] > avg_low:
                return 0.0, "Consolidation within Rectangle Pattern. Waiting for breakout.", {'type': 'rectangle', 'support': avg_low, 'resistance': avg_high}

        return 0.0, "Rectangle pattern not found", {}