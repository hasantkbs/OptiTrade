import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
import ta
import logging
import sys
import os
import argparse

# Proje kök dizinini Python yoluna ekle
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.optitrade.utils.data_fetcher import DataFetcher
from src.optitrade.models.model_utils import create_features
from src.optitrade.models.financial_ratio_model import FinancialRatioModel

# Loglama yapılandırması
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def create_target(df: pd.DataFrame, look_forward_days: int = 7) -> pd.Series:
    """
    Hedef değişkeni oluşturur: Fiyat `look_forward_days` gün sonra artacak mı?
    """
    future_price = df['Close'].shift(-look_forward_days)
    target = (future_price > df['Close']).astype(int)
    return target

def main():
    """
    Ana eğitim betiği.
    """
    parser = argparse.ArgumentParser(description="Makine öğrenmesi modeli eğitimi.")
    parser.add_argument('--interval', type=str, default='1d', choices=['15m', '4h', '1d'],
                        help='Eğitim yapılacak zaman aralığı (örn: 15m, 4h, 1d). Varsayılan: 1d')
    parser.add_argument('--symbol', type=str, default='AAPL', help='Eğitim yapılacak sembol (örn: AAPL). Varsayılan: AAPL')
    args = parser.parse_args()

    current_interval = args.interval
    current_symbol = args.symbol
    asset_type = 'crypto' if current_symbol in ["BTC-USD", "ETH-USD"] else 'stock'
    logging.info(f"Makine öğrenmesi modeli eğitim süreci başlatıldı ({current_interval} aralığı için, sembol: {current_symbol}, varlık tipi: {asset_type}).")

    # 1. Veri Çekme
    logging.info(f"Geçmiş veriler çekiliyor ({current_interval} aralığı için)...")
    fetcher = DataFetcher()
    
    # Interval'e göre veri çekme periyodunu ayarla
    period_map = {"15m": "60d", "4h": "730d", "1d": "365d"}
    fetch_period = period_map.get(current_interval, "5y")

    data = fetcher.get_market_data(symbol=current_symbol, period=fetch_period, interval=current_interval)
    if data.empty:
        logging.error("Veri çekilemedi. Eğitim durduruldu.")
        return

    # 2. Finansal Oranları Çekme (sadece hisse senetleri için)
    financial_ratios = None
    if current_symbol not in ["BTC-USD", "ETH-USD"]: # Basit bir kontrol, daha iyisi yapılabilir
        financial_ratio_model = FinancialRatioModel()
        financial_ratios = financial_ratio_model.get_ratios(current_symbol)
        if financial_ratios:
            logging.info(f"Finansal oranlar çekildi: {financial_ratios}")
        else:
            logging.warning(f"'{current_symbol}' için finansal oranlar çekilemedi veya boş.")

    # 3. Özellik (Feature) Oluşturma
    logging.info("Teknik göstergeler ve özellikler oluşturuluyor...")
    data = create_features(data, interval=current_interval, financial_ratios=financial_ratios)

    # 4. Hedef (Target) Oluşturma
    logging.info("Hedef değişken oluşturuluyor (7 gün sonrası için fiyat artışı)...")
    look_forward_days = 7 # Use a fixed 7-day look-forward period for target creation
    data['target'] = create_target(data, look_forward_days=look_forward_days)

    # 5. Veri Temizleme ve Hazırlama
    data = data.dropna()
    
    if data.empty:
        logging.error("Özellik ve hedef oluşturulduktan sonra veri kalmadı. Eğitim durduruldu.")
        return

    features = [
        'feature_price_change_1d', 'feature_price_change_3d', 'feature_price_change_7d',
        'feature_price_change_1d_lag1', 'feature_price_change_1d_lag2', 'feature_price_change_1d_lag3',
        'feature_volatility_7d', 'feature_volatility_30d', 'feature_rsi_14d',
        'feature_rsi_14d_lag1', 'feature_rsi_14d_lag2', 'feature_rsi_14d_lag3',
        'feature_macd', 'feature_macd_signal', 'feature_macd_diff',
        'feature_sma_50', 'feature_sma_200', 'feature_price_vs_sma50'
    ]
    # Ensure all required features are present in the dataframe
    features = [f for f in features if f in data.columns]
    X = data[features]
    y = data['target']
    logging.info(f"{len(X.columns)} adet özellik ile eğitim yapılacak: {X.columns.tolist()}")

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)
    logging.info(f"Eğitim seti boyutu: {len(X_train)}, Test seti boyutu: {len(X_test)}")

    # 6. Model Eğitimi
    logging.info("XGBoost modeli eğitiliyor...")
    model = xgb.XGBClassifier(
        objective='binary:logistic',
        eval_metric='logloss',
        use_label_encoder=False,
        n_estimators=200,
        max_depth=4,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8
    )
    model.fit(X_train, y_train)

    # 7. Model Değerlendirme
    logging.info("Model test verisi üzerinde değerlendiriliyor...")
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred, target_names=['Düşüş/Sabit', 'Yükseliş'])
    
    print("\n--- MODEL PERFORMANS RAPORU ---")
    print(f"Doğruluk (Accuracy): {accuracy:.4f}")
    print("\nSınıflandırma Raporu:")
    print(report)
    print("---------------------------------")

    # 8. Model Kaydetme
    model_path = f"src/optitrade/models/trained_models/xgb_price_predictor_{current_interval}.json"
    logging.info(f"Eğitilmiş model '{model_path}' dosyasına kaydediliyor...")
    model.save_model(model_path)
    logging.info("Model başarıyla kaydedildi.")

if __name__ == "__main__":
    main()