
import pandas as pd
import ta
from typing import Dict, Any

def create_features(df: pd.DataFrame, interval: str = "1d", financial_ratios: Dict[str, Any] = None) -> pd.DataFrame:
    """
    Creates features for the machine learning model from the given DataFrame.
    This function is used for both training and prediction.
    """
    df_copy = df.copy()

    # Price changes
    df_copy['feature_price_change_1d'] = df_copy['Close'].pct_change(1)
    df_copy['feature_price_change_3d'] = df_copy['Close'].pct_change(3)
    df_copy['feature_price_change_7d'] = df_copy['Close'].pct_change(7)

    # Lagged price changes
    df_copy['feature_price_change_1d_lag1'] = df_copy['feature_price_change_1d'].shift(1)
    df_copy['feature_price_change_1d_lag2'] = df_copy['feature_price_change_1d'].shift(2)
    df_copy['feature_price_change_1d_lag3'] = df_copy['feature_price_change_1d'].shift(3)
    
    # Volatility
    df_copy['feature_volatility_7d'] = df_copy['feature_price_change_1d'].rolling(window=7).std()
    df_copy['feature_volatility_30d'] = df_copy['feature_price_change_1d'].rolling(window=30).std()

    # RSI
    df_copy['feature_rsi_14d'] = ta.momentum.rsi(df_copy['Close'], window=14)

    # Lagged RSI
    df_copy['feature_rsi_14d_lag1'] = df_copy['feature_rsi_14d'].shift(1)
    df_copy['feature_rsi_14d_lag2'] = df_copy['feature_rsi_14d'].shift(2)
    df_copy['feature_rsi_14d_lag3'] = df_copy['feature_rsi_14d'].shift(3)
    
    # MACD
    macd = ta.trend.MACD(df_copy['Close'], window_slow=26, window_fast=12, window_sign=9)
    df_copy['feature_macd'] = macd.macd()
    df_copy['feature_macd_signal'] = macd.macd_signal()
    df_copy['feature_macd_diff'] = macd.macd_diff()

    # SMA
    df_copy['feature_sma_50'] = ta.trend.sma_indicator(df_copy['Close'], window=50)
    df_copy['feature_sma_200'] = ta.trend.sma_indicator(df_copy['Close'], window=200)
    
    # Price position relative to 50-day SMA
    df_copy['feature_price_vs_sma50'] = (df_copy['Close'] - df_copy['feature_sma_50']) / df_copy['feature_sma_50']

    # Add financial ratios as features
    if financial_ratios:
        for ratio_name, ratio_value in financial_ratios.items():
            df_copy[f'feature_{ratio_name}'] = ratio_value

    return df_copy