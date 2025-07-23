import pandas as pd
import numpy as np
import yfinance as yf
import argparse
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

class SupportResistanceModel:
    """
    Destek-direnç seviyeleri ile mevcut fiyatın ilişkisini analiz eden model.
    Kullanır: Pivot point, basit fraktal tespiti.
    Girdi: Günlük fiyat geçmişi (OHLC).
    Çıktı: Yakınlık skoru (0: uzakta, 1: çok yakın).
    """
    def __init__(self):
        """
        Modeli başlatır.
        """
        self.fractal_window = config.SUPPORT_RESISTANCE_FRACTAL_WINDOW

    def calculate_pivot_points(self, high: pd.Series, low: pd.Series, close: pd.Series) -> dict:
        """
        Pivot noktalarını ve destek/direnç seviyelerini hesaplar.
        Geleneksel Pivot Noktası formülünü kullanır.
        """
        if high.empty or low.empty or close.empty:
            return {}

        pivot_point = (high.iloc[-1] + low.iloc[-1] + close.iloc[-1]) / 3
        r1 = (2 * pivot_point) - low.iloc[-1]
        s1 = (2 * pivot_point) - high.iloc[-1]
        r2 = pivot_point + (high.iloc[-1] - low.iloc[-1])
        s2 = pivot_point - (high.iloc[-1] - low.iloc[-1])
        r3 = high.iloc[-1] + 2 * (pivot_point - low.iloc[-1])
        s3 = low.iloc[-1] - 2 * (high.iloc[-1] - pivot_point)

        return {
            'PP': pivot_point,
            'R1': r1, 'S1': s1,
            'R2': r2, 'S2': s2,
            'R3': r3, 'S3': s3
        }

    def find_fractals(self, prices: pd.Series, window: int = 2) -> list:
        """
        Basit fraktalları (yerel zirveler ve dipler) bulur.
        Bir nokta, kendisinden önceki ve sonraki 'window' kadar noktadan
        daha yüksekse/düşükse fraktal olarak kabul edilir.
        """
        fractals = []
        if len(prices) < (2 * window + 1):
            return fractals

        for i in range(window, len(prices) - window):
            # Yükseliş fraktalı (yerel zirve)
            is_high_fractal = True
            for j in range(1, window + 1):
                if prices.iloc[i] <= prices.iloc[i-j] or prices.iloc[i] <= prices.iloc[i+j]:
                    is_high_fractal = False
                    break
            if is_high_fractal:
                fractals.append(prices.iloc[i])

            # Düşüş fraktalı (yerel dip)
            is_low_fractal = True
            for j in range(1, window + 1):
                if prices.iloc[i] >= prices.iloc[i-j] or prices.iloc[i] >= prices.iloc[i+j]:
                    is_low_fractal = False
                    break
            if is_low_fractal:
                fractals.append(prices.iloc[i])
        return fractals

    def generate_proximity_score(self, data: pd.DataFrame, interval: str = '1d') -> float:
        logger.debug(f"SupportResistanceModel: generate_proximity_score called with interval: {interval}")

        # Interval'e göre fraktal pencere boyutunu ayarla
        if interval == '1m':
            fractal_window = 1
        elif interval == '5m':
            fractal_window = 2
        elif interval == '15m':
            fractal_window = 3
        elif interval == '30m' or interval == '60m' or interval == '1h':
            fractal_window = 4
        else: # 1d, 1wk, 1mo ve diğerleri için varsayılan değer
            fractal_window = self.fractal_window

        required_columns = ['High', 'Low', 'Close']
        if not isinstance(data, pd.DataFrame) or data.empty or not all(col in data.columns for col in required_columns):
            raise ValueError(f"DataFrame boş olamaz ve {required_columns} sütunlarını içermelidir.")

        high = data['High']
        low = data['Low']
        close = data['Close']

        if high.empty or low.empty or close.empty:
            return 0.0

        current_price = close.iloc[-1]

        # Pivot Noktaları
        pivot_levels = self.calculate_pivot_points(high, low, close)
        levels = list(pivot_levels.values())

        # Fraktallar
        fractal_levels = self.find_fractals(close, window=fractal_window)
        levels.extend(fractal_levels)

        if not levels:
            return 0.0

        # Mevcut fiyata en yakın seviyeyi bul
        min_distance = float('inf')
        for level in levels:
            if not pd.isna(level):
                distance = abs(current_price - level)
                if distance < min_distance:
                    min_distance = distance
        
        # Fiyat aralığına göre normalizasyon
        # Ortalama günlük aralığı kullanarak bir normalizasyon faktörü bulalım
        avg_daily_range = (high - low).mean()
        if avg_daily_range == 0:
            return 0.0

        # Mesafe ne kadar küçükse skor o kadar yüksek olur
        # Skor = 1 - (min_distance / avg_daily_range)
        # Negatif skorları önlemek için max(0, ...) kullan
        proximity_score = max(0, 1 - (min_distance / avg_daily_range))

        return float(proximity_score)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Destek-Direnç seviyelerine yakınlık skorunu hesaplar.')
    parser.add_argument('--symbol', type=str, default='BTC-USD', help='Hisse senedi/kripto para sembolü (örn: BTC-USD, AAPL). Varsayılan: BTC-USD')
    parser.add_argument('--period', type=str, default='1y', help='Veri çekme periyodu (örn: 1y, 6mo, 1mo). Varsayılan: 1y')
    parser.add_argument('--interval', type=str, default='1d', help='Veri çekme aralığı (örn: 1d, 1wk, 1mo). Varsayılan: 1d')

    args = parser.parse_args()

    logger.info(f"--- {args.symbol} için Destek-Direnç Yakınlık Analizi ---")

    try:
        ticker = yf.Ticker(args.symbol)
        data = ticker.history(period=args.period, interval=args.interval)

        if data.empty:
            logger.error(f"Hata: {args.symbol} için veri çekilemedi veya yeterli veri yok. Lütfen sembolü ve periyodu kontrol edin.")
        else:
            # open_prices = data['Open'] # Bu satırlar artık gerekli değil
            # high_prices = data['High']
            # low_prices = data['Low']
            # close_prices = data['Close']

            model = SupportResistanceModel()
            proximity_score = model.generate_proximity_score(data)
            logger.info(f"{args.symbol} Destek-Direnç Yakınlık Skoru: {proximity_score:.2f}")

    except Exception as e:
        logger.error(f"Veri çekme veya skor hesaplama sırasında bir hata oluştu: {e}")