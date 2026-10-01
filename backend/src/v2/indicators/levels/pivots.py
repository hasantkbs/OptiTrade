import pandas as pd
import numpy as np
from v2.indicators.base import BaseIndicator
from v2.models.schemas import IndicatorOutput

class PivotPointsIndicator(BaseIndicator):
    def __init__(self, weight: float = 1.0):
        super().__init__(name="PivotPoints", weight=weight)

    async def calculate(self, data: pd.DataFrame, **kwargs) -> IndicatorOutput:
        # Standard Pivot Points using Previous Period (Day/Week)
        # Here we approximate with the current window's High/Low/Close
        high = data['High'].max()
        low = data['Low'].min()
        close = data['Close'].iloc[-1]
        
        pp = (high + low + close) / 3
        r1 = (2 * pp) - low
        s1 = (2 * pp) - high
        r2 = pp + (high - low)
        s2 = pp - (high - low)
        
        current_price = data['Close'].iloc[-1]
        
        # Proximity score: if price is near support (+ score) or resistance (- score)
        # This is a bit counter-intuitive for breakout traders, 
        # but here we treat them as potential bounce zones.
        
        # Calculate distance to nearest level
        levels = [s2, s1, pp, r1, r2]
        distances = [current_price - l for l in levels]
        min_dist_idx = np.argmin([abs(d) for d in distances])
        nearest_dist = distances[min_dist_idx]
        
        # Normalize by ATR or range
        atr = (data['High'] - data['Low']).mean()
        if atr == 0: atr = 1e-9
        
        score = -np.tanh(nearest_dist / (atr * 0.5)) # Negative because near resistance = sell, near support = buy
        
        return IndicatorOutput(
            indicator_name=self.name,
            score=float(score),
            confidence=0.7,
            side=self.get_side(score),
            metadata={
                "pp": float(pp), "r1": float(r1), "s1": float(s1),
                "nearest_level_dist": float(nearest_dist)
            }
        )
