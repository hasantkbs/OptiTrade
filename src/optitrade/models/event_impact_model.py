import pandas as pd
from datetime import datetime, timedelta
import argparse
import numpy as np
import logging
from .. import config

# Loglama yapılandırması
logging.basicConfig(
    level=config.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

from .base_model import BaseModel

class EventImpactModel(BaseModel):
    """
    Önemli ekonomik/takvimsel olayların etkisini modelleyen model.
    Kullanır: Tarihsel haber-sonrası fiyat tepkisi analizi (basitleştirilmiş).
    Girdi: Olay tarihi, etkisi (FOMC, ETF onayı, vs.).
    Çıktı: Etki katsayısı.
    """
    def __init__(self, decay_rate: float = 0.1, **kwargs):
        super().__init__(**kwargs)
        """
        Modeli başlatır ve önceden tanımlanmış olayları yükler.
        Gerçek bir uygulamada bu veriler bir veritabanından veya API'den çekilmelidir.
        Format: {'date': datetime obj, 'type': str, 'impact_value': float}
        'impact_value': -1.0 (çok negatif) ile 1.0 (çok pozitif) arası.

        Args:
            decay_rate (float): Etkinin zamanla ne kadar hızlı azalacağını belirleyen oran.
                                 Daha yüksek değer, daha hızlı bozunma anlamına gelir.
        """
        self.events = [
            # 2024 Olayları
            {'date': datetime(2024, 1, 15), 'type': 'Major Economic Data Release', 'impact_value': 0.4},
            {'date': datetime(2024, 2, 28), 'type': 'Central Bank Speech', 'impact_value': -0.3},
            {'date': datetime(2024, 3, 20), 'type': 'Tech Giant Earnings', 'impact_value': 0.7},
            {'date': datetime(2024, 4, 10), 'type': 'Geopolitical Event', 'impact_value': -0.8},
            {'date': datetime(2024, 5, 1), 'type': 'Interest Rate Decision', 'impact_value': -0.6},
            {'date': datetime(2024, 6, 5), 'type': 'New Product Launch', 'impact_value': 0.6},
            {'date': datetime(2024, 7, 25), 'type': 'FOMC Meeting', 'impact_value': -0.7},
            {'date': datetime(2024, 8, 15), 'type': 'Inflation Report', 'impact_value': 0.5},
            {'date': datetime(2024, 9, 10), 'type': 'Major Tech Earnings', 'impact_value': 0.8},
            {'date': datetime(2024, 10, 1), 'type': 'Geopolitical Tension', 'impact_value': -0.9},
            {'date': datetime(2024, 11, 5), 'type': 'Election Day', 'impact_value': 0.6},
            {'date': datetime(2024, 12, 12), 'type': 'Holiday Season Impact', 'impact_value': 0.3},
            
            # 2025 Olayları
            {'date': datetime(2025, 1, 10), 'type': 'New Crypto ETF Approval', 'impact_value': 1.0},
            {'date': datetime(2025, 2, 20), 'type': 'Central Bank Rate Hike', 'impact_value': -0.6},
            {'date': datetime(2025, 3, 15), 'type': 'Major Industry Conference', 'impact_value': 0.5},
            {'date': datetime(2025, 4, 22), 'type': 'Quarterly Earnings Report', 'impact_value': 0.7},
            {'date': datetime(2025, 5, 18), 'type': 'Regulatory Announcement', 'impact_value': -0.4},
            {'date': datetime(2025, 6, 30), 'type': 'Global Economic Summit', 'impact_value': 0.2},
            {'date': datetime(2025, 7, 20), 'type': 'Key Technology Breakthrough', 'impact_value': 0.9},
            {'date': datetime(2025, 8, 5), 'type': 'Market Correction', 'impact_value': -0.7},
            {'date': datetime(2025, 9, 1), 'type': 'Major Policy Change', 'impact_value': 0.6},
            {'date': datetime(2025, 10, 10), 'type': 'Unexpected Market Event', 'impact_value': -1.0},
            {'date': datetime(2025, 11, 25), 'type': 'Holiday Shopping Season', 'impact_value': 0.4},
            {'date': datetime(2025, 12, 15), 'type': 'Year-End Rally', 'impact_value': 0.8},
        ]
        self.decay_rate = decay_rate

    def predict(self, symbol: str, interval: str = "1d", **kwargs) -> float:
        current_date = datetime.now()
        lookback_days = kwargs.get('lookback_days', 7)
        lookforward_days = kwargs.get('lookforward_days', 3)
        # current_date'i zaman dilimi bilgisinden arındır (tz-naive yap)
        if current_date.tzinfo is not None:
            current_date = current_date.replace(tzinfo=None)

        total_impact = 0.0
        relevant_events = []

        for event in self.events:
            time_diff_days = (current_date - event['date']).days
            
            # Olay geçmişte ve lookback_days içinde mi?
            if 0 <= time_diff_days <= lookback_days:
                # Üstel bozunma
                decay_factor = np.exp(-self.decay_rate * time_diff_days)
                relevant_events.append(event['impact_value'] * decay_factor)
            # Olay gelecekte ve lookforward_days içinde mi?
            elif -lookforward_days <= time_diff_days < 0:
                # Üstel bozunma (gelecekteki olaylar için)
                decay_factor = np.exp(-self.decay_rate * abs(time_diff_days))
                relevant_events.append(event['impact_value'] * decay_factor)
        
        if relevant_events:
            total_impact = sum(relevant_events) / len(relevant_events) # Ortalama etki

        # Skoru -1.0 ile 1.0 arasına sıkıştır
        return max(-1.0, min(1.0, total_impact))
