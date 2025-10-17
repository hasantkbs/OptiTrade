import streamlit as st
import inspect
from src.optitrade.models.registry import MODEL_REGISTRY

class BridgeDataFetcher:
    def __init__(self, data):
        self._data = data

    def get_historical_data(self, symbol, interval, limit):
        return self._data
    
    def get_federal_fund_rate(self):
        st.warning("MacroEconomicModel requires a full DataFetcher setup. Skipping.", icon="⚠️")
        return None

    def get_btc_transaction_data(self, timespan="1year"):
        st.warning("OnChainModel requires a full DataFetcher setup. Skipping.", icon="⚠️")
        return None

    def get_news(self, query):
        st.warning("News-based models require a full DataFetcher setup. Skipping.", icon="⚠️")
        return None

    def get_reddit_posts(self, query, limit=25):
        return []

    def get_tweets(self, query, limit=25):
        return []

# Define which models are applicable to which asset type
STOCK_MODELS = [
    "PriceTrendModel",
    "SupportResistanceModel",
    "DivergenceDetectionModel",
    "FibonacciModel",
    "FinancialRatioModel",
]

CRYPTO_MODELS = [
    "PriceTrendModel",
    "SupportResistanceModel",
    "DivergenceDetectionModel",
    "FibonacciModel",
    "OnChainModel",
]

def get_available_models(asset_type='stock'):
    """Returns a list of available model names based on asset type."""
    if asset_type == 'crypto':
        return [model for model in CRYPTO_MODELS if model in MODEL_REGISTRY]
    else: # stock
        return [model for model in STOCK_MODELS if model in MODEL_REGISTRY]

def run_analysis(selected_models, symbol, interval, data):
    results = {}
    bridge_fetcher = BridgeDataFetcher(data)

    for model_name in selected_models:
        with st.spinner(f"Running {model_name}..."):
            try:
                model_class = MODEL_REGISTRY.get(model_name)
                if not model_class:
                    results[model_name] = {"error": "Model not found in registry."}
                    continue

                sig = inspect.signature(model_class.__init__)
                if 'data_fetcher' in sig.parameters:
                    model_instance = model_class(data_fetcher=bridge_fetcher)
                else:
                    model_instance = model_class()
                
                result = model_instance.predict(symbol=symbol, interval=interval, data=data)
                results[model_name] = result

            except Exception as e:
                results[model_name] = {"error": f"An error occurred: {e}"}
            
    return results