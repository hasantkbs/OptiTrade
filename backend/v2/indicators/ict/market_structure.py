import pandas as pd
import numpy as np
from v2.indicators.base import BaseIndicator
from v2.models.schemas import IndicatorOutput

class MarketStructureIndicator(BaseIndicator):
    """
    ICT Market Structure Shift (MSS) / Break of Structure (BOS):
    Detects if the last Swing High or Swing Low was broken with momentum.
    """
    def __init__(self, window: int = 5, weight: float = 1.5):
        super().__init__(name="MarketStructure", weight=weight)
        self.window = window

    async def calculate(self, data: pd.DataFrame, **kwargs) -> IndicatorOutput:
        if len(data) < self.window * 3:
            return IndicatorOutput(indicator_name=self.name, score=0.0, confidence=0.0, side="NEUTRAL")

        # Find Swings
        # A simple swing high: High[i] > High[i-1] and High[i] > High[i+1]
        # For real-time, we look for the most recent established swing
        
        highs = data['High']
        lows = data['Low']
        closes = data['Close']
        
        last_swing_high = None
        last_swing_low = None
        
        # Look back to find the last confirmed swing high/low
        for i in range(len(data) - 2, self.window, -1):
            if highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i+1]:
                if highs.iloc[i] > highs.iloc[i-self.window:i].max():
                    last_swing_high = highs.iloc[i]
                    break
        
        for i in range(len(data) - 2, self.window, -1):
            if lows.iloc[i] < lows.iloc[i-1] and lows.iloc[i] < lows.iloc[i+1]:
                if lows.iloc[i] < lows.iloc[i-self.window:i].min():
                    last_swing_low = lows.iloc[i]
                    break
                    
        score = 0.0
        mss_type = "None"
        
        current_price = closes.iloc[-1]
        
        if last_swing_high and current_price > last_swing_high:
            # Bullish MSS / BOS
            momentum = closes.pct_change(3).iloc[-1]
            score = np.tanh(momentum * 100) # Only strong if momentum is high
            mss_type = "Bullish_BOS"
            
        elif last_swing_low and current_price < last_swing_low:
            # Bearish MSS / BOS
            momentum = closes.pct_change(3).iloc[-1]
            score = np.tanh(momentum * 100)
            mss_type = "Bearish_BOS"

        return IndicatorOutput(
            indicator_name=self.name,
            score=float(score),
            confidence=0.9 if abs(score) > 0.3 else 0.4,
            side=self.get_side(score),
            metadata={
                "mss_type": mss_type,
                "last_swing_high": float(last_swing_high) if last_swing_high else None,
                "last_swing_low": float(last_swing_low) if last_swing_low else None
            }
        )
