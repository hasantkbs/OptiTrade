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
# VERİTABANI YAPILANDIRMASI
# -----------------------------------------------------------------------------
DATABASE_FILE = "data/optitrade.db"


# -----------------------------------------------------------------------------
# API ANAHTARLARI VE YAPILANDIRMALARI
# -----------------------------------------------------------------------------

# Reddit API (PRAW)
REDDIT_CLIENT_ID = os.getenv("kSlf5qJ1Po-OxCL3qs-Vhw")
REDDIT_CLIENT_SECRET = os.getenv("vtSpZN21CugAvTGkfAUzTR2D3znvBw")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "OptiTrade_App/1.0")

# Twitter API
TWITTER_API_KEY = os.getenv("XYSpRPvbYoGfnyyLEhfRAV2Ui")
TWITTER_API_SECRET_KEY = os.getenv("YvQ2jVwiaUOrAxDNS40uoEyOxuM8NYzErL5jiMU31L8FovQnOx")
TWITTER_ACCESS_TOKEN = os.getenv("1856235494071545856-8RJWP0jjQEzkjoLdQ8YzBReHFaQJGk")
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("LVlUwrNdw6Ru36MCTLsfOBhGHE9e6r4i4vjNj5v2Imc9F")

# NewsAPI
NEWS_API_KEY = os.getenv("4c0d941b9b8a4ce68c091e0fceacb708")

# The Guardian API
GUARDIAN_API_KEY = os.getenv("cbf3e823-0603-4098-adee-b579ef3c8416")

# Alpha Vantage API
ALPHA_VANTAGE_API_KEY = os.getenv("Y2HFXHHI55EAG9XX")


# -----------------------------------------------------------------------------
# UYARI SİSTEMİ YAPILANDIRMASI (AlertSystem)
# -----------------------------------------------------------------------------
# Boğa ve ayı sinyalleri için kullanılacak skor eşikleri.
ALERT_BULLISH_THRESHOLD = 0.7
ALERT_BEARISH_THRESHOLD = -0.7

# E-posta uyarıları için SMTP yapılandırması
# Bu değerleri .env dosyanızda tanımlamanız gerekmektedir.
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
ALERT_RECIPIENT_EMAIL = os.getenv("ALERT_RECIPIENT_EMAIL")


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

# Fiyat Trend Modeli içindeki göstergelerin skorlama ağırlıkları.
PRICE_TREND_INDICATOR_WEIGHTS = {
    'rsi_overbought': 0.5,
    'rsi_oversold': 0.5,
    'macd_momentum': 5.0, # Bu değer, MACD farkının kapanış fiyatına oranına çarpıldığı için daha büyük olabilir.
    'sma_golden_cross': 0.15,
    'sma_death_cross': 0.15,
    'adx_uptrend': 0.15,
    'adx_downtrend': 0.15,
}


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
# FORMASYON TESPİT MODELİ YAPILANDIRMASI (FormationDetectionModel)
# -----------------------------------------------------------------------------
# Formasyon tespiti için ekstremum arama penceresi ve tolerans.
FORMATION_EXTREMA_ORDER = 10
FORMATION_TOLERANCE = 0.03
FORMATION_REQUIRED_DATA_POINTS = 150


# -----------------------------------------------------------------------------
# PİYASA REJİMİ SINIFLANDIRICI YAPILANDIRMASI (MarketConditionClassifier)
# -----------------------------------------------------------------------------
# ADX göstergesi için pencere boyutu ve trend eşiği.
MARKET_CLASSIFIER_ADX_WINDOW = 14
MARKET_CLASSIFIER_ADX_THRESHOLD = 25


# -----------------------------------------------------------------------------
# KORELASYON MODELİ YAPILANDIRMASI (CorrelationModel)
# -----------------------------------------------------------------------------
# Korelasyon hesaplaması için pencere boyutu ve karşılaştırılacak varlıklar.
CORRELATION_WINDOW = 30
CORRELATION_ASSETS = ['SPY', 'GLD']


# -----------------------------------------------------------------------------
# ON-CHAIN MODELİ YAPILANDIRMASI (OnChainModel)
# -----------------------------------------------------------------------------
# Hareketli ortalama pencereleri.
ONCHAIN_SHORT_WINDOW = 14
ONCHAIN_LONG_WINDOW = 50


# -----------------------------------------------------------------------------
# RİSK YÖNETİMİ YAPILANDIRMASI (RiskManager)
# -----------------------------------------------------------------------------

# Dinamik stop-loss hesaplaması için ATR (Average True Range) çarpanı.
RISK_ATR_MULTIPLIER = 2.0

# -----------------------------------------------------------------------------
# SCORING ENGINE YAPILANDIRMASI
# -----------------------------------------------------------------------------

# Alım/satım sinyali üretmek için gereken minimum skor eşiği.
SIGNAL_THRESHOLD = 0.5

# -----------------------------------------------------------------------------
# MODEL AĞIRLIKLARI (MODEL WEIGHTS)
# -----------------------------------------------------------------------------

# Farklı piyasa rejimleri için model ağırlıkları.
# Toplamları 1 olmak zorunda değildir, ScoringEngine tarafından normalize edilirler.

# Varsayılan (bilinmeyen veya karmaşık rejimler için)
MODEL_WEIGHTS_DEFAULT = {
    "MarketConditionClassifier": 0,
    "PriceTrendModel": 0.25,
    "VolumeSurgeModel": 0.15,
    "NewsSentimentModel": 0.1,
    "SocialSentimentModel": 0.05,
    "OnChainModel": 0.1,
    "CorrelationModel": 0.05,
    "SupportResistanceModel": 0.1,
    "DivergenceDetectionModel": 0.1,
    "FormationDetectionModel": 0.1,
    "FibonacciModel": 0.1,
}

# Güçlü Trend (yükselen veya düşen)
MODEL_WEIGHTS_STRONG_TREND = {
    "MarketConditionClassifier": 0,
    "PriceTrendModel": 0.4,
    "VolumeSurgeModel": 0.2,
    "NewsSentimentModel": 0.05,
    "SocialSentimentModel": 0.0,
    "OnChainModel": 0.1,
    "CorrelationModel": 0.0,
    "SupportResistanceModel": 0.1,
    "DivergenceDetectionModel": 0.15,
    "FormationDetectionModel": 0.0,
}

# Yatay Piyasa (menkul kıymet belirli bir aralıkta işlem gördüğünde)
MODEL_WEIGHTS_RANGING = {
    "MarketConditionClassifier": 0,
    "PriceTrendModel": 0.1,
    "VolumeSurgeModel": 0.1,
    "NewsSentimentModel": 0.1,
    "SocialSentimentModel": 0.1,
    "OnChainModel": 0.05,
    "CorrelationModel": 0.1,
    "SupportResistanceModel": 0.2,
    "DivergenceDetectionModel": 0.15,
    "FormationDetectionModel": 0.1,
}

