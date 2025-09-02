import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any

# OptiTrade'in yeni mimari bileşenlerini içe aktar
from .. import config
from ..utils.data_fetcher import DataFetcher
from ..scoring.scoring_engine import ScoringEngine

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

# Uygulama ömrü boyunca yaşayacak olan servislerimizi tutacak bir sözlük
app_lifespan_services: Dict[str, Any] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI uygulama ömrü yöneticisi.
    Uygulama başladığında servisleri başlatır ve uygulama kapandığında kaynakları serbest bırakır.
    """
    logger.info("OptiTrade API başlatılıyor...")
    # Merkezi DataFetcher servisini başlat
    data_fetcher = DataFetcher()
    # ScoringEngine'i DataFetcher ile başlat
    scoring_engine = ScoringEngine(data_fetcher=data_fetcher)
    
    # Servisleri global sözlüğe kaydet
    app_lifespan_services["data_fetcher"] = data_fetcher
    app_lifespan_services["scoring_engine"] = scoring_engine
    
    logger.info("Tüm servisler başarıyla başlatıldı.")
    yield
    # Uygulama kapandığında çalışacak kod (temizlik vb.)
    logger.info("OptiTrade API kapatılıyor...")
    app_lifespan_services.clear()

# FastAPI uygulamasını başlat
app = FastAPI(
    title="OptiTrade API",
    description="Dinamik ve modüler finansal analiz ve ticaret sinyali üretimi için API.",
    version="2.0.0",
    lifespan=lifespan
)

# CORS (Cross-Origin Resource Sharing) Middleware'ini ekle
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"]
)

# Bağımlılık Enjeksiyonu (Dependency Injection) için fonksiyonlar
def get_scoring_engine() -> ScoringEngine:
    return app_lifespan_services["scoring_engine"]

def get_data_fetcher() -> DataFetcher:
    return app_lifespan_services["data_fetcher"]

@app.get("/api/v1/signals", response_model=Dict[str, Any])
def get_trading_signals(
    symbol: str = Query(..., description="Analiz edilecek finansal varlık sembolü (örn: BTC-USD)"),
    interval: str = Query("1d", description="Analiz aralığı (örn: 15m, 4h, 1d)"),
    scoring_engine: ScoringEngine = Depends(get_scoring_engine),
    data_fetcher: DataFetcher = Depends(get_data_fetcher)
):
    logger.info(f"Sinyal isteği alındı: Sembol='{symbol}', Aralık='{interval}'")
    if not symbol:
        raise HTTPException(
            status_code=400,
            detail="Lütfen 'symbol' parametresi ile geçerli bir sembol girin."
        )

    try:
        # Sembolün anlık piyasa fiyatını çek
        # En son fiyatı almak için kısa bir periyot ve interval kullan
        # Not: 1m interval sadece 7 günlük veri çekebilir, 15m için 60 gün, 4h için 730 gün
        # Bu yüzden period parametresini interval'e göre ayarlamak daha doğru olur.
        period_map = {"15m": "60d", "4h": "730d", "1d": "5y"}
        fetch_period = period_map.get(interval, "5y") # Varsayılan 5 yıl

        latest_data = data_fetcher.get_market_data(symbol=symbol, period=fetch_period, interval=interval)
        current_price = None
        if not latest_data.empty:
            current_price = latest_data['Close'].iloc[-1]
            logger.info(f"'{symbol}' için anlık piyasa fiyatı: {current_price:.2f}")
        else:
            logger.warning(f"'{symbol}' için anlık piyasa fiyatı çekilemedi.")

        analysis_result = scoring_engine.run_engine(symbol=symbol, interval=interval)
        
        analysis_result["current_market_price"] = float(current_price) if current_price is not None else None

        return analysis_result
    except Exception as e:
        logger.error(f"'{symbol}' için analiz yapılırken bir hata oluştu: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Sunucu hatası: Analiz işlemi sırasında beklenmedik bir sorun oluştu."
        )

@app.get("/")
def read_root():
    return {"message": "OptiTrade API v2.0'a hoş geldiniz! Analiz için /api/v1/signals endpoint'ini kullanın."}

# Sunucuyu çalıştırmak için (geliştirme ortamında):
# uvicorn src.optitrade.api.server:app --reload