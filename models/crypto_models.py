import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout, GRU
from tensorflow.keras.optimizers import Adam
import xgboost as xgb

class CryptoPredictionModels:
    def __init__(self):
        self.scaler = StandardScaler()
        self.minmax_scaler = MinMaxScaler()
        self.lstm_model = None
        self.xgb_model = None
        self.ensemble_model = None

    def prepare_features(self, df):
        """Kripto analizi için özellik hazırlama"""
        features = df.copy()

        # Teknik göstergeler
        feature_columns = [
            'open', 'high', 'low', 'close', 'volume',
            'RSI', 'MACD', 'MACD_Signal', 'ATR_14',
            'Volatility', 'Volume_Ratio', 'Price_Change_24h',
            'MA_7', 'MA_25', 'EMA_12', 'EMA_26'
        ]

        # Mevcut sütunları filtrele
        available_features = [col for col in feature_columns if col in features.columns]
        features = features[available_features].fillna(method='ffill').fillna(0)

        return features

    def prepare_lstm_data(self, df, lookback=60, target_col='close'):
        """LSTM için veri hazırlama"""
        features = self.prepare_features(df)

        if len(features) < lookback:
            return None, None

        # Scale the data
        scaled_data = self.minmax_scaler.fit_transform(features)

        X, y = [], []
        target_idx = features.columns.get_loc(target_col) if target_col in features.columns else 0

        for i in range(lookback, len(scaled_data)):
            X.append(scaled_data[i-lookback:i])
            y.append(scaled_data[i, target_idx])

        return np.array(X), np.array(y)

    def build_lstm_model(self, input_shape):
        """Gelişmiş LSTM model (kripto için optimize edilmiş)"""
        model = Sequential([
            LSTM(128, return_sequences=True, input_shape=input_shape),
            Dropout(0.3),
            LSTM(64, return_sequences=True),
            Dropout(0.3),
            LSTM(32, return_sequences=False),
            Dropout(0.3),
            Dense(25, activation='relu'),
            Dense(1)
        ])

        model.compile(
            optimizer=Adam(learning_rate=0.001),
            loss='huber',  # Kripto paralarda daha iyi çalışan loss fonksiyonu
            metrics=['mae']
        )

        self.lstm_model = model
        return model

    def build_gru_model(self, input_shape):
        """GRU model (LSTM'e alternatif)"""
        model = Sequential([
            GRU(128, return_sequences=True, input_shape=input_shape),
            Dropout(0.3),
            GRU(64, return_sequences=True),
            Dropout(0.3),
            GRU(32, return_sequences=False),
            Dropout(0.3),
            Dense(25, activation='relu'),
            Dense(1)
        ])

        model.compile(
            optimizer=Adam(learning_rate=0.001),
            loss='huber',
            metrics=['mae']
        )

        return model

    def prepare_ml_data(self, df, target_col='close'):
        """ML modelleri için veri hazırlama"""
        features = self.prepare_features(df)

        if target_col in features.columns:
            y = features[target_col]
            X = features.drop(columns=[target_col])
        else:
            y = features.iloc[:, 3]  # Genellikle 'close' sütunu
            X = features.drop(features.columns[3], axis=1)

        return X, y

    def train_xgboost_model(self, X_train, y_train, X_val=None, y_val=None):
        """XGBoost modeli (kripto için optimize edilmiş)"""
        self.xgb_model = xgb.XGBRegressor(
            n_estimators=1000,
            max_depth=8,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            objective='reg:squarederror'
        )

        eval_set = [(X_val, y_val)] if X_val is not None else None
        early_stopping_rounds = 50 if X_val is not None else None

        self.xgb_model.fit(
            X_train, y_train,
            eval_set=eval_set,
            early_stopping_rounds=early_stopping_rounds,
            verbose=False
        )

        return self.xgb_model

    def create_ensemble_model(self, X_train, y_train, X_val=None, y_val=None):
        """Ensemble model (XGBoost + Random Forest)"""
        # XGBoost
        xgb_model = self.train_xgboost_model(X_train, y_train, X_val, y_val)

        # Random Forest
        rf_model = RandomForestRegressor(
            n_estimators=200,
            max_depth=15,
            random_state=42,
            n_jobs=-1
        )
        rf_model.fit(X_train, y_train)

        self.ensemble_model = {
            'xgb': xgb_model,
            'rf': rf_model
        }

        return self.ensemble_model

    def make_ensemble_predictions(self, X):
        """Ensemble tahminleri"""
        if self.ensemble_model is None:
            raise ValueError("Ensemble model eğitilmemiş!")

        xgb_pred = self.ensemble_model['xgb'].predict(X)
        rf_pred = self.ensemble_model['rf'].predict(X)

        # Ağırlıklı ortalama (XGBoost'e daha fazla ağırlık)
        ensemble_pred = 0.6 * xgb_pred + 0.4 * rf_pred

        return ensemble_pred

    def predict_short_term_volatility(self, df, window=24):
        """Kısa vadeli volatilite tahmini"""
        recent_data = df.tail(window)
        volatility = recent_data['Volatility'].mean()
        price_change_std = recent_data['Price_Change_24h'].std()

        return {
            'expected_volatility': volatility,
            'price_change_std': price_change_std,
            'volatility_trend': 'High' if volatility > 5 else 'Low'
        }

    def predict_market_sentiment(self, df):
        """Piyasa duygusu tahmini"""
        recent_rsi = df['RSI'].iloc[-1]
        recent_macd = df['MACD_Histogram'].iloc[-1] if 'MACD_Histogram' in df.columns else 0
        recent_volume = df['Volume_Ratio'].iloc[-1]

        # Sentiment skoru hesapla
        sentiment_score = 0
        if recent_rsi < 30:
            sentiment_score -= 1  # Aşırı satım
        elif recent_rsi > 70:
            sentiment_score += 1  # Aşırı alım

        if recent_macd > 0:
            sentiment_score += 0.5
        else:
            sentiment_score -= 0.5

        if recent_volume > 1.5:
            sentiment_score += 0.5  # Yüksek hacim

        sentiment = 'Bullish' if sentiment_score > 0.5 else 'Bearish' if sentiment_score < -0.5 else 'Neutral'

        return {
            'sentiment': sentiment,
            'sentiment_score': sentiment_score,
            'confidence': abs(sentiment_score) * 20  # % olarak güven
        }