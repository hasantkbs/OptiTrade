import streamlit as st
import yfinance as yf
import pandas as pd

from utils.dashboard import Dashboard
from utils.analysis_runner import get_available_models, run_analysis

def main():
    dashboard = Dashboard()
    dashboard.setup_page_config()

    # Sidebar
    symbol, period, chart_type = dashboard.create_sidebar()

    with st.sidebar:
        st.markdown("---")
        st.subheader("Detailed Analysis")
        available_models = get_available_models()
        selected_models = st.multiselect("Select models to run:", available_models)
        analyze_button = st.button("Run Detailed Analysis")

    # Başlık
    st.title("📈 OptiTrade - AI Stock Analyzer")
    st.markdown("---")

    try:
        # Veri çekme
        with st.spinner(f'{symbol} verileri yükleniyor...'):
            stock = yf.Ticker(symbol)
            data = stock.history(period=period)
            # Rename columns to lowercase for compatibility with optitrade models
            data.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}, inplace=True)

            # Teknik göstergeler ekle
            data = add_technical_indicators(data)

        # Ana metrikler
        dashboard.display_key_metrics(data)
        st.markdown("---")

        # Grafikler
        price_chart_placeholder = st.empty()
        
        col1, col2 = st.columns([3, 1])
        with col1:
            price_chart = dashboard.create_price_chart(data, symbol, chart_type)
            price_chart_placeholder.plotly_chart(price_chart, use_container_width=True)

        with col2:
            # Hızlı analiz
            st.subheader("⚡ Hızlı Analiz")
            latest_rsi = data['RSI'].iloc[-1] if 'RSI' in data.columns else 0

            if latest_rsi > 70:
                st.warning(f"RSI: {latest_rsi:.1f} - Aşırı Alım")
            elif latest_rsi < 30:
                st.success(f"RSI: {latest_rsi:.1f} - Aşırı Satım")
            else:
                st.info(f"RSI: {latest_rsi:.1f} - Nötr")

            # Son 5 günlük veri
            st.subheader("📅 Son 5 İş Günü")
            recent_data = data.tail(5)[['close', 'volume']].round(2)
            st.dataframe(recent_data)

        # Alt grafikler
        st.markdown("---")
        col3, col4 = st.columns(2)

        with col3:
            rsi_chart = dashboard.create_technical_indicators_chart(data)
            st.plotly_chart(rsi_chart, use_container_width=True)

        with col4:
            volume_chart = dashboard.create_volume_chart(data)
            st.plotly_chart(volume_chart, use_container_width=True)

        # Detailed Analysis Section
        if analyze_button and selected_models:
            st.markdown("---")
            st.subheader("🔬 Detailed Analysis Results")
            
            analysis_results = run_analysis(selected_models, symbol, "1d", data)

            for model_name, result in analysis_results.items():
                with st.expander(f"**{model_name}**"):
                    if "error" in result:
                        st.error(result["error"])
                    else:
                        # Custom display for different models
                        if model_name == "FibonacciModel":
                            st.write(result.get('details', 'No details'))
                            levels = result.get('levels', {})
                            if levels:
                                st.json(levels)
                                # Add levels to the main price chart
                                for level_name, level_val in levels.items():
                                    price_chart.add_hline(y=level_val, line_dash="dash", annotation_text=level_name, line_color="purple")
                                price_chart_placeholder.plotly_chart(price_chart, use_container_width=True)
                        
                        elif "score" in result:
                            st.metric("Score", f"{result.get('score', 0):.2f}")
                            st.write(result.get('details', 'No details'))
                        else:
                            # Generic display for other models
                            st.json(result)

    except Exception as e:
        st.error(f"Veri yüklenirken hata oluştu: {str(e)}")
        st.info("Lütfen farklı bir hisse senedi seçin veya daha sonra tekrar deneyin.")

def add_technical_indicators(df):
    df['MA20'] = df['close'].rolling(window=20).mean()
    df['MA50'] = df['close'].rolling(window=50).mean()
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    return df

if __name__ == "__main__":
    main()
