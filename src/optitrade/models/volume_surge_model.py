import pandas as pd
import numpy as np
import ta.volume
import ta.volatility
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

class VolumeSurgeModel:
    """
    Hacim anomalilerini, ortalamaya göre sapmaları analiz eden model.
    Kullanılan göstergeler: VWAP, On-Balance Volume, Volatility + Volume ilişkisi.
    """
    def __init__(self,
                 vwap_window: int = config.VOLUME_SURGE_VWAP_WINDOW,
                 obv_window: int = config.VOLUME_SURGE_OBV_WINDOW,
                 volatility_window: int = config.VOLUME_SURGE_VOLATILITY_WINDOW,
                 volume_ma_window: int = config.VOLUME_SURGE_MA_WINDOW,
                 volume_deviation_scale: float = config.VOLUME_SURGE_DEVIATION_SCALE, # Yeni parametre
                 obv_influence: float = config.VOLUME_SURGE_OBV_INFLUENCE): # Yeni parametre
        """
        Modeli başlatır ve gösterge parametrelerini ayarlar.

        Args:
            vwap_window (int): VWAP hesaplaması için pencere boyutu.
            obv_window (int): OBV için kullanılacak pencere boyutu (genellikle kullanılmaz, ancak esneklik için).
            volatility_window (int): Volatilite hesaplaması için pencere boyutu.
            volume_ma_window (int): Hacim hareketli ortalaması için pencere boyutu.
            volume_deviation_scale (float): Hacim sapmasının skoru ne kadar etkileyeceği.
            obv_influence (float): OBV trendinin hacim skoruna katkısı.
        """
        self.vwap_window = vwap_window
        self.obv_window = obv_window
        self.volatility_window = volatility_window
        self.volume_ma_window = volume_ma_window
        self.volume_deviation_scale = volume_deviation_scale
        self.obv_influence = obv_influence

    def generate_score(self, data: pd.DataFrame, interval: str = '1d') -> tuple[float, float]:
        logger.debug(f"VolumeSurgeModel: generate_score called with interval: {interval}")

        # Interval'e göre pencere boyutlarını ayarla
        if interval == '1m':
            vwap_window = 5
            obv_window = 5
            volatility_window = 5
            volume_ma_window = 10
        elif interval == '5m':
            vwap_window = 10
            obv_window = 10
            volatility_window = 10
            volume_ma_window = 20
        elif interval == '15m':
            vwap_window = 12
            obv_window = 12
            volatility_window = 12
            volume_ma_window = 30
        elif interval == '30m' or interval == '60m' or interval == '1h':
            vwap_window = 14
            obv_window = 14
            volatility_window = 14
            volume_ma_window = 40
        else: # 1d, 1wk, 1mo ve diğerleri için varsayılan değerler
            vwap_window = self.vwap_window
            obv_window = self.obv_window
            volatility_window = self.volatility_window
            volume_ma_window = self.volume_ma_window

        # Veri kontrolü
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        if not isinstance(data, pd.DataFrame) or data.empty or not all(col in data.columns for col in required_columns):
            raise ValueError(f"DataFrame boş olamaz ve {required_columns} sütunlarını içermelidir.")

        open_prices = data['open']
        high_prices = data['high']
        low_prices = data['low']
        close_prices = data['close']
        volumes = data['volume']

        min_data_points = max(vwap_window, obv_window, volatility_window, volume_ma_window)
        if len(close_prices) < min_data_points:
            logger.warning(f"Uyarı: Yeterli veri noktası yok ({len(close_prices)} mevcut, en az {min_data_points} gerekli). Nötr skorlar döndürülüyor.")
            return 0.0, 0.0

        # Göstergeleri hesapla
        # VWAP (Volume Weighted Average Price)
        # ta kütüphanesinde doğrudan VWAP fonksiyonu yok, manuel hesaplayalım
        # Typical Price = (High + Low + Close) / 3
        typical_price = (high_prices + low_prices + close_prices) / 3
        vwap = (typical_price * volumes).cumsum() / volumes.cumsum()

        # On-Balance Volume (OBV)
        obv = ta.volume.on_balance_volume(close_prices, volumes)

        # Volatilite (ATR - Average True Range)
        atr = ta.volatility.average_true_range(high_prices, low_prices, close_prices, window=volatility_window)

        # Hacim Hareketli Ortalaması
        volume_ma = volumes.rolling(window=volume_ma_window).mean()

        # Hacim Skoru Hesaplama
        volume_score = 0.0
        if not volumes.empty and not pd.isna(volumes.iloc[-1]) and not volume_ma.empty and not pd.isna(volume_ma.iloc[-1]):
            # Mevcut hacmin ortalama hacme göre sapması
            volume_deviation = (volumes.iloc[-1] - volume_ma.iloc[-1]) / volume_ma.iloc[-1] if volume_ma.iloc[-1] != 0 else 0

            # Yeni: Hacim sapmasını daha sürekli bir skora dönüştür
            volume_score_from_deviation = np.tanh(volume_deviation * self.volume_deviation_scale)

            # OBV Skoru
            obv_score = 0.0
            if not obv.empty and not pd.isna(obv.iloc[-1]) and not pd.isna(obv.iloc[-2]):
                if obv.iloc[-1] > obv.iloc[-2]:
                    obv_score = self.obv_influence # OBV yükseliyor, pozitif
                elif obv.iloc[-1] < obv.iloc[-2]:
                    obv_score = -self.obv_influence # OBV düşüyor, negatif

            volume_score = volume_score_from_deviation + obv_score
            # Nihai hacim skorunu -1.0 ile 1.0 arasına sıkıştır
            volume_score = np.tanh(volume_score) # Tekrar tanh uygulamak, değeri -1 ile 1 arasına sıkıştırır

        # Volatiliteyle Normalize Edilmiş Etki Hesaplama
        # Fiyat değişimi / ATR (volatilite)
        impact_score = 0.0
        if not close_prices.empty and not pd.isna(close_prices.iloc[-1]) and not pd.isna(close_prices.iloc[-2]) and \
           not atr.empty and not pd.isna(atr.iloc[-1]) and atr.iloc[-1] != 0:
            price_change = close_prices.iloc[-1] - close_prices.iloc[-2]
            impact_score = price_change / atr.iloc[-1]

            # Etki skorunu -1.0 ile 1.0 arasına normalize et
            impact_score = np.tanh(impact_score / 2) # Daha yumuşak bir normalizasyon

        return float(volume_score), float(impact_score)

