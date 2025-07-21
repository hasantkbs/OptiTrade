import pandas as pd
import numpy as np
import ta.momentum
import ta.volatility
import ta.trend
import yfinance as yf
import argparse

class PriceTrendModel:
    """
    Fiyat verilerinden teknik analiz göstergeleriyle skor üreten model.
    Kullanılan göstergeler: RSI, MACD, Moving Averages, Bollinger Bands, Trendline kırılımları, ADX.
    """
    def __init__(self,
                 rsi_window: int = 14,
                 macd_fast_window: int = 12,
                 macd_slow_window: int = 26,
                 macd_signal_window: int = 9,
                 sma_short_window: int = 20,
                 sma_long_window: int = 50,
                 bollinger_window: int = 20,
                 bollinger_std: float = 2.0,
                 adx_window: int = 14):
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

    def generate_score(self, prices: pd.Series) -> float:
        """
        Haftalık/günlük kapanış fiyatlarından teknik yön skoru üretir.

        Args:
            prices (pd.Series): Kapanış fiyatlarını içeren pandas Serisi.

        Returns:
            float: Teknik yön skoru (örneğin: -1.0 = düşüş, 1.0 = yükseliş).
        """
        if not isinstance(prices, pd.Series):
            raise TypeError("Girdi fiyatları bir pandas Serisi olmalıdır.")
        if prices.empty:
            raise ValueError("Fiyat serisi boş olamaz.")

        # Yeterli veri olup olmadığını kontrol et
        min_data_points = max(self.rsi_window, self.macd_slow_window, self.sma_long_window, self.bollinger_window, self.adx_window)
        if len(prices) < min_data_points:
            # Yeterli veri yoksa nötr bir skor döndür
            print(f"Uyarı: Yeterli veri noktası yok ({len(prices)} mevcut, en az {min_data_points} gerekli). Nötr skor döndürülüyor.")
            return 0.0

        # Göstergeleri hesapla
        # RSI
        rsi = ta.momentum.rsi(prices, window=self.rsi_window)

        # MACD
        macd = ta.trend.macd(prices, window_fast=self.macd_fast_window, window_slow=self.macd_slow_window)
        macd_signal = ta.trend.macd_signal(prices, window_fast=self.macd_fast_window, window_slow=self.macd_slow_window, window_sign=self.macd_signal_window)
        macd_diff = ta.trend.macd_diff(prices, window_fast=self.macd_fast_window, window_slow=self.macd_slow_window, window_sign=self.macd_signal_window)

        # Hareketli Ortalamalar
        sma_short = ta.trend.sma_indicator(prices, window=self.sma_short_window)
        sma_long = ta.trend.sma_indicator(prices, window=self.sma_long_window)

        # Bollinger Bantları
        bollinger_hband = ta.volatility.bollinger_hband(prices, window=self.bollinger_window, window_dev=self.bollinger_std)
        bollinger_lband = ta.volatility.bollinger_lband(prices, window=self.bollinger_window, window_dev=self.bollinger_std)

        # ADX
        # ADX için high, low, close fiyatlarına ihtiyaç var. Sadece 'prices' (kapanış) verildiği için
        # bu kısım için bir varsayım yapmamız gerekiyor veya modelin girdisini değiştirmemiz gerekiyor.
        # Şimdilik, basitlik adına 'prices'ı hem high, hem low, hem de close olarak kullanacağım.
        # Gerçek bir uygulamada, bu kısım OHLCV verisi alacak şekilde güncellenmelidir.
        adx = ta.trend.adx(prices, prices, prices, window=self.adx_window) # high, low, close
        adx_pos = ta.trend.adx_pos(prices, prices, prices, window=self.adx_window)
        adx_neg = ta.trend.adx_neg(prices, prices, prices, window=self.adx_window)

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
        if not bollinger_hband.empty and not pd.isna(bollinger_hband.iloc[-1]) and \
           not bollinger_lband.empty and not pd.isna(bollinger_lband.iloc[-1]) and \
           not prices.empty and not pd.isna(prices.iloc[-1]):
            if prices.iloc[-1] > bollinger_hband.iloc[-1]:
                score -= 0.2 # Üst bandın üzerinde, aşırı alım
            elif prices.iloc[-1] < bollinger_lband.iloc[-1]:
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

    print(f"\n--- {args.symbol} için Fiyat Trend Skoru Hesaplama ---")

    try:
        # yfinance ile veri çek
        ticker = yf.Ticker(args.symbol)
        data = ticker.history(period=args.period, interval=args.interval)

        if data.empty:
            print(f"Hata: {args.symbol} için veri çekilemedi veya yeterli veri yok. Lütfen sembolü ve periyodu kontrol edin.")
        else:
            # Kapanış fiyatlarını al
            prices = data['Close']

            model = PriceTrendModel()
            technical_score = model.generate_score(prices)
            print(f"{args.symbol} Teknik Yön Skoru: {technical_score:.2f}")

    except Exception as e:
        print(f"Veri çekme veya skor hesaplama sırasında bir hata oluştu: {e}")
