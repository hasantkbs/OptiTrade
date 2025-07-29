import sys
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
import matplotlib.pyplot as plt

# Proje ana dizinini Python path'ine ekleyerek modüllerin bulunmasını sağlayın
project_path = '.'
if project_path not in sys.path:
    sys.path.append(project_path)

# Oluşturduğumuz özellik üreticiyi import edelim
from src.optitrade.models.feature_generator import add_all_ta_features

# --- Adım 1: Veriyi Yükleme (200,000 satır) ---
file_path = 'archive/BTC-2021min.csv'
try:
    df = pd.read_csv(file_path, nrows=200000, skiprows=1, header=None)
    # Sütun isimlerini manuel olarak atayalım
    df.columns = ['unix', 'date', 'symbol', 'open', 'high', 'low', 'close', 'Volume BTC', 'Volume USD']
    print(f"'{file_path}' dosyasından ilk {len(df)} satır başarıyla okundu.")
except FileNotFoundError:
    print(f"HATA: '{file_path}' dosyası bulunamadı.")
    df = None

if df is not None:
    # --- Adım 2: Özellik Mühendisliği ve Veri Hazırlama ---
    print("Teknik analiz özellikleri üretiliyor...")
    df_features = add_all_ta_features(df)

    # Hedef değişkeni oluşturma (1 Saatlik Tahmin - İkili Sınıflandırma)
    # 60 dakika sonraki fiyat değişimine göre hedef belirleme
    price_change = df_features['close'].shift(-60) - df_features['close']
    # Yüzde değişim eşiği (örneğin %0.2)
    threshold = 0.002 # %0.2

    # 1: Yükselecek, 0: Düşecek/Sabit Kalacak
    df_features['Target'] = (price_change > df_features['close'] * threshold).astype(int)

    # Özellikler (X) ve Hedef (y) belirleme
    feature_columns = [
        'open', 'high', 'low', 'close', 'Volume BTC',
        'feature_rsi', 'feature_macd_diff', 'feature_bollinger_hband_indicator',
        'feature_bollinger_lband_indicator', 'feature_sma_crossover', 'feature_trend_strength',
        'feature_atr', 'feature_high_low_diff', 'feature_close_open_diff',
        'feature_nearest_support_dist', 'feature_nearest_resistance_dist',
        'feature_is_at_support', 'feature_is_at_resistance',
        'close_lag_1', 'close_lag_2', 'close_lag_3',
        'feature_rsi_lag_1', 'feature_rsi_lag_2', 'feature_rsi_lag_3',
        'feature_macd_diff_lag_1', 'feature_macd_diff_lag_2', 'feature_macd_diff_lag_3',
        'feature_trend_strength_lag_1', 'feature_trend_strength_lag_2', 'feature_trend_strength_lag_3',
        'feature_atr_lag_1', 'feature_atr_lag_2', 'feature_atr_lag_3',
        'feature_high_low_diff_lag_1', 'feature_high_low_diff_lag_2', 'feature_high_low_diff_lag_3',
        'feature_close_open_diff_lag_1', 'feature_close_open_diff_lag_2', 'feature_close_open_diff_lag_3'
    ]
    
    df_final = df_features.dropna()

    X = df_final[feature_columns]
    y = df_final['Target']

    # --- Adım 3: Eğitim ve Test Setlerini Ayırma ---
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)

    print(f"Eğitim seti boyutu: {X_train.shape}")
    print(f"Test seti boyutu: {X_test.shape}")

    # --- Adım 4: Modeli Eğitme ---
    print("\nRandomForestClassifier modeli eğitiliyor...")
    model = RandomForestClassifier(n_estimators=100, min_samples_leaf=10, random_state=42, class_weight='balanced_subsample')
    model.fit(X_train, y_train)
    print("Model eğitimi tamamlandı.")

    # --- Adım 5: Tahmin ve Değerlendirme ---
    print("Test seti üzerinde tahminler yapılıyor...")
    predictions = model.predict(X_test)

    accuracy = accuracy_score(y_test, predictions)
    print(f"\nModelin Yeni Test Doğruluğu (Accuracy): {accuracy:.4f}")

    print("\nDetaylı Sınıflandırma Raporu:")
    print(classification_report(y_test, predictions))

    print("\nModelin Kararlarında Etkili Olan Özellikler (Feature Importances):")
    feature_importances = pd.Series(model.feature_importances_, index=feature_columns).sort_values(ascending=False)
    print(feature_importances)

    # --- Adım 6: Destek/Direnç ve Fibonacci Grafiği Çizimi ---
    print("\nDestek, Direnç ve Fibonacci Seviyeleri Grafiği Çiziliyor...")
    plt.figure(figsize=(18, 8))
    plt.plot(df['close'], label='Kapanış Fiyatı', color='blue', alpha=0.7)

    # Destek seviyelerini çiz
    if hasattr(df_features, 'significant_supports'):
        for s_level in df_features.significant_supports:
            plt.axhline(y=s_level, color='green', linestyle='--', linewidth=1, label=f'Destek: {s_level:.2f}')

    # Direnç seviyelerini çiz
    if hasattr(df_features, 'significant_resistances'):
        for r_level in df_features.significant_resistances:
            plt.axhline(y=r_level, color='red', linestyle='--', linewidth=1, label=f'Direnç: {r_level:.2f}')

    # Fibonacci Geri Çekilme Seviyelerini Çiz
    # Sadece grafikteki görünen aralık için Fibonacci seviyelerini hesaplayalım
    max_price = df['close'].max()
    min_price = df['close'].min()
    price_range = max_price - min_price

    fib_levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]
    fib_prices = [max_price - (level * price_range) for level in fib_levels]

    for i, level in enumerate(fib_levels):
        plt.axhline(y=fib_prices[i], color='purple', linestyle=':', linewidth=1, label=f'Fib {level*100:.1f}%')

    plt.title('Fiyat, Destek, Direnç ve Fibonacci Seviyeleri')
    plt.xlabel('Zaman')
    plt.ylabel('Fiyat')
    plt.legend()
    plt.grid(True)
    plt.show()
