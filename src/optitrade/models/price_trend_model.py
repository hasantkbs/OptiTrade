import pandas as pd
import numpy as np
import ta.momentum
import ta.volatility
import ta.trend
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

class PriceTrendModel:
    """
    Fiyat verilerinden teknik analiz göstergeleriyle skor üreten model.
    Kullanılan göstergeler: RSI, MACD, Moving Averages, Bollinger Bands, Trendline kırılımları, ADX.
    """
    def __init__(self,
                 rsi_window: int = config.PRICE_TREND_RSI_WINDOW,
                 macd_fast_window: int = config.PRICE_TREND_MACD_FAST_WINDOW,
                 macd_slow_window: int = config.PRICE_TREND_MACD_SLOW_WINDOW,
                 macd_signal_window: int = config.PRICE_TREND_MACD_SIGNAL_WINDOW,
                 sma_short_window: int = config.PRICE_TREND_SMA_SHORT_WINDOW,
                 sma_long_window: int = config.PRICE_TREND_SMA_LONG_WINDOW,
                 bollinger_window: int = config.PRICE_TREND_BOLLINGER_WINDOW,
                 bollinger_std: float = config.PRICE_TREND_BOLLINGER_STD,
                 adx_window: int = config.PRICE_TREND_ADX_WINDOW):
        """
        Modeli başlatır ve gösterge parametrelerini ayarlar.

        Args:
            rsi_window (int): RSI hesaplaması için pencere boyutu.
            macd_fast_window (int): MACD hızlı EMA penceresi.
            macd_slow_window (int): MACD yavaş EMA penceresi.
            macd_signal_window (int): MACD sinyal hattı penceresi.
            sma_short_window (int): Kısa basit hareketli ortalama penceresi.
            sma_long_window (int): Uzun basit hareketli ortalama penceresi.
            bollinger_window (int): Bollinger Bantları penceresi.
            bollinger_std (float): Bollinger Bantları standart sapma çarpanı.
            adx_window (int): ADX hesaplaması için pencere boyutu.
        """
        self.rsi_window = rsi_window
        self.macd_fast_window = macd_fast_window
        self.macd_slow_window = macd_slow_window
        self.macd_signal_window = macd_signal_window
        self.sma_short_window = sma_short_window
        self.sma_long_window = sma_long_window
        self.bollinger_window = bollinger_window
        self.bollinger_std = bollinger_std
        self.adx_window = adx_window

    def generate_score(self, data: pd.Series, interval: str = '1d') -> float:
        logger.debug(f"PriceTrendModel: generate_score called with interval: {interval}")

        # Interval'e göre pencere boyutlarını ayarla
        if interval == '1m':
            short_window = 5
            long_window = 20
        elif interval == '5m':
            short_window = 10
            long_window = 30
        elif interval == '15m':
            short_window = 12
            long_window = 40
        elif interval == '30m' or interval == '60m' or interval == '1h':
            short_window = 14
            long_window = 50
        else: # 1d, 1wk, 1mo ve diğerleri için varsayılan değerler
            short_window = self.sma_short_window
            long_window = self.sma_long_window

        if data.empty or len(data) < long_window:
            logger.warning("PriceTrendModel: Yeterli veri yok. Nötr skor döndürülüyor.")
            return 0.0

        # Hareketli ortalamaları hesapla
        sma_short = ta.trend.sma_indicator(data['close'], window=self.sma_short_window)
        sma_long = ta.trend.sma_indicator(data['close'], window=self.sma_long_window)

        # RSI
        rsi = ta.momentum.rsi(data['close'], window=self.rsi_window)

        # MACD
        macd = ta.trend.macd(data['close'], window_fast=self.macd_fast_window, window_slow=self.macd_slow_window)
        macd_signal = ta.trend.macd_signal(data['close'], window_fast=self.macd_fast_window, window_slow=self.macd_slow_window, window_sign=self.macd_signal_window)
        macd_diff = ta.trend.macd_diff(data['close'], window_fast=self.macd_fast_window, window_slow=self.macd_slow_window, window_sign=self.macd_signal_window)

        # Bollinger Bantları
        bollinger_hband = ta.volatility.bollinger_hband(data['close'], window=self.bollinger_window, window_dev=self.bollinger_std)
        bollinger_lband = ta.volatility.bollinger_lband(data['close'], window=self.bollinger_window, window_dev=self.bollinger_std)

        # ADX
        adx = ta.trend.adx(data['high'], data['low'], data['close'], window=self.adx_window)
        adx_pos = ta.trend.adx_pos(data['high'], data['low'], data['close'], window=self.adx_window)
        adx_neg = ta.trend.adx_neg(data['high'], data['low'], data['close'], window=self.adx_window)

        # Skorlama mantığı
        score = 0.0

        # RSI Skoru (0-100 arası, 50 nötr)
        if not rsi.empty and not pd.isna(rsi.iloc[-1]):
            if rsi.iloc[-1] > 70:
                score -= (rsi.iloc[-1] - 70) / 30 * 0.5 # Aşırı alım, düşüş sinyali (0.0 - 0.5)
            elif rsi.iloc[-1] < 30:
                score += (30 - rsi.iloc[-1]) / 30 * 0.5 # Aşırı satım, yükseliş sinyali (0.0 - 0.5)

        # MACD Skoru
        if not macd_diff.empty and not pd.isna(macd_diff.iloc[-1]) and not pd.isna(macd_diff.iloc[-2]):
            if macd_diff.iloc[-1] > 0 and macd_diff.iloc[-2] <= 0: # MACD yukarı kesişimi
                score += 0.4
            elif macd_diff.iloc[-1] < 0 and macd_diff.iloc[-2] >= 0: # MACD aşağı kesişimi
                score -= 0.4
            elif not macd.empty and not pd.isna(macd.iloc[-1]) and not macd_signal.empty and not pd.isna(macd_signal.iloc[-1]):
                if macd.iloc[-1] > macd_signal.iloc[-1]: # MACD sinyal hattının üzerinde
                    score += 0.1
                elif macd.iloc[-1] < macd_signal.iloc[-1]: # MACD sinyal hattının altında
                    score -= 0.1

        # Hareketli Ortalama Skoru (MA Çaprazlama)
        if not sma_short.empty and not pd.isna(sma_short.iloc[-1]) and not pd.isna(sma_short.iloc[-2]) and \
           not sma_long.empty and not pd.isna(sma_long.iloc[-1]) and not pd.isna(sma_long.iloc[-2]):
            if sma_short.iloc[-1] > sma_long.iloc[-1] and sma_short.iloc[-2] <= sma_long.iloc[-2]:
                score += 0.3 # Altın Kesişim (Golden Cross)
            elif sma_short.iloc[-1] < sma_long.iloc[-1] and sma_short.iloc[-2] >= sma_long.iloc[-2]:
                score -= 0.3 # Ölüm Kesişimi (Death Cross)
            elif sma_short.iloc[-1] > sma_long.iloc[-1]:
                score += 0.1 # Yükseliş trendi
            else:
                score -= 0.1 # Düşüş trendi

        # Bollinger Bantları Skoru
        if (not bollinger_hband.empty and not pd.isna(bollinger_hband.iloc[-1]) and
            not bollinger_lband.empty and not pd.isna(bollinger_lband.iloc[-1]) and
            'close' in data and not data['close'].empty and not pd.isna(data['close'].iloc[-1])):
            if data['close'].iloc[-1] > bollinger_hband.iloc[-1]:
                score -= 0.2 # Üst bandın üzerinde, aşırı alım
            elif data['close'].iloc[-1] < bollinger_lband.iloc[-1]:
                score += 0.2 # Alt bandın altında, aşırı satım

        # ADX Skoru (Trend Gücü ve Yönü)
        if not adx.empty and not pd.isna(adx.iloc[-1]) and \
           not adx_pos.empty and not pd.isna(adx_pos.iloc[-1]) and \
           not adx_neg.empty and not pd.isna(adx_neg.iloc[-1]):
            if adx.iloc[-1] > 25: # Güçlü trend
                if adx_pos.iloc[-1] > adx_neg.iloc[-1]:
                    score += 0.2 # Güçlü yükseliş trendi
                else:
                    score -= 0.2 # Güçlü düşüş trendi
            elif adx.iloc[-1] < 20: # Zayıf trend
                score += 0.0 # Nötr

        # Skoru -1.0 ile 1.0 arasına normalize et
        normalized_score = np.tanh(score) # tanh fonksiyonu -1 ile 1 arasına sıkıştırır

        return float(normalized_score)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Hisse senedi fiyat trend skorunu hesaplar.')
    parser.add_argument('--symbol', type=str, default='AAPL', help='Hisse senedi sembolü (örn: AAPL, MSFT). Varsayılan: AAPL')
    parser.add_argument('--period', type=str, default='1y', help='Veri çekme periyodu (örn: 1y, 6mo, 1mo). Varsayılan: 1y')
    parser.add_argument('--interval', type=str, default='1d', help='Veri çekme aralığı (örn: 1d, 1wk, 1mo). Varsayılan: 1d')

    args = parser.parse_args()

    logger.info(f"--- {args.symbol} için Fiyat Trend Skoru Hesaplama ---")

    try:
        # yfinance ile veri çek
        ticker = yf.Ticker(args.symbol)
        data = ticker.history(period=args.period, interval=args.interval)

        if data.empty:
            logger.error(f"Hata: {args.symbol} için veri çekilemedi veya yeterli veri yok. Lütfen sembolü ve periyodu kontrol edin.")
        else:
            # Kapanış fiyatlarını al
            prices = data['Close']

            model = PriceTrendModel()
            technical_score = model.generate_score(prices)
            logger.info(f"{args.symbol} Teknik Yön Skoru: {technical_score:.2f}")

    except Exception as e:
        logger.error(f"Veri çekme veya skor hesaplama sırasında bir hata oluştu: {e}")
