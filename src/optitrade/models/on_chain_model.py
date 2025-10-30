import logging
import pandas as pd
from typing import Dict, Any

from .base_model import BaseModel
from .. import config

logger = logging.getLogger(__name__)

class OnChainModel(BaseModel):
    """
    Analyzes on-chain data (e.g., transaction volume, active addresses) to generate a score.
    This is a placeholder and needs a real on-chain data provider.
    """
    def __init__(self, **kwargs):
        super().__init__()
        self.short_window = kwargs.get('short_window', config.ONCHAIN_SHORT_WINDOW)
        self.long_window = kwargs.get('long_window', config.ONCHAIN_LONG_WINDOW)

    def predict(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        logger.info(f"Running '{self.name}' model...")

        # On-chain data is not typically in the main market data DataFrame.
        # This model would need a dedicated on-chain data fetcher.
        # For now, we simulate a signal based on market volume as a proxy.
        if 'Volume' not in data.columns or data['Volume'].isnull().all():
            return {'score': 0.0, 'details': 'On-chain data (Volume) not available.'}

        short_vol_ma = data['Volume'].rolling(window=self.short_window).mean().iloc[-1]
        long_vol_ma = data['Volume'].rolling(window=self.long_window).mean().iloc[-1]

        if short_vol_ma > long_vol_ma * 1.2:
            score = 0.4
            details = "On-chain activity (volume) is increasing."
        elif short_vol_ma < long_vol_ma * 0.8:
            score = -0.4
            details = "On-chain activity (volume) is decreasing."
        else:
            score = 0.0
            details = "On-chain activity (volume) is neutral."
        
        logger.info(f"'{self.name}' model result: {details}")
        return {'score': score, 'details': details}

