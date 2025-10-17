import streamlit as st
import yfinance as yf
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from utils.dashboard import Dashboard
from utils.technical_indicators import TechnicalIndicators
from models.prediction_models import PredictionModels
import plotly.graph_objects as go

def main():
    dashboard = Dashboard()
    dashboard.setup_page_config()

    st.title("🔮 Fiyat Tahmini")
    st.markdown("---")

    # Sidebar
    symbol, period, _ = dashboard.create_sidebar()

    # Tahmin ayarları
    with st.sidebar:
        st.markdown("---")
        st.subheader("Tahmin Ayarları")
        lookback_days = st.slider("Geçmiş Gün Sayısı", 30, 120, 60)
        prediction_days = st.slider("Tahmin Gün Sayısı", 1, 30, 7)
        model_type = st.selectbox(
            "Model Türü",
            ["LSTM", "XGBoost", "Random Forest", "Ensemble"]
        )

    try:
        with st.spinner(f'{symbol} verileri yükleniyor...'):
            # Veri çekme
            stock = yf.Ticker(symbol)
            data = stock.history(period=period)

            # Teknik göstergeler ekle
            ti = TechnicalIndicators()
            data_with_indicators = ti.add_all_indicators(data)

            # Tahmin modeli
            model = PredictionModels()

            if model_type == "LSTM":
                # LSTM için veri hazırlama
                X, y = model.prepare_lstm_data(data_with_indicators, lookback=lookback_days)

                if len(X) > 0 and len(y) > 0:
                    # Eğitim ve test verisi ayırma
                    split_idx = int(len(X) * 0.8)
                    if split_idx > 0 and len(X) > split_idx:
                        X_train, X_test = X[:split_idx], X[split_idx:]
                        y_train, y_test = y[:split_idx], y[split_idx:]

                        # Model eğitimi
                        with st.spinner("LSTM model eğitiliyor..."):
                            model.build_lstm_model((X_train.shape[1], X_train.shape[2]))
                            history = model.train_lstm_model(X_train, y_train, X_test, y_test, epochs=20)

                        # Tahmin yap
                        predictions = model.make_lstm_predictions(X_test)

                        # Sonuçları göster
                        st.subheader("LSTM Tahmin Sonuçları")
                        col1, col2, col3 = st.columns(3)
                        col1.metric("Son Fiyat", f"${data['Close'].iloc[-1]:.2f}")
                        col2.metric("Tahmin Edilen Fiyat", f"${predictions[-1][0]:.2f}")
                        col3.metric("Değişim", f"{((predictions[-1][0] - data['Close'].iloc[-1]) / data['Close'].iloc[-1] * 100):.2f}%")

                        # Grafik
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            x=list(range(len(y_test))),
                            y=y_test,
                            mode='lines',
                            name='Gerçek Fiyat',
                            line=dict(color='blue')
                        ))
                        fig.add_trace(go.Scatter(
                            x=list(range(len(predictions))),
                            y=predictions.flatten(),
                            mode='lines',
                            name='Tahmin',
                            line=dict(color='red')
                        ))
                        fig.update_layout(title="LSTM Tahmin Sonuçları", height=400)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("Yeterli veri yok. Daha uzun bir zaman periyodu seçin.")
                else:
                    st.warning("Veri hazırlanamadı. Farklı bir sembol seçin.")

            else:
                # XGBoost veya diğer modeller için
                X, y = model.prepare_ml_data(data_with_indicators)

                if len(X) > 10 and len(y) > 10:  # Minimum veri kontrolü
                    # Eğitim ve test verisi
                    X_train, X_test, y_train, y_test = train_test_split(
                        X, y, test_size=0.2, random_state=42
                    )

                    # Model seçimi ve eğitimi
                    with st.spinner(f"{model_type} model eğitiliyor..."):
                        if model_type == "XGBoost":
                            trained_model = model.train_xgboost_model(X_train, y_train, X_test, y_test)
                        elif model_type == "Random Forest":
                            trained_model = model.train_random_forest_model(X_train, y_train)
                        else:  # Ensemble
                            model.train_xgboost_model(X_train, y_train, X_test, y_test)
                            model.train_random_forest_model(X_train, y_train)

                    # Tahmin yap
                    if model_type == "XGBoost":
                        predictions = model.make_xgb_predictions(X_test)
                    elif model_type == "Random Forest":
                        predictions = model.make_rf_predictions(X_test)
                    else:  # Ensemble
                        xgb_pred = model.make_xgb_predictions(X_test)
                        rf_pred = model.make_rf_predictions(X_test)
                        predictions = (0.6 * xgb_pred + 0.4 * rf_pred)

                    # Performans değerlendirme
                    metrics = model.evaluate_model(y_test, predictions, model_type)

                    # Sonuçları göster
                    st.subheader(f"{model_type} Tahmin Sonuçları")
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Son Fiyat", f"${data['Close'].iloc[-1]:.2f}")
                    col2.metric("Tahmin Edilen Fiyat", f"${predictions[-1]:.2f}")
                    col3.metric("Değişim", f"{((predictions[-1] - data['Close'].iloc[-1]) / data['Close'].iloc[-1] * 100):.2f}%")

                    # Metrikler
                    st.subheader("Model Performansı")
                    col1, col2, col3 = st.columns(3)
                    col1.metric("MSE", f"{metrics['MSE']:.4f}")
                    col2.metric("MAE", f"{metrics['MAE']:.4f}")
                    col3.metric("RMSE", f"{metrics['RMSE']:.4f}")
                else:
                    st.warning("Yeterli veri yok. Daha uzun bir zaman periyodu seçin.")

    except Exception as e:
        st.error(f"Hata oluştu: {str(e)}")
        st.info("Lütfen farklı bir hisse senedi seçin veya ayarları kontrol edin.")

if __name__ == "__main__":
    main()