
from abc import ABC, abstractmethod
from typing import Dict, Optional
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
    def generate_score(self, data: pd.DataFrame) -> float:
        """
        Generates a trading signal score for the given data.

        This method must be implemented by each subclass according to its own logic.

        Args:
            data (pd.DataFrame): The input data for the model.

        Returns:
            float: A score between -1.0 (Strong Sell) and +1.0 (Strong Buy).
        """
        pass

    @property
    def name(self) -> str:
        """
        Returns the name of the model (derived from the class name).
        """
        return self.__class__.__name__
