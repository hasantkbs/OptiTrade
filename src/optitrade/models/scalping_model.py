import pandas as pd
import numpy as np
import ta.momentum
import ta.trend
import logging
from .. import config
from typing import Dict, Any

logger = logging.getLogger(__name__)

from .base_model import BaseModel

import logging
import pandas as pd
import ta
from typing import Dict, Any

from .base_model import BaseModel

logger = logging.getLogger(__name__)

class ScalpingModel(BaseModel):
    """
    A simple model for scalping, based on short-term RSI and MFI.
    """
    def __init__(self, **kwargs):
        super().__init__()
        self.rsi_window = kwargs.get('rsi_window', 5)
        self.mfi_window = kwargs.get('mfi_window', 10)

    def predict(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        logger.info(f"Running '{self.name}' model...")

        if len(data) < self.mfi_window:
            return {'score': 0.0, 'details': 'Not enough data for scalping analysis.'}

        rsi = ta.momentum.rsi(data['Close'], window=self.rsi_window).iloc[-1]
        mfi = ta.volume.money_flow_index(data['High'], data['Low'], data['Close'], data['Volume'], window=self.mfi_window).iloc[-1]

        score = 0.0
        details = f"No immediate scalp opportunity (RSI: {rsi:.2f}, MFI: {mfi:.2f})"

        if rsi < 20 and mfi < 20:
            score = 0.8
            details = f"Scalp Buy Signal (RSI: {rsi:.2f}, MFI: {mfi:.2f})"
        elif rsi > 80 and mfi > 80:
            score = -0.8
            details = f"Scalp Sell Signal (RSI: {rsi:.2f}, MFI: {mfi:.2f})"

        return {'score': score, 'details': details}
