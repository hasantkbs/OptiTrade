import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

class Dashboard:
    def __init__(self):
        pass

    def setup_page_config(self):
        """Sayfa konfigürasyonu"""
        st.set_page_config(
            page_title="OptiTrade - AI Stock Analyzer",
            page_icon="📈",
            layout="wide",
            initial_sidebar_state="expanded"
        )

    def create_sidebar(self):
        """Sidebar oluşturma"""
        with st.sidebar:
            st.title("📈 OptiTrade")
            st.markdown("---")

            # Sembol seçimi
            symbol = st.selectbox(
                "Hisse Senedi Seçin",
                ["AAPL", "GOOGL", "MSFT", "TSLA", "AMZN", "META", "NVDA"],
                index=0
            )

            # Zaman periyodu
            period = st.selectbox(
                "Zaman Periyodu",
                ["1mo", "3mo", "6mo", "1y", "2y", "5y", "max"],
                index=3
            )

            # Grafik tipi
            chart_type = st.radio(
                "Grafik Tipi",
                ["Candlestick", "Line", "Area"]
            )

            st.markdown("---")
            st.info("💡 AI destekli borsa analiz aracı")

        return symbol, period, chart_type

    def create_price_chart(self, data, symbol, chart_type="Candlestick"):
        """Fiyat grafiği oluşturma"""
        fig = go.Figure()

        if chart_type == "Candlestick":
            fig.add_trace(go.Candlestick(
                x=data.index,
                open=data['open'],
                high=data['high'],
                low=data['low'],
                close=data['close'],
                name='Fiyat'
            ))
        elif chart_type == "Line":
            fig.add_trace(go.Scatter(
                x=data.index,
                y=data['close'],
                mode='lines',
                name='Kapanış Fiyatı',
                line=dict(color='#1f77b4', width=2)
            ))
        else:  # Area
            fig.add_trace(go.Scatter(
                x=data.index,
                y=data['close'],
                fill='tonexty',
                mode='lines',
                name='Kapanış Fiyatı',
                line=dict(color='#1f77b4'),
                fillcolor='rgba(31, 119, 180, 0.3)'
            ))

        # Hareketli ortalamalar
        if 'MA20' in data.columns:
            fig.add_trace(go.Scatter(
                x=data.index,
                y=data['MA20'],
                name='MA20',
                line=dict(color='orange', width=1)
            ))

        if 'MA50' in data.columns:
            fig.add_trace(go.Scatter(
                x=data.index,
                y=data['MA50'],
                name='MA50',
                line=dict(color='red', width=1)
            ))

        fig.update_layout(
            title=f'{symbol} Fiyat Grafiği',
            xaxis_title='Tarih',
            yaxis_title='Fiyat ($)',
            height=600,
            showlegend=True,
            hovermode='x unified'
        )

        return fig

    def create_technical_indicators_chart(self, data):
        """Teknik göstergeler grafiği"""
        fig = go.Figure()

        # RSI
        if 'RSI' in data.columns:
            fig.add_trace(go.Scatter(
                x=data.index,
                y=data['RSI'],
                name='RSI',
                line=dict(color='purple')
            ))

            # RSI seviyeleri
            fig.add_hline(y=70, line_dash="dash", line_color="red", opacity=0.5)
            fig.add_hline(y=30, line_dash="dash", line_color="green", opacity=0.5)

        fig.update_layout(
            title='RSI (Relative Strength Index)',
            xaxis_title='Tarih',
            yaxis_title='RSI',
            height=300
        )

        return fig

    def create_volume_chart(self, data):
        """Hacim grafiği"""
        fig = go.Figure()

        colors = ['red' if data['close'].iloc[i] < data['open'].iloc[i]
                 else 'green' for i in range(len(data))]

        fig.add_trace(go.Bar(
            x=data.index,
            y=data['volume'],
            name='Hacim',
            marker_color=colors,
            opacity=0.7
        ))

        fig.update_layout(
            title='İşlem Hacmi',
            xaxis_title='Tarih',
            yaxis_title='Hacim',
            height=300
        )

        return fig

    def display_key_metrics(self, data):
        """Ana metrikleri göster"""
        if data.empty or len(data) < 2:
            st.warning("Not enough data to display key metrics.")
            return

        col1, col2, col3, col4 = st.columns(4)

        current_price = data['close'].iloc[-1]
        previous_price = data['close'].iloc[-2]
        price_change = ((current_price - previous_price) / previous_price) * 100 if previous_price else 0

        with col1:
            st.metric(
                label="Güncel Fiyat",
                value=f"${current_price:.2f}",
                delta=f"{price_change:.2f}%"
            )

        with col2:
            st.metric(
                label="24s Saat En Yüksek",
                value=f"${data['high'].iloc[-1]:.2f}"
            )

        with col3:
            st.metric(
                label="24s Saat En Düşük",
                value=f"${data['low'].iloc[-1]:.2f}"
            )

        with col4:
            st.metric(
                label="Ortalama Hacim",
                value=f"{data['volume'].mean()/1e6:.1f}M"
            )