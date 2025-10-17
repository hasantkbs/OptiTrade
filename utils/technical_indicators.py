import pandas as pd
import numpy as np

class TechnicalIndicators:
    def __init__(self):
        pass

    def add_all_indicators(self, df):
        """Tüm teknik göstergeleri ekle"""
        df = df.copy()

        # Trend Göstergeleri
        df = self.add_moving_averages(df)
        df = self.add_bollinger_bands(df)
        df = self.add_macd(df)

        # Momentum Göstergeleri
        df = self.add_rsi(df)
        df = self.add_stochastic_oscillator(df)
        df = self.add_williams_r(df)

        # Volatilite Göstergeleri
        df = self.add_atr(df)
        df = self.add_cci(df)

        # Hacim Göstergeleri
        df = self.add_obv(df)
        df = self.add_vwap(df)

        # Diğer Göstergeler
        df = self.add_ichimoku_cloud(df)

        return df

    def add_moving_averages(self, df):
        """Hareketli ortalamalar"""
        df['MA_5'] = df['Close'].rolling(window=5).mean()
        df['MA_10'] = df['Close'].rolling(window=10).mean()
        df['MA_20'] = df['Close'].rolling(window=20).mean()
        df['MA_50'] = df['Close'].rolling(window=50).mean()
        df['MA_200'] = df['Close'].rolling(window=200).mean()

        # Üssel hareketli ortalamalar
        df['EMA_12'] = df['Close'].ewm(span=12).mean()
        df['EMA_26'] = df['Close'].ewm(span=26).mean()

        return df

    def add_bollinger_bands(self, df, window=20, num_std=2):
        """Bollinger Bands"""
        df['BB_Middle'] = df['Close'].rolling(window=window).mean()
        bb_std = df['Close'].rolling(window=window).std()
        df['BB_Upper'] = df['BB_Middle'] + (bb_std * num_std)
        df['BB_Lower'] = df['BB_Middle'] - (bb_std * num_std)
        df['BB_Width'] = df['BB_Upper'] - df['BB_Lower']
        df['BB_Position'] = (df['Close'] - df['BB_Lower']) / df['BB_Width']

        return df

    def add_rsi(self, df, window=14):
        """Relative Strength Index"""
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        return df

    def add_macd(self, df):
        """MACD"""
        df['MACD_Line'] = df['EMA_12'] - df['EMA_26']
        df['MACD_Signal'] = df['MACD_Line'].ewm(span=9).mean()
        df['MACD_Histogram'] = df['MACD_Line'] - df['MACD_Signal']

        return df

    def add_stochastic_oscillator(self, df, k_window=14, d_window=3):
        """Stochastic Oscillator"""
        low_min = df['Low'].rolling(window=k_window).min()
        high_max = df['High'].rolling(window=k_window).max()
        df['Stochastic_K'] = 100 * ((df['Close'] - low_min) / (high_max - low_min))
        df['Stochastic_D'] = df['Stochastic_K'].rolling(window=d_window).mean()

        return df

    def add_williams_r(self, df, window=14):
        """Williams %R"""
        high_max = df['High'].rolling(window=window).max()
        low_min = df['Low'].rolling(window=window).min()
        df['Williams_R'] = -100 * ((high_max - df['Close']) / (high_max - low_min))

        return df

    def add_atr(self, df, window=14):
        """Average True Range"""
        high_low = df['High'] - df['Low']
        high_close = abs(df['High'] - df['Close'].shift())
        low_close = abs(df['Low'] - df['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        df['ATR'] = true_range.rolling(window=window).mean()

        return df

    def add_cci(self, df, window=20):
        """Commodity Channel Index"""
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        sma_tp = tp.rolling(window=window).mean()
        mean_deviation = tp.rolling(window=window).apply(lambda x: abs(x - x.mean()).mean())
        df['CCI'] = (tp - sma_tp) / (0.015 * mean_deviation)

        return df

    def add_obv(self, df):
        """On-Balance Volume"""
        obv = [0]
        for i in range(1, len(df)):
            if df['Close'].iloc[i] > df['Close'].iloc[i-1]:
                obv.append(obv[-1] + df['Volume'].iloc[i])
            elif df['Close'].iloc[i] < df['Close'].iloc[i-1]:
                obv.append(obv[-1] - df['Volume'].iloc[i])
            else:
                obv.append(obv[-1])
        df['OBV'] = obv

        return df

    def add_vwap(self, df):
        """Volume Weighted Average Price"""
        typical_price = (df['High'] + df['Low'] + df['Close']) / 3
        cumulative_tp_volume = (typical_price * df['Volume']).cumsum()
        cumulative_volume = df['Volume'].cumsum()
        df['VWAP'] = cumulative_tp_volume / cumulative_volume

        return df

    def add_ichimoku_cloud(self, df):
        """Ichimoku Cloud"""
        # Tenkan-sen (Conversion Line)
        nine_period_high = df['High'].rolling(window=9).max()
        nine_period_low = df['Low'].rolling(window=9).min()
        df['Tenkan_sen'] = (nine_period_high + nine_period_low) / 2

        # Kijun-sen (Base Line)
        twenty_six_period_high = df['High'].rolling(window=26).max()
        twenty_six_period_low = df['Low'].rolling(window=26).min()
        df['Kijun_sen'] = (twenty_six_period_high + twenty_six_period_low) / 2

        # Senkou Span A (Leading Span A)
        df['Senkou_span_a'] = ((df['Tenkan_sen'] + df['Kijun_sen']) / 2).shift(26)

        # Senkou Span B (Leading Span B)
        fifty_two_period_high = df['High'].rolling(window=52).max()
        fifty_two_period_low = df['Low'].rolling(window=52).min()
        df['Senkou_span_b'] = ((fifty_two_period_high + fifty_two_period_low) / 2).shift(26)

        # Chikou Span (Lagging Span)
        df['Chikou_span'] = df['Close'].shift(-26)

        return df
