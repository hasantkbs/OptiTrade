import joblib
import pandas as pd
import numpy as np
import os
from typing import Optional, Dict

class MLPredictorV2:
    def __init__(self, model_path: str = "backend/models/v2_xgb_model.joblib"):
        self.model_path = model_path
        self.model_data = None
        if os.path.exists(model_path):
            self.model_data = joblib.load(model_path)
            
    def predict(self, data: pd.DataFrame) -> Optional[Dict]:
        if self.model_data is None:
            return None
        
        try:
            # Extract features matching training logic
            df = data.copy()
            
            # EMA Cross
            ema20 = df['Close'].ewm(span=20, adjust=False).mean()
            ema50 = df['Close'].ewm(span=50, adjust=False).mean()
            df['ema_dist'] = (ema20 - ema50) / df['Close']
            
            # Rolling VWAP
            p = (df['High'] + df['Low'] + df['Close']) / 3
            v = df['Volume']
            df['vwap_rolling'] = (p * v).rolling(14).sum() / v.rolling(14).sum()
            df['vwap_dist'] = (df['Close'] - df['vwap_rolling']) / df['vwap_rolling']
            
            # RSI
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))
            
            # Momentum
            df['velocity'] = df['Close'].pct_change(5)
            
            # Volatility
            df['range'] = (df['High'] - df['Low']) / df['Close']
            
            # Get last row
            last_row = df[self.model_data['features']].iloc[-1:]
            
            if last_row.isnull().values.any():
                return None
                
            prob = self.model_data['model'].predict_proba(last_row)[0][1]
            return {
                "probability": float(prob),
                "is_bullish": prob > 0.5,
                "confidence": abs(prob - 0.5) * 2
            }
        except Exception as e:
            print(f"ML Predictor Error: {e}")
            return None
