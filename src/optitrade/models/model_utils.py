import pandas as pd
import ta

def _get_scaling_factor(interval: str) -> float:
    """
    Farklı zaman aralıkları için ölçeklendirme faktörünü döndürür.
    Varsayım: Temel aralık 1d (günlük) veridir.
    """
    if interval == "1d": return 1.0
    if interval == "4h": return 6.0  # 1 gün = 6 * 4 saat
    if interval == "15m": return 96.0 # 1 gün = 96 * 15 dakika
    return 1.0 # Bilinmeyen aralıklar için varsayılan

def create_features(df: pd.DataFrame, interval: str = "1d") -> pd.DataFrame:
    """
    Verilen DataFrame'den makine öğrenmesi modeli için özellikler oluşturur.
    Bu fonksiyon hem eğitim hem de tahmin için kullanılır.
    """
    df_copy = df.copy()

    scaling_factor = _get_scaling_factor(interval)

    # Fiyat değişimleri (ölçeklendirilmiş pencerelerle)
    df_copy['feature_price_change_1d'] = df_copy['Close'].pct_change(max(1, int(1 * scaling_factor)))
    df_copy['feature_price_change_3d'] = df_copy['Close'].pct_change(max(1, int(3 * scaling_factor)))
    df_copy['feature_price_change_7d'] = df_copy['Close'].pct_change(max(1, int(7 * scaling_factor)))
    
    # Volatilite (ölçeklendirilmiş pencerelerle)
    df_copy['feature_volatility_7d'] = df_copy['feature_price_change_1d'].rolling(window=max(1, int(7 * scaling_factor))).std()
    df_copy['feature_volatility_30d'] = df_copy['feature_price_change_1d'].rolling(window=max(1, int(30 * scaling_factor))).std()

    # RSI (ölçeklendirilmiş pencereyle)
    df_copy['feature_rsi_14d'] = ta.momentum.rsi(df_copy['Close'], window=max(1, int(14 * scaling_factor)))
    
    # MACD (ölçeklendirilmiş pencerelerle)
    macd_fast = max(1, int(12 * scaling_factor))
    macd_slow = max(1, int(26 * scaling_factor))
    macd_sign = max(1, int(9 * scaling_factor))
    macd = ta.trend.MACD(df_copy['Close'], window_slow=macd_slow, window_fast=macd_fast, window_sign=macd_sign)
    df_copy['feature_macd'] = macd.macd()
    df_copy['feature_macd_signal'] = macd.macd_signal()
    df_copy['feature_macd_diff'] = macd.macd_diff()

    # SMA (ölçeklendirilmiş pencerelerle)
    sma_50 = max(1, int(50 * scaling_factor))
    sma_200 = max(1, int(200 * scaling_factor))
    df_copy['feature_sma_50'] = ta.trend.sma_indicator(df_copy['Close'], window=sma_50)
    df_copy['feature_sma_200'] = ta.trend.sma_indicator(df_copy['Close'], window=sma_200)
    
    # Fiyatın 50 günlük ortalamaya göre konumu
    df_copy['feature_price_vs_sma50'] = (df_copy['Close'] - df_copy['feature_sma_50']) / df_copy['feature_sma_50']

    return df_copy