import pandas as pd
import numpy as np
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from v2.models.schemas import IndicatorOutput, SignalSide

class BaseIndicator(ABC):
    def __init__(self, name: str, weight: float = 1.0):
        self.name = name
        self.weight = weight

    @abstractmethod
    async def calculate(self, data: pd.DataFrame, **kwargs) -> IndicatorOutput:
        """Calculate the indicator and return a normalized output."""
        pass

    def normalize(self, value: float, min_val: float, max_val: float) -> float:
        """Clamp and normalize value between -1 and 1."""
        if max_val == min_val:
            return 0.0
        normalized = 2 * ((value - min_val) / (max_val - min_val)) - 1
        return max(-1.0, min(1.0, normalized))

    def get_side(self, score: float, threshold: float = 0.2) -> SignalSide:
        if score > threshold:
            return SignalSide.BUY
        elif score < -threshold:
            return SignalSide.SELL
        return SignalSide.NEUTRAL
