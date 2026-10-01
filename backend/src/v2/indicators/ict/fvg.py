import pandas as pd
import numpy as np
from v2.indicators.base import BaseIndicator
from v2.models.schemas import IndicatorOutput

class FVGIndicator(BaseIndicator):
    """
    ICT Fair Value Gap (FVG):
    Bullish FVG: Low of Bar 3 > High of Bar 1
    Bearish FVG: High of Bar 3 < Low of Bar 1
    """
    def __init__(self, weight: float = 1.3):
        super().__init__(name="FairValueGap", weight=weight)

    async def calculate(self, data: pd.DataFrame, **kwargs) -> IndicatorOutput:
        if len(data) < 3:
            return IndicatorOutput(indicator_name=self.name, score=0.0, confidence=0.0, side="NEUTRAL")

        # Check the last 3 candles
        # Bar 1: data.iloc[-3]
        # Bar 2: data.iloc[-2] (The displacement bar)
        # Bar 3: data.iloc[-1]
        
        b1_high = data['High'].iloc[-3]
        b1_low = data['Low'].iloc[-3]
        b3_high = data['High'].iloc[-1]
        b3_low = data['Low'].iloc[-1]
        
        score = 0.0
        gap_size = 0.0
        
        # Bullish FVG
        if b3_low > b1_high:
            gap_size = b3_low - b1_high
            # Normalize by ATR
            atr = (data['High'] - data['Low']).rolling(14).mean().iloc[-1]
            score = np.tanh(gap_size / atr)
        
        # Bearish FVG
        elif b3_high < b1_low:
            gap_size = b1_low - b3_high
            atr = (data['High'] - data['Low']).rolling(14).mean().iloc[-1]
            score = -np.tanh(gap_size / atr)

        # FVG is more powerful if it's "fresh" (not filled)
        # In this simple implementation, we only check the current state
        
        return IndicatorOutput(
            indicator_name=self.name,
            score=float(score),
            confidence=0.8 if abs(score) > 0.1 else 0.2,
            side=self.get_side(score),
            metadata={"gap_size": float(gap_size)}
        )
