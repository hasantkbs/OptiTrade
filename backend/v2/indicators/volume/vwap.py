import pandas as pd
import numpy as np
from v2.indicators.base import BaseIndicator
from v2.models.schemas import IndicatorOutput

class VWAPIndicator(BaseIndicator):
    def __init__(self, weight: float = 1.0):
        super().__init__(name="VWAP", weight=weight)

    async def calculate(self, data: pd.DataFrame, **kwargs) -> IndicatorOutput:
        # VWAP = sum(Price * Volume) / sum(Volume)
        # Typically resets daily, but for simplicity we calculate on the window
        p = (data['High'] + data['Low'] + data['Close']) / 3
        v = data['Volume']
        
        vwap = (p * v).cumsum() / v.cumsum()
        current_vwap = vwap.iloc[-1]
        current_price = data['Close'].iloc[-1]
        
        # Distance from VWAP normalized by Standard Deviation
        std_dist = (data['Close'] - vwap).std()
        if std_dist == 0: std_dist = 1e-9
        
        z_score = (current_price - current_vwap) / std_dist
        score = np.tanh(z_score) # -1 to 1
        
        return IndicatorOutput(
            indicator_name=self.name,
            score=float(score),
            confidence=0.85,
            side=self.get_side(score),
            metadata={"vwap": float(current_vwap), "z_score": float(z_score)}
        )
