

import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
import os

class SupportResistanceModel:
    def __init__(self, order: int = 20, tolerance: float = 0.01):
        self.order = order
        self.tolerance = tolerance
        self.supports = []
        self.resistances = []

    def find_support_resistance(self, data: pd.Series):
        """
        Verilen bir fiyat serisindeki yerel minimum ve maksimum noktaları bularak
        destek ve direnç seviyelerini tespit eder.
        """
        local_min_indices = argrelextrema(data.values, np.less_equal, order=self.order)[0]
        local_max_indices = argrelextrema(data.values, np.greater_equal, order=self.order)[0]

        self.supports = data.iloc[local_min_indices].tolist()
        self.resistances = data.iloc[local_max_indices].tolist()
        return self.supports, self.resistances

    def generate_signal(self, current_price: float):
        """
        Mevcut fiyata göre destek veya direnç sinyali üretir.
        """
        for level in self.supports:
            if abs(current_price - level) / level <= self.tolerance:
                return f"Yükselme Sinyali (Destek Seviyesi: {level:.2f})"

        for level in self.resistances:
            if abs(current_price - level) / level <= self.tolerance:
                return f"Alçalma Sinyali (Direnç Seviyesi: {level:.2f})"

        return "Sinyal Yok"

    def calculate_score(self, data: pd.DataFrame) -> float:
        """
        Destek ve direnç analizine dayalı bir puan hesaplar.
        """
        if 'close' not in data.columns or len(data) < self.order * 2:
            return 0.0

        price_series = data['close']
        current_price = price_series.iloc[-1]
        
        self.find_support_resistance(price_series)
        
        signal = self.generate_signal(current_price)

        if "Yükselme Sinyali" in signal:
            return 0.75
        elif "Alçalma Sinyali" in signal:
            return -0.75
        else:
            return 0.0

    

if __name__ == "__main__":
    # Proje ana dizinini bulmak için dosya yolunu ayarla
    script_dir = os.path.dirname(__file__)
    project_root = os.path.abspath(os.path.join(script_dir, "..", "..", ".."))
    file_path = os.path.join(project_root, "archive", "BTC-Daily.csv")

    print(f"Veri dosyası okunuyor: {file_path}")

    try:
        # Veriyi yükle
        df = pd.read_csv(file_path, parse_dates=['date'], index_col='date')
        price_data = df['close'].dropna()

        # Modeli başlat ve kullan
        model = SupportResistanceModel(order=30, tolerance=0.02)
        supports, resistances = model.find_support_resistance(price_data)

        print("\n--- Tespit Edilen Seviyeler ---")
        print(f"Önemli Destek Seviyeleri: {[f'{s:.2f}' for s in supports[-5:]]} (Son 5)")
        print(f"Önemli Direnç Seviyeleri: {[f'{r:.2f}' for r in resistances[-5:]]} (Son 5)")

        last_price = price_data.iloc[-1]
        print(f"\n--- Sinyal Analizi (Mevcut Fiyat: {last_price:.2f}) ---")

        signal = model.generate_signal(last_price)
        print(f"Sinyal: {signal}")

        score = model.calculate_score(df.rename(columns={'close': 'Close'}))
        print(f"Hesaplanan Puan: {score}")


    except FileNotFoundError:
        print(f"HATA: Veri dosyası bulunamadı. Lütfen '{file_path}' dosyasının mevcut olduğundan emin olun.")
    except Exception as e:
        print(f"Bir hata oluştu: {e}")
