import pandas as pd
import ta
import numpy as np

def add_all_ta_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Verilen DataFrame'e teknik analiz (TA) özelliklerini ekler.
    """
    data = df.copy()
    close = data['close']
    high = data['high']
    low = data['low']

    # Teknik Göstergeler
    data['feature_rsi'] = ta.momentum.rsi(close, window=14)
    data['feature_macd_diff'] = ta.trend.macd_diff(close, window_slow=26, window_fast=12, window_sign=9)
    bollinger = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    data['feature_bollinger_hband_indicator'] = bollinger.bollinger_hband_indicator()
    data['feature_bollinger_lband_indicator'] = bollinger.bollinger_lband_indicator()
    adx_indicator = ta.trend.ADXIndicator(high, low, close, window=14)
    data['feature_trend_strength'] = adx_indicator.adx()
    sma_short = ta.trend.sma_indicator(close, window=12)
    sma_long = ta.trend.sma_indicator(close, window=50)
    data['feature_sma_crossover'] = (sma_short > sma_long).astype(int)

    # Yeni Özellikler: Volatilite ve Fiyat Farkları
    data['feature_atr'] = ta.volatility.average_true_range(high, low, close, window=14)
    data['feature_high_low_diff'] = high - low
    data['feature_close_open_diff'] = close - data['open']

    # Gecikmeli Özellikler (Lagged Features)
    important_features = ['close', 'feature_rsi', 'feature_macd_diff', 'feature_trend_strength', 'feature_atr', 'feature_high_low_diff', 'feature_close_open_diff']
    for feature in important_features:
        for i in range(1, 4):
            data[f'{feature}_lag_{i}'] = data[feature].shift(i)

    # Destek ve Direnç Özellikleri eklenecek yer
    data = _add_support_resistance_features(data)

    return data

def _add_support_resistance_features(data: pd.DataFrame, window: int = 20, tolerance_pct: float = 0.005, min_touches: int = 10) -> pd.DataFrame:
    """
    Adds support and resistance features to the DataFrame.
    Identifies levels with multiple touches within a given window and tolerance.
    """
    df = data.copy()
    df['is_local_min'] = (df['low'] == df['low'].rolling(window=window, center=True).min())
    df['is_local_max'] = (df['high'] == df['high'].rolling(window=window, center=True).max())

    support_levels = []
    resistance_levels = []

    # Identify potential levels
    for i in range(len(df)):
        if df.loc[i, 'is_local_min']:
            support_levels.append(df.loc[i, 'low'])
        if df.loc[i, 'is_local_max']:
            resistance_levels.append(df.loc[i, 'high'])

    # Group similar levels and count touches
    def get_significant_levels(levels, price_series, tolerance_pct, min_touches):
        significant_levels = {}
        for level in sorted(list(set(levels))):
            touches = 0
            for price in price_series:
                if abs(price - level) / level <= tolerance_pct:
                    touches += 1
            if touches >= min_touches:
                # Average the levels that are close to each other
                if not significant_levels:
                    significant_levels[level] = [level]
                else:
                    found_group = False
                    for existing_level in significant_levels:
                        if abs(level - existing_level) / existing_level <= tolerance_pct:
                            significant_levels[existing_level].append(level)
                            found_group = True
                            break
                    if not found_group:
                        significant_levels[level] = [level]
        
        final_levels = {}
        for group_key, group_values in significant_levels.items():
            avg_level = np.mean(group_values)
            final_levels[avg_level] = len(group_values) # Store count of distinct levels in group
        return final_levels

    sig_supports = get_significant_levels(support_levels, df['low'], tolerance_pct, min_touches)
    sig_resistances = get_significant_levels(resistance_levels, df['high'], tolerance_pct, min_touches)

    # Add features based on these levels
    df['feature_nearest_support_dist'] = np.nan
    df['feature_nearest_resistance_dist'] = np.nan
    df['feature_is_at_support'] = 0
    df['feature_is_at_resistance'] = 0

    for i in range(len(df)):
        current_price = df.loc[i, 'close']
        
        # Nearest Support
        min_s_dist = float('inf')
        for s_level in sig_supports:
            dist = current_price - s_level
            if dist >= 0 and dist < min_s_dist: # Price is above or at support
                min_s_dist = dist
        if min_s_dist != float('inf'):
            df.loc[i, 'feature_nearest_support_dist'] = min_s_dist
            if min_s_dist / current_price <= tolerance_pct:
                df.loc[i, 'feature_is_at_support'] = 1

        # Nearest Resistance
        min_r_dist = float('inf')
        for r_level in sig_resistances:
            dist = r_level - current_price
            if dist >= 0 and dist < min_r_dist: # Price is below or at resistance
                min_r_dist = dist
        if min_r_dist != float('inf'):
            df.loc[i, 'feature_nearest_resistance_dist'] = min_r_dist
            if min_r_dist / current_price <= tolerance_pct:
                df.loc[i, 'feature_is_at_resistance'] = 1
    
    # Store the significant levels for plotting later
    df.significant_supports = list(sig_supports.keys())
    df.significant_resistances = list(sig_resistances.keys())

    return df