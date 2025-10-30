import logging
import json
from typing import Dict, Any

import numpy as np

from .. import config
from ..models.registry import MODEL_REGISTRY
from ..models.base_model import BaseModel
from ..utils.data_fetcher import DataFetcher

logger = logging.getLogger(__name__)

class ScoringEngine:
    """
    Runs all valid models, determines market regime, and aggregates their results
    using dynamic, regime-based weighting to produce a final score.
    """
    def __init__(self, data_fetcher: DataFetcher):
        self.data_fetcher = data_fetcher
        self.models = self._load_models()

    def _load_models(self) -> Dict[str, BaseModel]:
        logger.info("Loading models...")
        loaded_models = {}
        broken_models = ["RecommendationModel", "FinancialRatioModel"]

        for model_name, model_class in MODEL_REGISTRY.items():
            if model_name in broken_models:
                logger.warning(f"Skipping broken/abstract model: {model_name}")
                continue
            try:
                loaded_models[model_name] = model_class()
            except Exception as e:
                logger.error(f"Failed to initialize model '{model_name}': {e}")
        logger.info(f"{len(loaded_models)} models loaded successfully: {list(loaded_models.keys())}")
        return loaded_models

    def _normalize_weights(self, weights: Dict[str, float]) -> Dict[str, float]:
        """Normalizes a given set of weights to sum to 1."""
        total_weight = sum(weights.values())
        if total_weight > 0:
            return {name: w / total_weight for name, w in weights.items()}
        return weights

    def _select_weights(self, regime: str) -> Dict[str, float]:
        """Selects the appropriate weight profile based on the market regime."""
        if "Strong" in regime:
            logger.info(f"Regime '{regime}' -> Selecting STRONG_TREND weights.")
            return config.MODEL_WEIGHTS_STRONG_TREND
        elif "Weak" in regime or "Ranging" in regime:
            logger.info(f"Regime '{regime}' -> Selecting RANGING weights.")
            return config.MODEL_WEIGHTS_RANGING
        else: # Default/Unknown
            logger.info(f"Regime '{regime}' -> Selecting DEFAULT weights.")
            return config.MODEL_WEIGHTS_DEFAULT

    def run_engine(self, symbol: str, interval: str = "1d", model_params: Dict[str, Any] = None) -> Dict[str, Any]:
        if model_params is None:
            model_params = {}

        is_stock = '.' in symbol
        asset_type = "stock" if is_stock else "crypto"

        data = self.data_fetcher.get_market_data(symbol, asset_type, interval=interval, period="1y")
        if data.empty:
            logger.warning(f"Could not fetch market data for '{symbol}'. Aborting analysis.")
            return {"error": "Market data not available."}

        all_results = {}
        logger.info(f"Running analysis for {symbol}...")

        for model_name, model_instance in self.models.items():
            if is_stock and model_name == "OnChainModel":
                logger.info("Skipping OnChainModel for stock analysis.")
                continue

            try:
                params = model_params.get(model_name, {})
                model_result = model_instance.predict(data=data.copy(), **params)
                all_results[model_name] = model_result
            except Exception as e:
                logger.error(f"Error running model '{model_name}': {e}", exc_info=True)
                all_results[model_name] = {'error': str(e)}

        # --- Dynamic Weighted Scoring ---
        market_regime = all_results.get("MarketConditionClassifier", {}).get("regime", "Unknown")
        active_weights = self._select_weights(market_regime)
        normalized_weights = self._normalize_weights(active_weights)
        
        logger.info(f"Calculating final score with weights for regime '{market_regime}'.")
        final_score = 0.0
        for model_name, result in all_results.items():
            if model_name in normalized_weights and 'score' in result:
                model_score = result.get('score', 0.0)
                weight = normalized_weights[model_name]
                final_score += model_score * weight
                logger.debug(f"  - {model_name}: (Score: {model_score:.2f} * Weight: {weight:.2f}) -> Partial: {model_score * weight:.2f}")

        all_results['final_score'] = np.tanh(final_score)

        logger.info(f"Scoring Engine finished. Final Score: {all_results['final_score']:.4f}")
        return all_results