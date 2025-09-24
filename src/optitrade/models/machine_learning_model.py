import pandas as pd
import xgboost as xgb
import logging
import os
from typing import Dict, Any, Optional

from .base_model import BaseModel
from .model_utils import create_features

# Loglama yapılandırması
logger = logging.getLogger(__name__)

class MachineLearningModel(BaseModel):
    """
    Uses a pre-trained XGBoost model to predict price direction.
    """
    def __init__(self, interval: str = "1d"):
        super().__init__()
        self.interval = interval
        self.model_path_template = "src/optitrade/models/trained_models/xgb_price_predictor_{}.json"
        self.model = self._load_model(self.interval)
        self.features = [
            'feature_price_change_1d', 'feature_price_change_3d', 'feature_price_change_7d',
            'feature_volatility_7d', 'feature_volatility_30d', 'feature_rsi_14d',
            'feature_macd', 'feature_macd_signal', 'feature_macd_diff',
            'feature_sma_50', 'feature_sma_200', 'feature_price_vs_sma50',
            'feature_pe_ratio', 'feature_pb_ratio', 'feature_de_ratio' # New financial ratio features
        ]
        self.required_data_points = 200 + 5

    def _load_model(self, interval: str) -> xgb.XGBClassifier:
        model_path = self.model_path_template.format(interval)
        if not os.path.exists(model_path):
            logger.error(f"Trained model file not found: {model_path}")
            logger.error(f"Please run `scripts/train_model.py` for this interval first.")
            return None
        
        logger.info(f"Loading trained model from '{model_path}'...")
        model = xgb.XGBClassifier()
        model.load_model(model_path)
        logger.info("Model loaded successfully.")
        return model

    def generate_score(self, data: pd.DataFrame, financial_ratios: Optional[Dict[str, Any]] = None) -> float:
        if not self.model:
            logger.warning(f"'{self.name}': Model not loaded, skipping prediction.")
            return 0.0

        logger.info(f"Running '{self.name}' model for interval '{self.interval}'...")

        if data.empty or len(data) < self.required_data_points:
            logger.warning(f"'{self.name}': Not enough data for prediction.")
            return 0.0

        data_with_features = create_features(data, interval=self.interval, financial_ratios=financial_ratios)
        latest_features = data_with_features[self.features].iloc[-1:]
        
        if latest_features.isnull().values.any():
            logger.warning(f"'{self.name}': Could not calculate features for the latest data (NaN values present).")
            return 0.0

        prediction_proba = self.model.predict_proba(latest_features)
        probability_of_increase = prediction_proba[0][1]

        score = (probability_of_increase - 0.5) * 2

        logger.info(f"'{self.name}' model result: Probability of Increase={probability_of_increase:.4f}, Score={score:.4f}")
        return float(score)

    def retrain(self, data: pd.DataFrame):
        """
        Retrains the model with new data.
        """
        logger.info(f"Retraining '{self.name}' model for interval '{self.interval}'...")
        # This is a placeholder for the actual retraining logic.
        # In a real implementation, you would:
        # 1. Create labels for the new data.
        # 2. Append the new data and labels to the training set.
        # 3. Retrain the XGBoost model.
        # 4. Save the updated model.
        pass