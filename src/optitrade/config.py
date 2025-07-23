import os
from dotenv import load_dotenv

# .env dosyasındaki ortam değişkenlerini yükle
load_dotenv()

# -----------------------------------------------------------------------------
# LOGLAMA YAPILANDIRMASI
# -----------------------------------------------------------------------------

# Hata ayıklama modunu etkinleştirir. Geliştirme ortamında `True` olmalıdır.
DEBUG = os.getenv("DEBUG", "True").lower() == "true"

# Loglama seviyesi. Hata ayıklama modunda `DEBUG`, aksi halde `INFO`.
LOG_LEVEL = "DEBUG" if DEBUG else "INFO"

# Log dosyası adı.
LOG_FILE = "optitrade.log"


# -----------------------------------------------------------------------------
# API ANAHTARLARI VE YAPILANDIRMALARI
# -----------------------------------------------------------------------------

# Reddit API (PRAW)
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "OptiTrade_App/1.0")

# NewsAPI
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

# Alpha Vantage API
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")


# -----------------------------------------------------------------------------
# UYARI SİSTEMİ YAPILANDIRMASI (AlertSystem)
# -----------------------------------------------------------------------------
# Boğa ve ayı sinyalleri için kullanılacak skor eşikleri.
ALERT_BULLISH_THRESHOLD = 0.7
ALERT_BEARISH_THRESHOLD = -0.7


# -----------------------------------------------------------------------------
# FİYAT TREND MODELİ YAPILANDIRMASI (PriceTrendModel)
# -----------------------------------------------------------------------------
# Teknik analiz göstergeleri için pencere boyutları.
PRICE_TREND_RSI_WINDOW = 14
PRICE_TREND_MACD_FAST_WINDOW = 12
PRICE_TREND_MACD_SLOW_WINDOW = 26
PRICE_TREND_MACD_SIGNAL_WINDOW = 9
PRICE_TREND_SMA_SHORT_WINDOW = 20
PRICE_TREND_SMA_LONG_WINDOW = 50
PRICE_TREND_BOLLINGER_WINDOW = 20
PRICE_TREND_BOLLINGER_STD = 2.0
PRICE_TREND_ADX_WINDOW = 14


# -----------------------------------------------------------------------------
# HACİM ARTIŞ MODELİ YAPILANDIRMASI (VolumeSurgeModel)
# -----------------------------------------------------------------------------
# Hacim analizi göstergeleri için pencere boyutları ve etki faktörleri.
VOLUME_SURGE_VWAP_WINDOW = 14
VOLUME_SURGE_OBV_WINDOW = 14
VOLUME_SURGE_VOLATILITY_WINDOW = 14
VOLUME_SURGE_MA_WINDOW = 20
VOLUME_SURGE_DEVIATION_SCALE = 1.0  # Hacim sapmasının skora etkisini ölçeklendirir.
VOLUME_SURGE_OBV_INFLUENCE = 0.2   # OBV trendinin skora katkısı.


# -----------------------------------------------------------------------------
# DESTEK/DİRENÇ MODELİ YAPILANDIRMASI (SupportResistanceModel)
# -----------------------------------------------------------------------------
# Fraktal tespiti için pencere boyutu.
SUPPORT_RESISTANCE_FRACTAL_WINDOW = 2


# -----------------------------------------------------------------------------
# UYUMSUZLUK TESPİT MODELİ YAPILANDIRMASI (DivergenceDetectionModel)
# -----------------------------------------------------------------------------
# Uyumsuzluk tespiti için gösterge ve arama parametreleri.
DIVERGENCE_INDICATOR_WINDOW = 14
DIVERGENCE_MACD_FAST_WINDOW = 12
DIVERGENCE_MACD_SLOW_WINDOW = 26
DIVERGENCE_MACD_SIGNAL_WINDOW = 9
DIVERGENCE_EXTREMA_ORDER = 5          # Yerel ekstremumları bulmak için komşu nokta sayısı.
DIVERGENCE_LOOKBACK_PERIOD = 60       # Uyumsuzluk aramak için geçmişe dönük gün sayısı.
DIVERGENCE_TOLERANCE_DAYS = 5         # Fiyat ve gösterge ekstremumlarını eşleştirme toleransı.


# -----------------------------------------------------------------------------
# PUANLAMA MOTORU YAPILANDIRMASI (ScoringEngine)
# -----------------------------------------------------------------------------
# Her bir modelin nihai skora katkısını belirleyen ağırlıklar.
# Bu ağırlıklar, backtesting ile optimize edilebilir.
SCORING_ENGINE_WEIGHTS = {
    'price_trend_score': 0.2177,
    'volume_surge_score': 0.0021,
    'news_sentiment_score': 0.0596,
    'social_sentiment_score': 0.3155,
    'support_resistance_score': 0.1221,
    'divergence_score': 0.1369,
    'event_impact_score': 0.1462,
}

# Piyasa koşullarına göre skor ayarlama faktörleri.
SCORING_ADJUSTMENT_BULL_POSITIVE = 1.1  # Boğa piyasasında pozitif skorlar için çarpan.
SCORING_ADJUSTMENT_BULL_NEGATIVE = 0.9  # Boğa piyasasında negatif skorlar için çarpan.
SCORING_ADJUSTMENT_BEAR_POSITIVE = 0.9  # Ayı piyasasında pozitif skorlar için çarpan.
SCORING_ADJUSTMENT_BEAR_NEGATIVE = 1.1  # Ayı piyasasında negatif skorlar için çarpan.