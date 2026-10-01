import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix
import joblib
import os
from datetime import datetime

# Feature extraction logic matching v2 indicators
def extract_v2_features(df):
    # 1. EMA Cross (20/50)
    ema20 = df['Close'].ewm(span=20, adjust=False).mean()
    ema50 = df['Close'].ewm(span=50, adjust=False).mean()
    df['ema_dist'] = (ema20 - ema50) / df['Close']
    
    # 2. VWAP approximation (since it's daily data, we use a rolling vwap-like indicator)
    # Using 24-period for daily might not make sense, let's use 14-period rolling vwap
    p = (df['High'] + df['Low'] + df['Close']) / 3
    v = df['Volume']
    df['vwap_rolling'] = (p * v).rolling(14).sum() / v.rolling(14).sum()
    df['vwap_dist'] = (df['Close'] - df['vwap_rolling']) / df['vwap_rolling']
    
    # 3. RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # 4. Momentum / Velocity
    df['velocity'] = df['Close'].pct_change(5)
    
    # 5. Volatility (ATR-like)
    df['range'] = (df['High'] - df['Low']) / df['Close']
    
    # Drop NaNs
    return df.dropna()

def train_v2_model(file_path, model_name="v2_xgb_model.joblib"):
    print(f"Loading data from {file_path}...")
    df = pd.read_csv(file_path)
    
    # Rename columns to match our expected format
    df = df.rename(columns={
        'Open time': 'Timestamp',
        'Open': 'Open',
        'High': 'High',
        'Low': 'Low',
        'Close': 'Close',
        'Volume': 'Volume'
    })
    
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    df = df.sort_values('Timestamp')
    
    print("Extracting features...")
    df_feats = extract_v2_features(df)
    
    # Labeling: 1 if 5-day return > 2%, else 0
    df_feats['target'] = (df_feats['Close'].shift(-5) / df_feats['Close'] - 1 > 0.02).astype(int)
    df_feats = df_feats.dropna() # Last 5 rows will be NaN target
    
    features = ['ema_dist', 'vwap_dist', 'rsi', 'velocity', 'range']
    X = df_feats[features]
    y = df_feats['target']
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    model = xgb.XGBClassifier(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.03,
        subsample=0.8,
        colsample_bytree=0.8,
        use_label_encoder=False,
        eval_metric='logloss'
    )
    
    print("Training model...")
    model.fit(X_train, y_train)
    
    y_pred = model.predict(X_test)
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred))
    
    # Save model and metadata
    os.makedirs("backend/models", exist_ok=True)
    save_path = f"backend/models/{model_name}"
    joblib.dump({
        "model": model,
        "features": features,
        "trained_at": datetime.now().isoformat(),
        "accuracy": model.score(X_test, y_test)
    }, save_path)
    
    print(f"\nModel saved to {save_path}")

if __name__ == "__main__":
    dataset_path = "/home/mayasoft/.cache/kagglehub/datasets/novandraanugrah/bitcoin-historical-datasets-2018-2024/versions/427/btc_1d_data_2018_to_2025.csv"
    train_v2_model(dataset_path)
