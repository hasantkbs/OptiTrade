import pandas as pd
import numpy as np

class CryptoTechnicalIndicators:
    def __init__(self):
        pass

    def add_crypto_indicators(self, df):
        """Kripto paralara özel teknik göstergeler"""
        if df.empty or len(df) == 0:
            return df

        df = df.copy()

        # Standart teknik göstergeler
        df = self.add_volatility_indicators(df)
        df = self.add_volume_indicators(df)
        df = self.add_momentum_indicators(df)
        df = self.add_trend_indicators(df)

        # Kripto spesifik göstergeler
        df = self.add_crypto_specific_indicators(df)

        return df

    def add_volatility_indicators(self, df):
        """Volatilite göstergeleri"""
        if df.empty or len(df) == 0:
            return df

        try:
            # Gerçek aralık (True Range)
            df['TR'] = np.maximum(
                np.maximum(
                    df['high'] - df['low'],
                    abs(df['high'] - df['close'].shift(1))
                ),
                abs(df['low'] - df['close'].shift(1))
            )

            # ATR (Average True Range)
            df['ATR_14'] = df['TR'].rolling(window=14).mean()

            # Volatilite yüzdesi
            df['Volatility'] = (df['high'] - df['low']) / df['close'] * 100

        except Exception as e:
            print(f"Volatility indicators error: {e}")
            df['TR'] = 0
            df['ATR_14'] = 0
            df['Volatility'] = 0

        return df

    def add_volume_indicators(self, df):
        """Hacim göstergeleri"""
        if df.empty or len(df) == 0:
            return df

        try:
            # Hacim hareketli ortalamaları
            df['Volume_MA_7'] = df['volume'].rolling(window=7).mean()
            df['Volume_MA_14'] = df['volume'].rolling(window=14).mean()

            # Hacim oranı
            df['Volume_Ratio'] = df['volume'] / df['Volume_MA_14']
            df['Volume_Ratio'] = df['Volume_Ratio'].fillna(1)

            # Hacim artış oranı
            df['Volume_Change'] = df['volume'].pct_change().fillna(0)

        except Exception as e:
            print(f"Volume indicators error: {e}")
            df['Volume_MA_7'] = 0
            df['Volume_MA_14'] = 0
            df['Volume_Ratio'] = 1
            df['Volume_Change'] = 0

        return df

    def add_momentum_indicators(self, df):
        """Momentum göstergeleri"""
        if df.empty or len(df) == 0:
            return df

        try:
            # RSI
            df['RSI'] = self.calculate_rsi(df['close'])

            # Stochastic RSI
            df['Stoch_RSI'] = self.calculate_stochastic_rsi(df['RSI'])

            # Williams %R
            df['Williams_R'] = self.calculate_williams_r(df)

        except Exception as e:
            print(f"Momentum indicators error: {e}")
            df['RSI'] = 50
            df['Stoch_RSI'] = 50
            df['Williams_R'] = -50

        return df

    def add_trend_indicators(self, df):
        """Trend göstergeleri"""
        if df.empty or len(df) == 0:
            return df

        try:
            # Hareketli ortalamalar
            df['MA_7'] = df['close'].rolling(window=7).mean()
            df['MA_25'] = df['close'].rolling(window=25).mean()
            df['MA_99'] = df['close'].rolling(window=99).mean()

            # EMA
            df['EMA_12'] = df['close'].ewm(span=12).mean()
            df['EMA_26'] = df['close'].ewm(span=26).mean()

            # MACD
            df['MACD'] = df['EMA_12'] - df['EMA_26']
            df['MACD_Signal'] = df['MACD'].ewm(span=9).mean()
            df['MACD_Histogram'] = df['MACD'] - df['MACD_Signal']

        except Exception as e:
            print(f"Trend indicators error: {e}")
            df['MA_7'] = df['close']
            df['MA_25'] = df['close']
            df['MA_99'] = df['close']
            df['EMA_12'] = df['close']
            df['EMA_26'] = df['close']
            df['MACD'] = 0
            df['MACD_Signal'] = 0
            df['MACD_Histogram'] = 0

        return df

    def add_crypto_specific_indicators(self, df):
        """Kripto paralara özel göstergeler"""
        if df.empty or len(df) == 0:
            return df

        try:
            # Fiyat değişimi oranı (24s saat)
            df['Price_Change_24h'] = df['close'].pct_change(24) * 100

            # Fiyat değişimi oranı (1 saat)
            df['Price_Change_1h'] = df['close'].pct_change(1) * 100

            # Fiyat değişimi oranı (4 saat)
            df['Price_Change_4h'] = df['close'].pct_change(4) * 100

            # Momentum gücü
            df['Momentum_Strength'] = df['Price_Change_24h'] / (df['Volatility'] + 0.001)  # 0'a bölme hatası önlemek için

            # Hacim-Fiyat trendi
            df['Volume_Price_Trend'] = (df['volume'] * df['close']).pct_change().fillna(0)

        except Exception as e:
            print(f"Crypto specific indicators error: {e}")
            df['Price_Change_24h'] = 0
            df['Price_Change_1h'] = 0
            df['Price_Change_4h'] = 0
            df['Momentum_Strength'] = 0
            df['Volume_Price_Trend'] = 0

        return df

    def calculate_rsi(self, prices, window=14):
        """RSI hesaplama"""
        try:
            delta = prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
            rs = gain / (loss + 0.001)  # 0'a bölme hatası önlemek için
            rsi = 100 - (100 / (1 + rs))
            return rsi.fillna(50)
        except:
            return pd.Series([50] * len(prices)) if len(prices) > 0 else pd.Series([50])

    def calculate_stochastic_rsi(self, rsi, window=14):
        """Stochastic RSI hesaplama"""
        try:
            min_rsi = rsi.rolling(window=window).min()
            max_rsi = rsi.rolling(window=window).max()
            stoch_rsi = (rsi - min_rsi) / (max_rsi - min_rsi + 0.001) * 100  # 0'a bölme hatası önlemek için
            return stoch_rsi.fillna(50)
        except:
            return pd.Series([50] * len(rsi)) if len(rsi) > 0 else pd.Series([50])

    def calculate_williams_r(self, df, window=14):
        """Williams %R hesaplama"""
        try:
            highest_high = df['high'].rolling(window=window).max()
            lowest_low = df['low'].rolling(window=window).min()
            williams_r = (highest_high - df['close']) / (highest_high - lowest_low + 0.001) * -100 # 0'a bölme hatası önlemek için
            return williams_r.fillna(-50)
        except:
            return pd.Series([-50] * len(df)) if len(df) > 0 else pd.Series([-50])