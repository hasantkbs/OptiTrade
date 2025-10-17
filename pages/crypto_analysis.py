import streamlit as st
import pandas as pd
import numpy as np
from data.crypto_data import CryptoDataFetcher
from utils.dashboard import Dashboard
from utils.crypto_indicators import CryptoTechnicalIndicators
from models.crypto_models import CryptoPredictionModels
from utils.analysis_runner import get_available_models, run_analysis
import plotly.graph_objects as go

def main():
    dashboard = Dashboard()
    dashboard.setup_page_config()

    st.title("₿ Kripto Para Analizi")
    st.markdown("---")

    crypto_fetcher = CryptoDataFetcher()

    with st.sidebar:
        st.title("₿ Kripto Analiz")
        st.markdown("---")
        top_cryptos = crypto_fetcher.get_top_cryptos(30)
        symbol = st.selectbox("Kripto Para Seçin", top_cryptos, index=0)
        exchange = st.selectbox("Borsa Seçin", ["binance", "coinbase", "kraken", "bybit"], index=0)
        timeframe = st.selectbox("Zaman Periyodu", ["1h", "4h", "1d", "1w"], index=2)
        limit = st.slider("Veri Sayısı", 100, 2000, 500)
        
        st.markdown("---")
        st.subheader("Detailed Analysis")
        available_models = get_available_models(asset_type='crypto')
        selected_models = st.multiselect("Select models to run:", available_models)
        analyze_button = st.button("Run Detailed Analysis")

        st.markdown("---")
        st.info("💡 Kripto para analiz aracı")

    try:
        with st.spinner(f'{symbol} verileri yükleniyor...'):
            df, error = crypto_fetcher.get_ohlcv_data(symbol, exchange, timeframe, limit)

            if error:
                st.error(f"Veri çekme hatası: {error}")
                return

            crypto_ti = CryptoTechnicalIndicators()
            df_with_indicators = crypto_ti.add_crypto_indicators(df)

            funding_rate = crypto_fetcher.get_funding_rates(symbol, exchange)
            order_book = crypto_fetcher.get_order_book_data(symbol, exchange)
            sentiment = crypto_fetcher.get_market_sentiment(symbol)

        display_crypto_metrics(df, funding_rate, order_book, sentiment)
        st.markdown("---")

        price_chart_placeholder = st.empty()
        col1, col2 = st.columns([3, 1])
        with col1:
            price_chart = create_crypto_price_chart(df_with_indicators, symbol)
            price_chart_placeholder.plotly_chart(price_chart, use_container_width=True)
        with col2:
            st.subheader("⚡ Hızlı Analiz")
            # ... (rest of the quick analysis)

        st.markdown("---")
        col3, col4 = st.columns(2)
        with col3:
            rsi_chart = create_rsi_chart(df_with_indicators)
            st.plotly_chart(rsi_chart, use_container_width=True)
        with col4:
            volume_chart = create_volume_chart(df)
            st.plotly_chart(volume_chart, use_container_width=True)

        # Detailed Analysis Section
        if analyze_button and selected_models:
            st.markdown("---")
            st.subheader("🔬 Detailed Analysis Results")
            
            analysis_results = run_analysis(selected_models, symbol, timeframe, df_with_indicators)

            for model_name, result in analysis_results.items():
                with st.expander(f"**{model_name}**"):
                    if "error" in result:
                        st.error(result["error"])
                    else:
                        if model_name == "FibonacciModel":
                            st.write(result.get('details', 'No details'))
                            levels = result.get('levels', {})
                            if levels:
                                st.json(levels)
                                for level_name, level_val in levels.items():
                                    price_chart.add_hline(y=level_val, line_dash="dash", annotation_text=level_name, line_color="purple")
                                price_chart_placeholder.plotly_chart(price_chart, use_container_width=True)
                        
                        elif "score" in result:
                            st.metric("Score", f"{result.get('score', 0):.2f}")
                            st.write(result.get('details', 'No details'))
                        else:
                            st.json(result)

        st.markdown("---")
        st.subheader("🔮 Fiyat Tahmini (LSTM/GRU)")
        if st.button("Run LSTM/GRU Prediction"):
            make_crypto_prediction(df_with_indicators, symbol)

    except Exception as e:
        st.error(f"Bir hata oluştu: {str(e)}")
        st.info("Lütfen farklı bir kripto para seçin veya daha sonra tekrar deneyin.")

# ... (rest of the functions are the same)

if __name__ == "__main__":
    main()
