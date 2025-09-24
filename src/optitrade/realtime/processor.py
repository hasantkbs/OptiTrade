
import asyncio
import logging
import pandas as pd
import pkgutil
import importlib
import json
import os

from src.optitrade.realtime.stream_handler_base import StreamHandlerBase
import src.optitrade.models as models
from src.optitrade.models.support_resistance_model import SupportResistanceModel
from src.optitrade.models.formation_detection_model import FormationDetectionModel
from src.optitrade.models.dcf_model import DCFModel

logger = logging.getLogger(__name__)

class RealtimeProcessor:
    """
    Processes real-time data and feeds it to all available models.
    """
    def __init__(self, stream_handler: StreamHandlerBase, model_lookback_bars: int, historical_data: pd.DataFrame = None):
        self.stream_handler = stream_handler
        self.model_lookback_bars = model_lookback_bars
        self.models = self._load_models()
        self.optimized_parameters = self._load_optimized_parameters()
        
        if historical_data is not None and not historical_data.empty:
            self.historical_bars = historical_data.copy()
            logger.info(f"RealtimeProcessor initialized with {len(self.historical_bars)} historical bars.")
        else:
            self.historical_bars = pd.DataFrame()

        self.stream_handler.on_message_callback = self._on_message
        logger.info("RealtimeProcessor initialized.")

    def _load_optimized_parameters(self):
        """Loads optimized parameters from JSON files."""
        optimized_params = {}
        for filename in os.listdir("."):
            if filename.startswith("optimized_parameters_") and filename.endswith(".json"):
                try:
                    with open(filename, "r") as f:
                        parts = filename.replace("optimized_parameters_", "").replace(".json", "").split("_")
                        model_name = parts[0]
                        symbol = parts[1]
                        interval = parts[2]
                        if model_name not in optimized_params:
                            optimized_params[model_name] = {}
                        if symbol not in optimized_params[model_name]:
                            optimized_params[model_name][symbol] = {}
                        optimized_params[model_name][symbol][interval] = json.load(f)
                except Exception as e:
                    logger.error(f"Error loading optimized parameters from {filename}: {e}")
        return optimized_params

    def _load_models(self):
        """
        Dynamically loads all model classes from the src.optitrade.models package.
        """
        loaded_models = {}
        for _, name, _ in pkgutil.iter_modules(models.__path__):
            try:
                module = importlib.import_module(f'src.optitrade.models.{name}')
                for attribute_name in dir(module):
                    attribute = getattr(module, attribute_name)
                    if isinstance(attribute, type) and issubclass(attribute, models.base_model.BaseModel) and attribute is not models.base_model.BaseModel:
                        if attribute is SupportResistanceModel or attribute is FormationDetectionModel or attribute is DCFModel:
                            loaded_models[name] = attribute()
                        else:
                            loaded_models[name] = attribute()
            except Exception as e:
                logger.error(f"Error loading model {name}: {e}")
        logger.info(f"Loaded models: {list(loaded_models.keys())}")
        return loaded_models

    async def _on_message(self, data: dict):
        """
        Callback function called by the stream handler when a new message is received.
        """
        price = data.get('p')
        timestamp = data.get('T')

        if price is not None and timestamp is not None:
            new_bar = pd.DataFrame([{'Open': float(price), 'High': float(price), 'Low': float(price), 'Close': float(price), 'Volume': 0}], 
                                   index=[pd.to_datetime(timestamp, unit='ms')])
            await self._on_bar_close(new_bar)

    async def _on_bar_close(self, new_bar_df: pd.DataFrame):
        """
        Callback function called when a new bar is closed.
        """
        logger.info(f"Processor received new bar: {new_bar_df.index[0]} - C:{new_bar_df['Close'].iloc[0]:.2f}")
        
        # Apply optimized parameters
        if self.optimized_parameters:
            for model_name, optimized_model_params in self.optimized_parameters.items():
                if model_name in self.models and self.stream_handler.stream_name in optimized_model_params and self.stream_handler.interval in optimized_model_params[self.stream_handler.stream_name]:
                    params_to_apply = optimized_model_params[self.stream_handler.stream_name][self.stream_handler.interval]
                    logger.info(f"Applying optimized parameters for {model_name}: {params_to_apply}")
                    model_instance = self.models[model_name]
                    for param_name, param_value in params_to_apply.items():
                        setattr(model_instance, param_name, param_value)

        self.historical_bars = self.historical_bars.drop(new_bar_df.index, errors='ignore')
        self.historical_bars = pd.concat([self.historical_bars, new_bar_df])
        
        if len(self.historical_bars) > self.model_lookback_bars:
            self.historical_bars = self.historical_bars.iloc[-self.model_lookback_bars:]

        self.historical_bars = self.historical_bars.sort_index()

        if len(self.historical_bars) >= self.model_lookback_bars:
            scores = {}
            support_resistance_levels = {}
            formation = {}
            for model_name, model in self.models.items():
                try:
                    if isinstance(model, DCFModel):
                        score = model.generate_score(self.historical_bars, self.stream_handler.stream_name)
                    else:
                        score = model.generate_score(self.historical_bars)
                    scores[model_name] = score
                    if isinstance(model, SupportResistanceModel):
                        levels = model._calculate_score_and_levels(self.historical_bars['Close'], model.order)
                        support_resistance_levels = {
                            'support': levels.get('closest_support'),
                            'resistance': levels.get('closest_resistance')
                        }
                    if isinstance(model, FormationDetectionModel):
                        score, details, points = model._detect_head_and_shoulders(self.historical_bars['Close'])
                        if score != 0.0:
                            formation = {'name': 'Head and Shoulders', 'details': details, 'points': points}
                        else:
                            score, details, points = model._detect_triangles(self.historical_bars['Close'])
                            if score != 0.0:
                                formation = {'name': 'Triangle', 'details': details, 'points': points}
                            else:
                                score, details, points = model._detect_double_top_bottom(self.historical_bars['Close'])
                                if score != 0.0:
                                    formation = {'name': 'Double Top/Bottom', 'details': details, 'points': points}

                except Exception as e:
                    logger.error(f"Error running model {model_name}: {e}")
            
            logger.info(f"Real-time scores: {scores}")
            
            # Combine all data to be sent to the frontend
            frontend_data = {
                'scores': scores,
                'support_resistance': support_resistance_levels,
                'formation': formation,
                'latest_price': new_bar_df['Close'].iloc[0]
            }
            
            # This is where you would broadcast the data to the frontend
            # For now, we will just log it
            logger.info(f"Data to be sent to frontend: {frontend_data}")

            # Placeholder for continuous learning
            await self._continuous_learning()

    async def _continuous_learning(self):
        """
        Placeholder for continuous learning.
        This method would be responsible for retraining models with new data.
        """
        if len(self.historical_bars) % 100 == 0:
            logger.info("Triggering continuous learning...")
            ml_model = self.models.get('machine_learning_model')
            if ml_model:
                try:
                    pass
                except Exception as e:
                    logger.error(f"Error during continuous learning: {e}")

    async def start(self, stream_name: str, interval: str):
        """
        Starts the real-time data streaming and processing.
        """
        logger.info("Starting real-time data stream...")
        self.stream_handler.stream_name = stream_name
        self.stream_handler.interval = interval
        await self.stream_handler.start(stream_name)
