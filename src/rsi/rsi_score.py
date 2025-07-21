import yfinance as yf
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
import ta

def detect_divergence(df):
    divergences = []
    price_low_indices = df.index[df['price_min'].notna()]
    price_high_indices = df.index[df['price_max'].notna()]

    # Bullish divergence
    if len(price_low_indices) >= 2:
        for i in range(1, len(price_low_indices)):
            prev_idx, curr_idx = price_low_indices[i-1], price_low_indices[i]
            if df.loc[df.index == curr_idx, 'price_min'].item() < df.loc[df.index == prev_idx, 'price_min'].item() and \
               df.loc[df.index == curr_idx, 'rsi'].item() > df.loc[df.index == prev_idx, 'rsi'].item():
                divergences.append((curr_idx, 'Bullish'))

    # Bearish divergence
    if len(price_high_indices) >= 2:
        for i in range(1, len(price_high_indices)):
            prev_idx, curr_idx = price_high_indices[i-1], price_high_indices[i]
            if df.loc[df.index == curr_idx, 'price_max'].item() > df.loc[df.index == prev_idx, 'price_max'].item() and \
               df.loc[df.index == curr_idx, 'rsi'].item() < df.loc[df.index == prev_idx, 'rsi'].item():
                divergences.append((curr_idx, 'Bearish'))

    return divergences

def calculate_rsi_score(df, divergences):
    score = 50
    latest_rsi = df['rsi'].iloc[-1]

    if latest_rsi > 70:
        score -= (latest_rsi - 70) * 1.5
    elif latest_rsi < 30:
        score += (30 - latest_rsi) * 1.5
    else:
        score -= (latest_rsi - 50)

    if divergences:
        latest_divergence_date, latest_divergence_type = divergences[-1]
        # Check if the divergence is recent (within the last 8 periods of the interval)
        if (df.index[-1] - latest_divergence_date).total_seconds() < (df.index[-1] - df.index[-9]).total_seconds():
            if latest_divergence_type == 'Bullish':
                score += 30
                print(f"Yakın zamanda Bullish uyumsuzluk tespit edildi (+30 puan)")
            elif latest_divergence_type == 'Bearish':
                score -= 30
                print(f"Yakın zamanda Bearish uyumsuzluk tespit edildi (-30 puan)")

    return max(0, min(100, score))

def analyze_timeframe(ticker, period, interval):
    print(f"--- {interval.upper()} Zaman Aralığı Analizi ---")
    data = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)

    if data.empty:
        print(f"{interval} için veri indirilemedi.\n")
        return

    # Ensure close is a 1D Series
    close = data['Close'].squeeze()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    data['rsi'] = ta.momentum.RSIIndicator(close=close, window=14).rsi()

    order = 5
    price_min_idx = argrelextrema(close.values, np.less_equal, order=order)[0]
    price_max_idx = argrelextrema(close.values, np.greater_equal, order=order)[0]

    data['price_min'] = np.nan
    if len(price_min_idx) > 0:
        data.loc[data.index[price_min_idx], 'price_min'] = close.iloc[price_min_idx]
    data['price_max'] = np.nan
    if len(price_max_idx) > 0:
        data.loc[data.index[price_max_idx], 'price_max'] = close.iloc[price_max_idx]

    divergences = detect_divergence(data)
    final_score = calculate_rsi_score(data, divergences)

    print(f"Son RSI Değeri: {data['rsi'].iloc[-1]:.2f}")
    print(f"RSI Skoru: {final_score:.2f} / 100")

    if final_score > 70:
        print("Yorum: Güçlü yükseliş potansiyeli.")
    elif final_score > 55:
        print("Yorum: Yükseliş potansiyeli.")
    elif final_score < 30:
        print("Yorum: Güçlü düşüş potansiyeli.")
    elif final_score < 45:
        print("Yorum: Düşüş potansiyeli.")
    else:
        print("Yorum: Nötr.")
    print("="*35 + "\n")

# Ana İşlem
timeframes = {
    "1wk": "2y",
    "1d": "1y",
    "4h": "6mo"
}

for interval, period in timeframes.items():
    analyze_timeframe("BTC-USD", period, interval)
