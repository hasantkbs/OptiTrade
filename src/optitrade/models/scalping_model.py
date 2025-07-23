import pandas as pd
import numpy as np
import ta.momentum
import ta.trend
import logging
from .. import config

logger = logging.getLogger(__name__)

class ScalpingModel:
    """
    Scalping stratejisi için hızlı tepki veren bir model.
    Kısa vadeli hareketli ortalamalar ve RSI gibi göstergeleri kullanır.
    """
    def __init__(self,
                 fast_ma_window: int = 5,
                 slow_ma_window: int = 13,
                 rsi_window: int = 7,
                 rsi_overbought: int = 70,
                 rsi_oversold: int = 30):
        self.fast_ma_window = fast_ma_window
        self.slow_ma_window = slow_ma_window
        self.rsi_window = rsi_window
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold

    def generate_score(self, data: pd.DataFrame, interval: str = '1m') -> float:
        logger.debug(f"ScalpingModel: generate_score called with interval: {interval}")

        # Interval'e göre pencere boyutlarını ayarla
        if interval == '1m':
            fast_ma_window = 3
            slow_ma_window = 8
            rsi_window = 5
        elif interval == '5m':
            fast_ma_window = 5
            slow_ma_window = 13
            rsi_window = 7
        elif interval == '15m':
            fast_ma_window = 8
            slow_ma_window = 21
            rsi_window = 9
        elif interval == '30m' or interval == '60m' or interval == '1h':
            fast_ma_window = 13
            slow_ma_window = 34
            rsi_window = 14
        else: # 1d, 1wk, 1mo ve diğerleri için varsayılan değerler
            fast_ma_window = self.fast_ma_window
            slow_ma_window = self.slow_ma_window
            rsi_window = self.rsi_window

        if data.empty or len(data) < max(fast_ma_window, slow_ma_window, rsi_window):
            logger.warning("ScalpingModel: Yeterli veri yok. Nötr skor döndürülüyor.")
            return 0.0

        close_prices = data['Close']

        # Kısa vadeli hareketli ortalamalar
        fast_ma = ta.trend.sma_indicator(close_prices, window=fast_ma_window)
        slow_ma = ta.trend.sma_indicator(close_prices, window=slow_ma_window)

        # RSI
        rsi = ta.momentum.rsi(close_prices, window=rsi_window)

        score = 0.0

        # MA Kesişimleri
        if not fast_ma.empty and not slow_ma.empty and \
           not pd.isna(fast_ma.iloc[-1]) and not pd.isna(slow_ma.iloc[-1]) and \
           not pd.isna(fast_ma.iloc[-2]) and not pd.isna(slow_ma.iloc[-2]):
            
            # Altın Kesişim (Golden Cross) - Alım sinyali
            if fast_ma.iloc[-1] > slow_ma.iloc[-1] and fast_ma.iloc[-2] <= slow_ma.iloc[-2]:
                score += 0.5
            # Ölüm Kesişimi (Death Cross) - Satış sinyali
            elif fast_ma.iloc[-1] < slow_ma.iloc[-1] and fast_ma.iloc[-2] >= slow_ma.iloc[-2]:
                score -= 0.5

        # RSI Aşırı Alım/Satım
        if not rsi.empty and not pd.isna(rsi.iloc[-1]):
            if rsi.iloc[-1] > self.rsi_overbought:
                score -= 0.3 # Aşırı alım, satış baskısı
            elif rsi.iloc[-1] < self.rsi_oversold:
                score += 0.3 # Aşırı satım, alış baskısı

        # Skoru -1.0 ile 1.0 arasına normalize et
        return float(np.tanh(score))

if __name__ == '__main__':
    import yfinance as yf
    import argparse

    parser = argparse.ArgumentParser(description='Scalping modeli için skor hesaplar.')
    parser.add_argument('--symbol', type=str, default='BTC-USD', help='Hisse senedi/kripto para sembolü.')
    parser.add_argument('--interval', type=str, default='1m', help='Veri çekme aralığı (örn: 1m, 5m).')
    parser.add_argument('--period', type=str, default='7d', help='Veri çekme periyodu (örn: 7d, 1mo).')

    args = parser.parse_args()

    logger.info(f"--- {args.symbol} için Scalping Skoru Hesaplama ({args.interval} aralığı) ---")

    try:
        ticker = yf.Ticker(args.symbol)
        # Scalping için kısa periyotlar ve aralıklar önemlidir
        data = ticker.history(period=args.period, interval=args.interval)

        if data.empty:
            logger.error(f"Hata: {args.symbol} için veri çekilemedi veya yeterli veri yok. Lütfen sembolü, periyodu ve aralığı kontrol edin.")
        else:
            model = ScalpingModel()
            scalping_score = model.generate_score(data)
            logger.info(f"{args.symbol} Scalping Skoru: {scalping_score:.2f}")

    except Exception as e:
        logger.error(f"Veri çekme veya skor hesaplama sırasında bir hata oluştu: {e}")
