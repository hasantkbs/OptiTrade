import streamlit as st
from pages.home import main as home_page
from pages.predictions import main as predictions_page
from pages.crypto_analysis import main as crypto_page

# Sayfa yönlendirme
pages = {
    "🏠 Ana Sayfa": home_page,
    "🔮 Fiyat Tahmini": predictions_page,
    "₿ Kripto Analiz": crypto_page,
}

# Sidebar menü
st.sidebar.title("🧭 Navigation")
selection = st.sidebar.radio("Sayfa Seçin", list(pages.keys()))

# Sayfayı yükle
page = pages[selection]
page()
