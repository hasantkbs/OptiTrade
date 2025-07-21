import pandas as pd
import numpy as np
import ta.momentum
import ta.trend
from scipy.signal import argrelextrema
import yfinance as yf
import argparse

class DivergenceDetectionModel:
    """
    RSI veya MACD ile fiyat arasındaki uyumsuzlukları (divergence) bulan model.
    Kullanır: argrelextrema + RSI/MACD.
    Girdi: Fiyat geçmişi ve ilgili gösterge (RSI veya MACD).
    Çıktı: Sinyal (bullish/bearish) veya skor.
    """
    def __init__(self,
                 indicator_window: int = 14, # RSI veya ADX için
                 macd_fast_window: int = 12,
                 macd_slow_window: int = 26,
                 macd_signal_window: int = 9,
                 extrema_order: int = 5, # argrelextrema için komşu nokta sayısı
                 divergence_lookback_period: int = 20): # Uyumsuzluk arama penceresi
        """
        Modeli başlatır ve parametreleri ayarlar.

        Args:
            indicator_window (int): RSI veya diğer göstergeler için pencere boyutu.
            macd_fast_window (int): MACD hızlı EMA penceresi.
            macd_slow_window (int): MACD yavaş EMA penceresi.
            macd_signal_window (int): MACD sinyal hattı penceresi.
            extrema_order (int): Yerel ekstremumları bulmak için kullanılacak komşu nokta sayısı.
            divergence_lookback_period (int): Uyumsuzlukları aramak için geçmişe dönük gün sayısı.
        """
        self.indicator_window = indicator_window
        self.macd_fast_window = macd_fast_window
        self.macd_slow_window = macd_slow_window
        self.macd_signal_window = macd_signal_window
        self.extrema_order = extrema_order
        self.divergence_lookback_period = divergence_lookback_period

    def _find_extrema(self, series: pd.Series, find_max: bool = True) -> pd.Series:
        """
        Bir serideki yerel maksimum veya minimum noktaları bulur.
        """
        if len(series) < self.extrema_order * 2 + 1:
            return pd.Series(dtype=float) # Yeterli veri yoksa boş seri döndür

        if find_max:
            extrema_indices = argrelextrema(series.values, np.greater, order=self.extrema_order)[0]
        else:
            extrema_indices = argrelextrema(series.values, np.less, order=self.extrema_order)[0]
        return series.iloc[extrema_indices]

    def detect_divergence(self, data: pd.DataFrame, indicator_type: str = 'rsi') -> dict:
        """
        Fiyat ve gösterge arasındaki uyumsuzlukları tespit eder.

        Args:
            data (pd.DataFrame): OHLCV verilerini içeren pandas DataFrame.
            indicator_type (str): Kullanılacak gösterge ('rsi', 'macd_line' veya 'macd_hist').

        Returns:
            dict: Tespit edilen uyumsuzlukları içeren sözlük (örn: {'bullish': True, 'bearish': False, 'score': 0.5}).
        """
        required_columns = ['High', 'Low', 'Close']
        if not isinstance(data, pd.DataFrame) or data.empty or not all(col in data.columns for col in required_columns):
            raise ValueError(f"DataFrame boş olamaz ve {required_columns} sütunlarını içermelidir.")

        prices = data['Close']
        high_prices = data['High']
        low_prices = data['Low']

        if len(prices) < max(self.indicator_window, self.macd_slow_window, self.extrema_order * 2 + 1):
            return {'bullish': False, 'bearish': False, 'score': 0.0, 'message': 'Yeterli veri yok.'}

        indicator = None
        if indicator_type == 'rsi':
            indicator = ta.momentum.rsi(prices, window=self.indicator_window)
        elif indicator_type == 'macd_line':
            indicator = ta.trend.macd(prices, window_fast=self.macd_fast_window, window_slow=self.macd_slow_window)
        elif indicator_type == 'macd_hist':
            indicator = ta.trend.macd_diff(prices, window_fast=self.macd_fast_window, window_slow=self.macd_slow_window, window_sign=self.macd_signal_window)
        else:
            return {'bullish': False, 'bearish': False, 'score': 0.0, 'message': 'Geçersiz gösterge tipi.'}

        if indicator.empty or indicator.isnull().all():
            return {'bullish': False, 'bearish': False, 'score': 0.0, 'message': 'Gösterge verisi eksik veya geçersiz.'}

        # Sadece son 'divergence_lookback_period' kadar veriyi al
        prices_slice = prices.iloc[-self.divergence_lookback_period:].dropna()
        indicator_slice = indicator.iloc[-self.divergence_lookback_period:].dropna()

        if len(prices_slice) < self.extrema_order * 2 + 1 or len(indicator_slice) < self.extrema_order * 2 + 1:
            return {'bullish': False, 'bearish': False, 'score': 0.0, 'message': 'Hizalanmış veri yeterli değil.'}

        # Fiyat ve gösterge ekstremumlarını bul
        price_highs = self._find_extrema(prices_slice, find_max=True)
        price_lows = self._find_extrema(prices_slice, find_max=False)
        indicator_highs = self._find_extrema(indicator_slice, find_max=True)
        indicator_lows = self._find_extrema(indicator_slice, find_max=False)

        bullish_divergence = False
        bearish_divergence = False
        divergence_score = 0.0

        # Boğa Uyumsuzluğu (Bullish Divergence): Fiyat daha düşük dip yaparken, gösterge daha yüksek dip yapar.
        # Fiyat düşerken gösterge yükselir.
        if len(price_lows) >= 2 and len(indicator_lows) >= 2:
            for i in range(len(price_lows) - 1, 0, -1):
                current_price_low = price_lows.iloc[i]
                prev_price_low = price_lows.iloc[i-1]

                if current_price_low < prev_price_low: # Fiyat daha düşük dip yapıyor
                    # İlgili gösterge diplerini bul
                    # Fiyat dibinin oluştuğu tarihe yakın gösterge dibini ara
                    for j in range(len(indicator_lows) - 1, 0, -1):
                        current_indicator_low = indicator_lows.iloc[j]
                        prev_indicator_low = indicator_lows.iloc[j-1]

                        # İndekslerin sırasını kontrol et (fiyat dibi ve gösterge dibi aynı yönde olmalı)
                        if indicator_lows.index[j] > indicator_lows.index[j-1] and \
                           prices_slice.index.get_loc(price_lows.index[i]) > prices_slice.index.get_loc(price_lows.index[i-1]):
                            
                            if current_indicator_low > prev_indicator_low: # Gösterge daha yüksek dip yapıyor
                                bullish_divergence = True
                                # Uyumsuzluğun gücüne göre skor ata
                                score_strength = abs(current_indicator_low - prev_indicator_low) / (indicator_slice.max() - indicator_slice.min() + 1e-9)
                                divergence_score += score_strength * 0.7 # Maksimum 0.7 katkı
                                break # İlk uyumsuzluğu bulduktan sonra çık
                    if bullish_divergence: break

        # Ayı Uyumsuzluğu (Bearish Divergence): Fiyat daha yüksek zirve yaparken, gösterge daha düşük zirve yapar.
        # Fiyat yükselirken gösterge düşer.
        if len(price_highs) >= 2 and len(indicator_highs) >= 2:
            for i in range(len(price_highs) - 1, 0, -1):
                current_price_high = price_highs.iloc[i]
                prev_price_high = price_highs.iloc[i-1]

                if current_price_high > prev_price_high: # Fiyat daha yüksek zirve yapıyor
                    # İlgili gösterge zirvelerini bul
                    for j in range(len(indicator_highs) - 1, 0, -1):
                        current_indicator_high = indicator_highs.iloc[j]
                        prev_indicator_high = indicator_highs.iloc[j-1]

                        # İndekslerin sırasını kontrol et
                        if indicator_highs.index[j] > indicator_highs.index[j-1] and \
                           prices_slice.index.get_loc(price_highs.index[i]) > prices_slice.index.get_loc(price_highs.index[i-1]):

                            if current_indicator_high < prev_indicator_high: # Gösterge daha düşük zirve yapıyor
                                bearish_divergence = True
                                # Uyumsuzluğun gücüne göre skor ata
                                score_strength = abs(current_indicator_high - prev_indicator_high) / (indicator_slice.max() - indicator_slice.min() + 1e-9)
                                divergence_score -= score_strength * 0.7 # Maksimum 0.7 katkı
                                break # İlk uyumsuzluğu bulduktan sonra çık
                    if bearish_divergence: break

        # Skoru -1.0 ile 1.0 arasına normalize et
        final_score = np.tanh(divergence_score) # tanh fonksiyonu -1 ile 1 arasına sıkıştırır

        return {
            'bullish': bullish_divergence,
            'bearish': bearish_divergence,
            'score': float(final_score),
            'message': 'Uyumsuzluk tespit edildi.' if bullish_divergence or bearish_divergence else 'Uyumsuzluk tespit edilmedi.'
        }

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Fiyat ve gösterge arasındaki uyumsuzlukları tespit eder.')
    parser.add_argument('--symbol', type=str, default='BTC-USD', help='Hisse senedi/kripto para sembolü (örn: BTC-USD, AAPL). Varsayılan: BTC-USD')
    parser.add_argument('--period', type=str, default='1y', help='Veri çekme periyodu (örn: 1y, 6mo, 1mo). Varsayılan: 1y')
    parser.add_argument('--interval', type=str, default='1d', help='Veri çekme aralığı (örn: 1d, 1wk, 1mo). Varsayılan: 1d')
    parser.add_argument('--indicator', type=str, default='rsi', choices=['rsi', 'macd_line', 'macd_hist'], help='Kullanılacak gösterge (rsi, macd_line veya macd_hist). Varsayılan: rsi')

    args = parser.parse_args()

    print(f"\n--- {args.symbol} için Uyumsuzluk Tespiti ({args.indicator.upper()}) ---")

    try:
        ticker = yf.Ticker(args.symbol)
        data = ticker.history(period=args.period, interval=args.interval)

        if data.empty:
            print(f"Hata: {args.symbol} için veri çekilemedi veya yeterli veri yok. Lütfen sembolü ve periyodu kontrol edin.")
        else:
            model = DivergenceDetectionModel()
            divergence_result = model.detect_divergence(data, indicator_type=args.indicator)

            print(f"{args.symbol} Uyumsuzluk Sonucu: {divergence_result['message']}")
            print(f"  Boğa Uyumsuzluğu: {divergence_result['bullish']}")
            print(f"  Ayı Uyumsuzluğu: {divergence_result['bearish']}")
            print(f"  Uyumsuzluk Skoru: {divergence_result['score']:.2f}")

    except Exception as e:
        print(f"Veri çekme veya uyumsuzluk tespiti sırasında bir hata oluştu: {e}")
