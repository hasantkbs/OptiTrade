
from abc import ABC, abstractmethod
from typing import Dict, Optional, Any
import pandas as pd

from ..utils.data_fetcher import DataFetcher

class BaseModel(ABC):
    """
    Base interface (abstract class) for all trading signal models.

    This class defines the standard structure that every model must adhere to. Each model
    can be initialized with an optional DataFetcher instance and must include a `generate_score` method.
    """
    def __init__(self, data_fetcher: Optional[DataFetcher] = None):
        """
        Initializes the model.

        Args:
            data_fetcher (DataFetcher, optional): The centralized data service to be used for fetching data. Defaults to None.
        """
        if data_fetcher and not isinstance(data_fetcher, DataFetcher):
            raise TypeError("data_fetcher must be an instance of the DataFetcher class.")
        self.data_fetcher = data_fetcher

    @abstractmethod
    def predict(self, symbol: str, interval: str = "1d", **kwargs) -> Dict[str, Any]:
        """
        Generates a trading signal score and related details for the given data.

        This method must be implemented by each subclass according to its own logic.

        Args:
            symbol (str): The symbol to predict for.
            interval (str): The interval to predict for.
            **kwargs: Additional parameters that can be passed to the model.

        Returns:
            Dict[str, Any]: A dictionary containing at least the 'score' key.
                            Example: {'score': 0.75, 'details': 'Strong bullish signal'}
                """
        pass

    @property
    def name(self) -> str:
        """
        Returns the name of the model (derived from the class name).
        """
        return self.__class__.__name__
