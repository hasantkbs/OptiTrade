
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, Optional, List
import json
import asyncio

# OptiTrade'in yeni mimari bileşenlerini içe aktar
from .. import config
from ..utils.data_fetcher import DataFetcher
from ..scoring.scoring_engine import ScoringEngine
from ..database.database_handler import DatabaseHandler
from ..realtime.binance_stream_handler import BinanceStreamHandler
from ..realtime.stock_stream_handler import StockStreamHandler
from ..realtime.processor import RealtimeProcessor
from ..risk.portfolio_optimizer import PortfolioOptimizer

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

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

# Uygulama ömrü boyunca yaşayacak olan servislerimizi tutacak bir sözlük
app_lifespan_services: Dict[str, Any] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI uygulama ömrü yöneticisi.
    Uygulama başladığında servisleri başlatır ve uygulama kapandığında kaynakları serbest bırakır.
    """
    logger.info("OptiTrade API başlatılıyor...")
    # Servisleri başlat
    data_fetcher = DataFetcher()
    db_handler = DatabaseHandler()
    scoring_engine = ScoringEngine(data_fetcher=data_fetcher, db_handler=db_handler)
    
    # Servisleri global sözlüğe kaydet
    app_lifespan_services["data_fetcher"] = data_fetcher
    app_lifespan_services["scoring_engine"] = scoring_engine
    app_lifespan_services["db_handler"] = db_handler
    app_lifespan_services["realtime_processors"] = {}
    
    logger.info("Tüm servisler başarıyla başlatıldı.")
    yield
    # Uygulama kapandığında çalışacak kod (temizlik vb.)
    logger.info("OptiTrade API kapatılıyor...")
    db_handler.close_connection()
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

@app.websocket("/ws/{asset_type}/{symbol}")
async def websocket_endpoint(websocket: WebSocket, asset_type: str, symbol: str):
    await manager.connect(websocket)
    
    processor_key = f"{asset_type}_{symbol}"
    if processor_key not in app_lifespan_services["realtime_processors"]:
        logger.info(f"Creating new realtime processor for {processor_key}")
        if asset_type == 'crypto':
            stream_handler = BinanceStreamHandler(on_message_callback=realtime_on_message)
        elif asset_type == 'stock':
            stream_handler = StockStreamHandler(on_message_callback=realtime_on_message)
        else:
            logger.error(f"Invalid asset type: {asset_type}")
            return

        processor = RealtimeProcessor(
            stream_handler=stream_handler,
            model_lookback_bars=200
        )
        app_lifespan_services["realtime_processors"][processor_key] = asyncio.create_task(processor.start(symbol, interval="1d")) # Assuming 1d for now
    
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        # If no more clients are listening for this symbol, stop the processor
        if not any(processor_key in ws.path_params for ws in manager.active_connections):
            logger.info(f"Stopping realtime processor for {processor_key}")
            app_lifespan_services["realtime_processors"][processor_key].cancel()
            del app_lifespan_services["realtime_processors"][processor_key]

async def realtime_on_message(data: dict):
    await manager.broadcast(json.dumps(data))

@app.get("/api/v1/signals", response_model=Dict[str, Any])
def get_trading_signals(
    asset_type: str = Query("crypto", description="Varlık tipi (crypto veya stock)"),
    symbol: str = Query(..., description="Analiz edilecek finansal varlık sembolü (örn: BTC-USD)"),
    interval: str = Query("1d", description="Analiz aralığı (örn: 15m, 4h, 1d)"),
    rsi_period: Optional[int] = Query(None, description="RSI periyodu (örn: 14). Eğer belirtilmezse modelin varsayılan değeri kullanılır."),
    model_params: Optional[str] = Query(None, description="JSON formatında diğer model parametreleri (örn: {\"VolumeSurgeModel\":{\"window\":5}})"),
    scoring_engine: ScoringEngine = Depends(get_scoring_engine)
):
    logger.info(f"Sinyal isteği alındı: Varlık Tipi='{asset_type}', Sembol='{symbol}', Aralık='{interval}'")
    if not symbol:
        raise HTTPException(
            status_code=400,
            detail="Lütfen 'symbol' parametresi ile geçerli bir sembol girin."
        )

    parsed_model_params = {}
    if model_params:
        try:
            parsed_model_params = json.loads(model_params)
            logger.info(f"Alınan diğer model parametreleri: {parsed_model_params}")
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="model_params geçerli bir JSON formatında değil.")

    # RSI periyodu doğrudan parametre olarak geldiyse, PriceTrendModel için ayarla
    if rsi_period is not None:
        if "PriceTrendModel" not in parsed_model_params:
            parsed_model_params["PriceTrendModel"] = {}
        parsed_model_params["PriceTrendModel"]["rsi_window"] = rsi_period
        logger.info(f"RSI periyodu PriceTrendModel için ayarlandı: {rsi_period}")

    try:
        # Analiz ve tüm hesaplamalar artık ScoringEngine içinde yapılıyor
        analysis_result = scoring_engine.run_engine(asset_type=asset_type, symbol=symbol, interval=interval, model_params=parsed_model_params)
        return analysis_result

@app.get("/api/v1/market_data", response_model=list[Dict[str, Any]])
def get_market_data_for_chart(
    asset_type: str = Query("crypto", description="Varlık tipi (crypto veya stock)"),
    symbol: str = Query(..., description="Grafik için finansal varlık sembolü (örn: BTC-USD)"),
    interval: str = Query("1d", description="Grafik için analiz aralığı (örn: 15m, 4h, 1d)"),
    data_fetcher: DataFetcher = Depends(get_data_fetcher)
):
    """Frontend'de grafik çizimi için geçmiş piyasa verilerini sağlar."""
    logger.info(f"Grafik verisi isteği alındı: Varlık Tipi='{asset_type}', Sembol='{symbol}', Aralık='{interval}'")
    try:
        period_map = {"15m": "60d", "4h": "730d", "1d": "5y"}
        fetch_period = period_map.get(interval, "5y")
        
        market_data = data_fetcher.get_market_data(asset_type=asset_type, symbol=symbol, period=fetch_period, interval=interval)
        
        if market_data.empty:
            return []

        # Recharts'ın beklediği formata dönüştür (JSON array)
        market_data.reset_index(inplace=True)
        # Tarih formatını daha okunabilir yapalım
        market_data['Date'] = market_data['Date'].dt.strftime('%Y-%m-%d %H:%M')
        return market_data.to_dict(orient='records')

    except Exception as e:
        logger.error(f"'{symbol}' için grafik verisi çekilirken bir hata oluştu: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Sunucu hatası: Grafik verisi çekilirken bir sorun oluştu."
        )

@app.get("/api/v1/portfolio/optimize", response_model=Dict[str, Any])
def optimize_portfolio(
    symbols: str = Query(..., description="Comma-separated list of symbols (e.g., 'AAPL,MSFT,GOOG')."),
    start_date: str = Query(..., description="Start date for historical data (YYYY-MM-DD)."),
    end_date: str = Query(..., description="End date for historical data (YYYY-MM-DD)."),
):
    logger.info(f"Portfolio optimization request received for symbols: {symbols}, from {start_date} to {end_date}")
    try:
        symbol_list = [s.strip() for s in symbols.split(',')]
        optimizer = PortfolioOptimizer()
        optimal_portfolio = optimizer.optimize_portfolio(symbol_list, start_date, end_date)
        return optimal_portfolio
    except Exception as e:
        logger.error(f"Error during portfolio optimization: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Server error during portfolio optimization: {e}"
        )

@app.get("/")
def read_root():
    return {"message": "OptiTrade API v2.0'a hoş geldiniz! Analiz için /api/v1/signals endpoint'ini kullanın."}

# Sunucuyu çalıştırmak için (geliştirme ortamında):
# uvicorn src.optitrade.api.server:app --reload
