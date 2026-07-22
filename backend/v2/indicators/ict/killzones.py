import pandas as pd
import numpy as np
from datetime import datetime, time
import pytz
from v2.indicators.base import BaseIndicator
from v2.models.schemas import IndicatorOutput

class KillzoneIndicator(BaseIndicator):
    """
    ICT Killzones:
    - London Open: 02:00 - 05:00 EST
    - NY Open: 07:00 - 10:00 EST
    - London Close: 10:00 - 12:00 EST
    - Asian Session: 20:00 - 00:00 EST
    """
    KILLZONES = {
        "London_Open": (time(2, 0), time(5, 0)),
        "NY_Open": (time(7, 0), time(10, 0)),
        "London_Close": (time(10, 0), time(12, 0)),
        "Asian": (time(20, 0), time(0, 0))
    }

    def __init__(self, weight: float = 1.0):
        super().__init__(name="ICT_Killzone", weight=weight)

    async def calculate(self, data: pd.DataFrame, **kwargs) -> IndicatorOutput:
        # Determine timezone from data if possible, default to New York
        # Some yfinance data has timezone info in the index
        ts = data.index[-1]
        
        target_tz = pytz.timezone("America/New_York")
        if hasattr(data.index, "tz") and data.index.tz is not None:
            # If data is already localized, just convert to target_tz
            ts_localized = ts.astimezone(target_tz)
        else:
            # Naive to localized
            ts_localized = pytz.utc.localize(ts).astimezone(target_tz)
            
        current_time = ts_localized.time()
        active_kz = None
        for kz, (start, end) in self.KILLZONES.items():
            if start < end:
                if start <= current_time <= end:
                    active_kz = kz
                    break
            else: # Overnight session (Asian)
                if current_time >= start or current_time <= end:
                    active_kz = kz
                    break
        
        if active_kz:
            # Killzones increase volatility and signal importance
            # We check if price is expanding (momentum)
            momentum = data['Close'].pct_change(5).iloc[-1]
            score = np.tanh(momentum * 100) # Exaggerate for killzone
            confidence = 0.9
        else:
            score = 0.0
            confidence = 0.3 # Low importance outside killzones
            active_kz = "None"

        return IndicatorOutput(
            indicator_name=self.name,
            score=float(score),
            confidence=confidence,
            side=self.get_side(score),
            metadata={"active_killzone": active_kz, "ny_time": str(current_time)}
        )