if __name__ == '__main__':
    import yfinance as yf
    import argparse

    parser = argparse.ArgumentParser(description='Hacim anomalilerini ve volatiliteyle normalize edilmiş etkiyi hesaplar.')
    parser.add_argument('--symbol', type=str, default='BTC-USD', help='Hisse senedi/kripto para sembolü (örn: BTC-USD, AAPL). Varsayılan: BTC-USD')
    parser.add_argument('--period', type=str, default='1y', help='Veri çekme periyodu (örn: 1y, 6mo, 1mo). Varsayılan: 1y')
    parser.add_argument('--interval', type=str, default='1d', help='Veri çekme aralığı (örn: 1d, 1wk, 1mo). Varsayılan: 1d')

    args = parser.parse_args()

    logger.info(f"--- {args.symbol} için Hacim ve Volatilite Analizi ---")

    try:
        ticker = yf.Ticker(args.symbol)
        data = ticker.history(period=args.period, interval=args.interval)

        if data.empty:
            logger.error(f"Hata: {args.symbol} için veri çekilemedi veya yeterli veri yok. Lütfen sembolü ve periyodu kontrol edin.")
        else:
            model = VolumeSurgeModel()
            volume_score, impact_score = model.generate_score(data)
            logger.info(f"{args.symbol} Hacim Skoru: {volume_score:.2f}")
            logger.info(f"{args.symbol} Volatiliteyle Normalize Edilmiş Etki: {impact_score:.2f}")

    except Exception as e:
        logger.error(f"Veri çekme veya skor hesaplama sırasında bir hata oluştu: {e}")
