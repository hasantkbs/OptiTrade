import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import numpy as np

# Teknik göstergeleri hesaplamak için yardımcı fonksiyonlar
def calculate_rsi(data, window):
    diff = data.diff(1).dropna()
    up, down = diff.copy(), diff.copy()
    up[up < 0] = 0
    down[down > 0] = 0
    roll_up = up.ewm(span=window).mean()
    roll_down = down.abs().ewm(span=window).mean()
    rs = roll_up / roll_down
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi

def calculate_macd(data, fast_period, slow_period, signal_period):
    ema_fast = data.ewm(span=fast_period, adjust=False).mean()
    ema_slow = data.ewm(span=slow_period, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal = macd.ewm(span=signal_period, adjust=False).mean()
    return macd, signal

def calculate_bollinger_bands(data, window, num_std_dev):
    sma = data.rolling(window=window).mean()
    std_dev = data.rolling(window=window).std()
    upper_band = sma + (std_dev * num_std_dev)
    lower_band = sma - (std_dev * num_std_dev)
    return upper_band, lower_band

def calculate_stochastic_oscillator(high, low, close, window):
    lowest_low = low.rolling(window=window).min()
    highest_high = high.rolling(window=window).max()
    k_percent = ((close - lowest_low) / (highest_high - lowest_low)) * 100
    d_percent = k_percent.rolling(window=3).mean() # %D genellikle %K'nin 3 dönemlik hareketli ortalamasıdır
    return k_percent, d_percent

def calculate_atr(high, low, close, window):
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    true_range = pd.DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3}).max(axis=1)
    atr = true_range.ewm(span=window, adjust=False).mean()
    return atr

file_path = "/Users/hasantekbas/Documents/OptiTrade/OptiTradeCode/archive/BTC-Hourly.csv"
df = pd.read_csv(file_path)

df['date'] = pd.to_datetime(df['date'])
df.set_index('date', inplace=True)

# 4 saatlik periyotlara yeniden örnekle
df_4h = df['close'].resample('4H').last().to_frame()
df_4h['open'] = df['open'].resample('4H').first()
df_4h['high'] = df['high'].resample('4H').max()
df_4h['low'] = df['low'].resample('4H').min()
df_4h['volume'] = df['Volume BTC'].resample('4H').sum()

df_4h.dropna(inplace=True)

# Teknik Göstergeleri Hesapla
df_4h['SMA_12'] = df_4h['close'].rolling(window=12).mean()
df_4h['SMA_24'] = df_4h['close'].rolling(window=24).mean()
df_4h['EMA_12'] = df_4h['close'].ewm(span=12, adjust=False).mean()
df_4h['EMA_24'] = df_4h['close'].ewm(span=24, adjust=False).mean()
df_4h['RSI'] = calculate_rsi(df_4h['close'], 14)
macd, signal = calculate_macd(df_4h['close'], 12, 26, 9)
df_4h['MACD'] = macd
df_4h['MACD_Signal'] = signal

# Yeni Göstergeler
upper_band, lower_band = calculate_bollinger_bands(df_4h['close'], 20, 2)
df_4h['Bollinger_Upper'] = upper_band
df_4h['Bollinger_Lower'] = lower_band

k_percent, d_percent = calculate_stochastic_oscillator(df_4h['high'], df_4h['low'], df_4h['close'], 14)
df_4h['Stoch_K'] = k_percent
df_4h['Stoch_D'] = d_percent

df_4h['ATR'] = calculate_atr(df_4h['high'], df_4h['low'], df_4h['close'], 14)

# Gecikmeli Özellikler Ekle
for col in ['close', 'volume', 'RSI', 'MACD']:
    for i in range(1, 4): # 1, 2, 3 periyot gecikme
        df_4h[f'{col}_lag_{i}'] = df_4h[col].shift(i)

# Hedef Değişkeni Oluştur: Bir sonraki 4 saatlik periyotta fiyat yükselecek mi? (1: evet, 0: hayır)
df_4h['target'] = (df_4h['close'].shift(-1) > df_4h['close']).astype(int)

# NaN değerleri düşür (gösterge ve gecikme hesaplamalarından kaynaklananlar)
df_4h.dropna(inplace=True)

# Özellikler (X) ve Hedef (y) değişkenlerini ayır
X = df_4h.drop('target', axis=1)
y = df_4h['target']

# Veriyi eğitim ve test setlerine ayır
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, shuffle=False)

# Random Forest Sınıflandırıcısı oluştur ve eğit
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# Test seti üzerinde tahmin yap
y_pred = model.predict(X_test)

# Doğruluk oranını hesapla
accuracy = accuracy_score(y_test, y_pred)

print(f"Model Doğruluk Oranı: {accuracy:.2f}%")
