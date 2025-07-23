# src/optitrade/api/server.py

import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd

# OptiTrade modüllerini içe aktar
from .. import config
from ..models.registry import initialize_models
from ..models.main import calculate_all_model_scores
from ..scoring.scoring_engine import ScoringEngine
from ..alerting.alert_system import AlertSystem
from ..utils.data_fetcher import MarketDataFetcher, NewsFetcher

# Loglama yapılandırması
logging.basicConfig(
    level=config.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# FastAPI uygulamasını başlat
app = FastAPI(
    title="OptiTrade API",
    description="Finansal analiz ve ticaret sinyali üretimi için API.",
    version="1.0.0"
)

# CORS (Cross-Origin Resource Sharing) Middleware'ini ekle
# Bu, frontend uygulamasının (örn: http://localhost:3000) bu API'ye istek yapmasına izin verir.
origins = [
    "http://localhost:3000", # React geliştirme sunucusu
    "http://localhost",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Tüm metodlara (GET, POST, vb.) izin ver
    allow_headers=["*"], # Tüm başlıklara izin ver
)

# Modelleri ve sistemleri önceden yükle (uygulama başlangıcında bir kez)
models = initialize_models()
scoring_engine = ScoringEngine()
alert_system = AlertSystem()
market_fetcher = MarketDataFetcher()
news_fetcher = NewsFetcher()

# İstek gövdesi için Pydantic modeli
class AnalysisRequest(BaseModel):
    symbol: str
    period: str = 'max'
    interval: str = '1d'
    data_source: str = 'yfinance'
    news_query: str = None # Opsiyonel, eğer verilmezse sembol kullanılır
    news_lang: str = 'en'

@app.post("/api/v1/analyze")
def analyze_symbol(request: AnalysisRequest):
    """
    Belirtilen sembol için tam bir finansal analiz yapar.
    
    - **symbol**: Analiz edilecek hisse senedi veya kripto para sembolü (örn: "BTC-USD", "AAPL").
    - **period**: Veri çekme periyodu (örn: "1y", "6mo").
    - **interval**: Veri çekme aralığı (örn: "1d", "1wk").
    - **data_source**: Veri kaynağı ('yfinance' veya 'alpha_vantage').
    """
    logger.info(f"API isteği alındı: {request.symbol}")
    
    # 1. Piyasa Verilerini Çekme
    market_data = market_fetcher.fetch_market_data(
        symbol=request.symbol, 
        period=request.period, 
        interval=request.interval, 
        data_source=request.data_source,
        av_api_key=config.ALPHA_VANTAGE_API_KEY # API anahtarını da ilet
    )

    # Hata Yönetimi: Eğer market_data boş ise, sembol bulunamamıştır.
    if market_data.empty:
        raise HTTPException(
            status_code=404, 
            detail=f"'{request.symbol}' sembolü için piyasa verisi bulunamadı. Lütfen geçerli bir sembol girin."
        )

    # 2. Haber Verilerini Çekme
    news_query = request.news_query if request.news_query else request.symbol
    news_headlines = []
    if config.NEWS_API_KEY:
        news_data = news_fetcher.fetch_news_from_newsapi(config.NEWS_API_KEY, query=news_query, language=request.news_lang)
        if news_data and news_data.get('articles'):
            news_headlines = [article.get('title', '') for article in news_data['articles'] if article.get('title')]

    # 3. Skorları Hesaplama
    model_scores = calculate_all_model_scores(
        historical_data=market_data, 
        models=models, 
        news_headlines=news_headlines,
        social_media_query=request.symbol,
        interval=request.interval
    )

    # 4. Nihai Skoru ve Uyarıyı Hesaplama
    final_score = scoring_engine.generate_final_score(model_scores)
    alert_message = alert_system.check_for_alert(final_score)
    recommendation_message = models['recommendation'].get_recommendation(final_score)

    # 5. Sonucu Döndürme
    return {
        "symbol": request.symbol,
        "final_score": final_score,
        "alert_message": alert_message,
        "model_scores": model_scores,
        "recommendation_message": recommendation_message,
        "historical_prices": market_data['Close'].reset_index().rename(columns={'Date': 'date', 'Close': 'price'}).to_dict(orient='records')
    }

@app.get("/")
def read_root():
    """
    API'nin çalıştığını doğrulayan kök endpoint.
    """
    return {"message": "OptiTrade API'sine hoş geldiniz! Analiz için /api/v1/analyze endpoint'ine POST isteği gönderin."}

@app.get("/v1/models")
def get_models_info():
    """
    Frontend'den gelebilecek /v1/models isteğini karşılamak için boş bir endpoint.
    """
    return {"message": "Model bilgileri burada listelenebilir, ancak şu an için boş."}

# Sunucuyu çalıştırmak için (geliştirme ortamında):
# uvicorn src.optitrade.api.server:app --reload
