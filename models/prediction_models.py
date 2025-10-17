import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.optimizers import Adam
import xgboost as xgb

class PredictionModels:
    def __init__(self):
        self.scaler = MinMaxScaler()
        self.lstm_model = None
        self.xgb_model = None
        self.rf_model = None

    def prepare_lstm_data(self, data, lookback=60, target_col='Close'):
        """LSTM için veri hazırlama"""
        # Sadece sayısal sütunları kullan
        numeric_data = data.select_dtypes(include=[np.number]).fillna(method='ffill').fillna(0)

        # Scale the data
        scaled_data = self.scaler.fit_transform(numeric_data)

        X, y = [], []
        target_idx = numeric_data.columns.get_loc(target_col)

        for i in range(lookback, len(scaled_data)):
            X.append(scaled_data[i-lookback:i])
            y.append(scaled_data[i, target_idx])

        return np.array(X), np.array(y)

    def build_lstm_model(self, input_shape):
        """Gelişmiş LSTM model"""
        model = Sequential([
            LSTM(100, return_sequences=True, input_shape=input_shape),
            Dropout(0.2),
            LSTM(100, return_sequences=True),
            Dropout(0.2),
            LSTM(50, return_sequences=False),
            Dropout(0.2),
            Dense(25),
            Dense(1)
        ])

        model.compile(
            optimizer=Adam(learning_rate=0.001),
            loss='mean_squared_error',
            metrics=['mae']
        )

        self.lstm_model = model
        return model

    def train_lstm_model(self, X_train, y_train, X_val, y_val, epochs=50, batch_size=32):
        """LSTM modeli eğit"""
        if self.lstm_model is None:
            self.lstm_model = self.build_lstm_model((X_train.shape[1], X_train.shape[2]))

        # Early stopping
        early_stopping = tf.keras.callbacks.EarlyStopping(
            monitor='val_loss',
            patience=10,
            restore_best_weights=True
        )

        # Model checkpoint
        checkpoint = tf.keras.callbacks.ModelCheckpoint(
            'best_lstm_model.h5',
            monitor='val_loss',
            save_best_only=True,
            verbose=1
        )

        history = self.lstm_model.fit(
            X_train, y_train,
            batch_size=batch_size,
            epochs=epochs,
            validation_data=(X_val, y_val),
            callbacks=[early_stopping, checkpoint],
            verbose=1
        )

        return history

    def prepare_ml_data(self, data, target_col='Close'):
        """ML modelleri için veri hazırlama"""
        # Sadece sayısal sütunlar
        numeric_data = data.select_dtypes(include=[np.number]).fillna(method='ffill').fillna(0)

        # Hedef değişkeni ayır
        if target_col in numeric_data.columns:
            y = numeric_data[target_col]
            X = numeric_data.drop(columns=[target_col])
        else:
            y = numeric_data.iloc[:, 0]  # İlk sütunu hedef al
            X = numeric_data.iloc[:, 1:]

        return X, y

    def train_xgboost_model(self, X_train, y_train, X_val, y_val):
        """XGBoost modeli eğit"""
        self.xgb_model = xgb.XGBRegressor(
            n_estimators=1000,
            max_depth=10,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42
        )

        eval_set = [(X_val, y_val)]
        self.xgb_model.fit(
            X_train, y_train,
            eval_set=eval_set,
            early_stopping_rounds=50,
            verbose=False
        )

        return self.xgb_model

    def train_random_forest_model(self, X_train, y_train):
        """Random Forest modeli eğit"""
        self.rf_model = RandomForestRegressor(
            n_estimators=200,
            max_depth=20,
            random_state=42,
            n_jobs=-1
        )

        self.rf_model.fit(X_train, y_train)
        return self.rf_model

    def make_lstm_predictions(self, X):
        """LSTM tahminleri"""
        if self.lstm_model is None:
            raise ValueError("LSTM model eğitilmemiş!")

        predictions = self.lstm_model.predict(X)
        return predictions

    def make_xgb_predictions(self, X):
        """XGBoost tahminleri"""
        if self.xgb_model is None:
            raise ValueError("XGBoost model eğitilmemiş!")

        predictions = self.xgb_model.predict(X)
        return predictions

    def make_rf_predictions(self, X):
        """Random Forest tahminleri"""
        if self.rf_model is None:
            raise ValueError("Random Forest model eğitilmemiş!")

        predictions = self.rf_model.predict(X)
        return predictions

    def evaluate_model(self, y_true, y_pred, model_name="Model"):
        """Model performansını değerlendir"""
        mse = mean_squared_error(y_true, y_pred)
        mae = mean_absolute_error(y_true, y_pred)
        rmse = np.sqrt(mse)

        print(f"\n{model_name} Performansı:")
        print(f"MSE: {mse:.4f}")
        print(f"MAE: {mae:.4f}")
        print(f"RMSE: {rmse:.4f}")

        return {
            'MSE': mse,
            'MAE': mae,
            'RMSE': rmse
        }

    def create_ensemble_predictions(self, lstm_pred, xgb_pred, rf_pred, weights=None):
        """Ensemble tahminleri"""
        if weights is None:
            weights = [0.4, 0.3, 0.3]  # LSTM, XGBoost, Random Forest

        ensemble_pred = (weights[0] * lstm_pred +
                        weights[1] * xgb_pred +
                        weights[2] * rf_pred)

        return ensemble_pred