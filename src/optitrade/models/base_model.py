
from abc import ABC, abstractmethod
from typing import Dict
import pandas as pd

from ..utils.data_fetcher import DataFetcher

class BaseModel(ABC):
    """
    Tüm alım-satım sinyali modelleri için temel arayüz (soyut sınıf).

    Bu sınıf, her modelin uyması gereken standart yapıyı tanımlar. Her model,
    bir `DataFetcher` örneği ile başlatılmalı ve bir `predict` metodu içermelidir.
    """
    def __init__(self, data_fetcher: DataFetcher):
        """
        Modeli başlatır.

        Args:
            data_fetcher (DataFetcher): Veri çekmek için kullanılacak merkezi veri servis.
        """
        if not isinstance(data_fetcher, DataFetcher):
            raise TypeError("data_fetcher, DataFetcher sınıfının bir örneği olmalıdır.")
        self.data_fetcher = data_fetcher

    @abstractmethod
    def predict(self, symbol: str, **kwargs) -> Dict[str, float]:
        """
        Belirtilen sembol için bir alım-satım sinyali tahmini yapar.

        Bu metot, her alt model tarafından kendi mantığına göre uygulanmalıdır.

        Args:
            symbol (str): Tahmin yapılacak olan finansal varlığın sembolü (örn: "BTC-USD").
            **kwargs: Modele özgü ek parametreler.

        Returns:
            Dict[str, float]: Modelin tahminini içeren bir sözlük.
                - 'score' (float): -1.0 (Güçlü Sat) ile +1.0 (Güçlü Al) arasında bir puan.
                - 'confidence' (float, optional): Tahminin güvenilirliği (0.0 ile 1.0 arası).
                - Diğer modele özgü metrikler...
        """
        pass

    @property
    def name(self) -> str:
        """
        Modelin adını döndürür (sınıf adından türetilir).
        """
        return self.__class__.__name__
