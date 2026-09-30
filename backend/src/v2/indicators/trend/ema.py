import pandas as pd
import numpy as np
from v2.indicators.base import BaseIndicator
from v2.models.schemas import IndicatorOutput

class EMAIndicator(BaseIndicator):
    def __init__(self, fast: int = 20, slow: int = 50, weight: float = 1.0):
        super().__init__(name="EMA_Cross", weight=weight)
        self.fast = fast
        self.slow = slow

    async def calculate(self, data: pd.DataFrame, **kwargs) -> IndicatorOutput:
        ema_fast = data['Close'].ewm(span=self.fast, adjust=False).mean()
        ema_slow = data['Close'].ewm(span=self.slow, adjust=False).mean()
        
        current_fast = ema_fast.iloc[-1]
        current_slow = ema_slow.iloc[-1]
        
        # Distance between EMAs normalized by ATR (volatility)
        high_low = data['High'] - data['Low']
        high_close = (data['High'] - data['Close'].shift()).abs()
        low_close = (data['Low'] - data['Close'].shift()).abs()
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        atr = true_range.rolling(14).mean().iloc[-1]
        
        if atr == 0 or np.isnan(atr): atr = current_fast * 0.001
        
        dist = (current_fast - current_slow) / atr
        score = np.tanh(dist)
        
        return IndicatorOutput(
            indicator_name=self.name,
            score=float(score),
            confidence=0.75,
            side=self.get_side(score),
            metadata={"ema_fast": float(current_fast), "ema_slow": float(current_slow)}
        )
