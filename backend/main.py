from fastapi import FastAPI, HTTPException, Query, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from typing import Any, Dict, List, Optional, Union
import logging
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

load_dotenv()  # backend/.env varsa (ör. GROQ_API_KEY) burada yüklenir

from models.schemas import (
    AnalysisRequest, AnalysisResult, ScanRequest, ScanResult,
    ChartResponse, ChartPoint,
    EnhancedAnalysisRequest, MonteCarloResult, RecommendationResult,
    PortfolioOptRequest, PortfolioOptResult,
    SessionInfo,
)
from core.analyzer import analyze
from core.ml_predictor import get_model_info
from core.monitoring import init_db, log_prediction, validate_predictions, get_performance_stats
from research.ml_trainer import train as train_model
from core.advanced_analysis import run_monte_carlo, optimize_portfolio, compute_recommendation
from core.session_analysis import compute_session_score, get_current_session, SESSIONS
from core.news_analyzer import get_news_summary, analyze_news
from core.sector_intelligence import (
    analyze_sector, get_sector_overview,
    sector_overview_to_dict, sector_detail_to_dict,
    SECTOR_DEFINITIONS,
)
from data.fetcher import fetch_history
from v2.api.router import router as v2_router
from api.v1.router import api_v1_router
from core.rate_limiter import limiter
from pipeline import PipelineResponse, PipelineService, QuantAnalysisRequest
from model_serving import MLPredictionRequest, MLPredictionResult, ServingHealthReport
from model_serving.exceptions import ModelServingError, NoActiveModelError
from portfolio import (
    PortfolioDashboardService,
    PortfolioOptimizationService,
    PortfolioService,
    PositionAnalyticsService,
    RebalancingService,
    RecommendationEngine,
    RiskAnalyticsService,
    ScenarioAnalysisService,
)
from portfolio.exceptions import (
    InsufficientCashError,
    InsufficientPositionError,
    InsufficientPriceDataError,
    InvalidTransactionError,
    PortfolioError,
    PortfolioNotFoundError,
)
from portfolio.models import (
    CreatePortfolioRequest,
    DepositRequest,
    DividendRequest,
    OptimizationResult,
    OptimizeRequest,
    Portfolio,
    PortfolioDashboard,
    PortfolioSnapshot,
    PositionAnalytics,
    RebalancePlan,
    RebalanceRequest,
    Recommendation,
    RecommendationsRequest,
    RiskAnalytics,
    ScenarioRequest,
    ScenarioResult,
    ScenarioType,
    TradeRequest,
    Transaction,
    WithdrawRequest,
)
from watchlist import AlertScheduler, WatchlistService
from watchlist.exceptions import (
    AlertNotFoundError,
    InsufficientAlertDataError,
    InvalidAlertError,
    WatchlistError,
    WatchlistItemNotFoundError,
    WatchlistNotFoundError,
)
from watchlist.models import (
    AddWatchlistItemRequest,
    Alert,
    CreateAlertRequest,
    CreateWatchlistRequest,
    ScanReport,
    SetAlertEnabledRequest,
    Watchlist,
    WatchlistItem,
)
from users import (
    APIKeyService,
    AuditService,
    AuthenticationService,
    AuthorizationService,
    OrganizationService,
    PreferencesService,
    SessionService,
    TeamService,
    UserService,
    UsersRepository,
)
from users.authentication import decode_access_token
from users.exceptions import (
    APIKeyNotFoundError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidTokenError,
    InvitationNotFoundError,
    LastOwnerError,
    MembershipNotFoundError,
    OrganizationNotFoundError,
    PermissionDeniedError,
    QuotaExceededError,
    TeamNotFoundError,
    UserNotFoundError,
    UserPlatformError,
    ValidationFailedError,
)
from users.models import DeviceInfo, OrganizationQuotas, Permission as UsersPermission, User as UsersUser
from users.schemas import (
    AcceptInvitationRequest,
    AddTeamMemberRequest,
    APIKeyCreatedResponse,
    APIKeyResponse,
    APIKeyUsageStatsResponse,
    AuditLogEntryResponse,
    ChangeRoleRequest,
    CreateAPIKeyRequest,
    CreateOrganizationRequest,
    CreateTeamRequest,
    InvitationCreatedResponse,
    InvitationResponse,
    InviteMemberRequest,
    LoginHistoryEntryResponse,
    LoginRequest,
    LogoutRequest,
    MembershipResponse,
    OrganizationResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequestSchema,
    PreferencesResponse,
    RefreshRequest,
    RegisterRequest,
    ResourceUsageResponse,
    SessionResponse,
    TeamMembershipResponse,
    TeamResponse,
    TokenPairResponse,
    UpdateOrganizationRequest,
    UpdatePreferencesRequest,
    UpdateProfileRequest,
    UserResponse,
)
from feature_store.service import FeatureStoreService
from paper_trading import (
    JournalService,
    PaperTradingRepository,
    PaperTradingScheduler,
    PaperTradingService,
    PortfolioSyncService,
    PositionService,
)
from paper_trading.exceptions import (
    AccountNotFoundError,
    InsufficientPaperCashError,
    InsufficientPaperPositionError,
    InvalidOrderError,
    JournalEntryNotFoundError,
    MarketClosedError,
    OrderNotFoundError,
    OrderNotOpenError,
    PaperTradingError,
)
from paper_trading.exceptions import ValidationFailedError as PaperTradingValidationFailedError
from paper_trading.models import (
    AnalyticsSummary,
    ClosedTrade,
    EquityPoint,
    MonthlyPerformance,
    Order as PaperOrder,
    OrderStatus as PaperOrderStatus,
    ReportPeriod,
    TradeReport,
)
from paper_trading.schemas import (
    AccountResponse,
    AddJournalTagsRequest,
    AddScreenshotRequest,
    CreateAccountRequest,
    JournalEntryResponse,
    ModifyOrderRequest,
    OrderResponse,
    PlaceOrderRequest,
    ScreenshotResponse,
    UpdateJournalNotesRequest,
)
from dashboard import (
    AlertDashboardService,
    DashboardPortfolioService,
    DashboardRepository,
    DashboardScheduler,
    DashboardService,
    EngineDashboardService,
    LearningDashboardService,
    MarketDashboardService,
    ModelDashboardService,
    OverviewDashboardService,
    PaperTradingDashboardService,
    WatchlistDashboardService,
)
from dashboard.exceptions import DashboardError
from dashboard.models import (
    AlertDashboardView,
    DashboardReport,
    EngineDashboardView,
    LearningDashboardView,
    MarketDashboardView,
    MLDashboardView,
    OverviewMetrics,
    PaperTradingDashboardView,
    PortfolioDashboardExtended,
    ReportFormat,
    ReportPeriod as DashboardReportPeriod,
    WatchlistDashboardView,
)
from learning.models import RollingWindow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Firebase Admin ─────────────────────────────────────────────────────────────
_firebase_app = None
try:
    import firebase_admin
    from firebase_admin import credentials, auth as fb_auth

    _cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "firebase-credentials.json")
    if os.path.exists(_cred_path):
        cred = credentials.Certificate(_cred_path)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK baslatildi.")
    else:
        logger.warning("Firebase credentials bulunamadi. Auth devre disi.")
except ImportError:
    logger.warning("firebase-admin paketi kurulu degil. Auth devre disi.")

# ── Rate Limiter (bkz. core/rate_limiter.py — api/ router'larıyla paylaşılır) ───

# ── FastAPI App ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="OptiTrade API",
    description="Hisse senedi ve kripto analiz motoru — v3.1",
    version="3.1.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS (production-ready) ────────────────────────────────────────────────────
ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://localhost:3000",
    "https://optitrade-fcda9.web.app",
    "https://optitrade-fcda9.firebaseapp.com",
]
_cors_origins = os.getenv("ALLOWED_ORIGINS", "").split(",")
ALLOWED_ORIGINS += [o.strip() for o in _cors_origins if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(v2_router)
app.include_router(api_v1_router)

# ── Background Tasks ──────────────────────────────────────────────────────────

async def self_evolution_loop() -> None:
    """Günlük doğrulama ve haftalık eğitim yapan arka plan döngüsü.

    validate_predictions()/train_model() are synchronous and slow
    (network + CPU-bound) - run through the executor thread pool (see
    _run_in_executor below), same as every other blocking call in this
    file, so a daily validation/retraining cycle never freezes the
    event loop (and therefore every concurrent request) for its
    duration."""
    while True:
        try:
            logger.info("Kendi kendini geliştirme döngüsü çalışıyor...")
            # 1. Tahminleri doğrula
            validated = await _run_in_executor(validate_predictions)
            if validated > 0:
                logger.info(f"{validated} tahmin doğrulandı.")

            # 2. Haftalık eğitimi kontrol et (Her Pazar gecesi gibi basit bir mantık veya her 7 günde bir)
            # Şimdilik basitçe her gün bir kez kontrol edip haftalık tetikleme yapabiliriz
            # Ya da doğrudan her gün eğitimi yenileyebiliriz (veri seti küçükse)
            # Kullanıcının isteği üzerine günlük ve haftalık test/eğitim:
            await _run_in_executor(train_model)
            logger.info("Model güncel verilerle yeniden eğitildi.")

        except Exception as e:
            logger.error(f"Self-evolution döngüsünde hata: {e}")

        # 24 saat bekle (86400 saniye)
        await asyncio.sleep(86400)


_WATCHLIST_ALERT_SCAN_INTERVAL_SECONDS = 60
_PAPER_TRADING_FILL_SCAN_INTERVAL_SECONDS = 30


async def alert_scan_loop() -> None:
    """Periodically runs every enabled alert through
    `AlertScheduler.run_scan` (watchlist/scheduler.py) - previously
    instantiated at startup but never invoked by anything, so no price/
    technical/decision/news/portfolio alert could ever actually fire."""
    while True:
        await asyncio.sleep(_WATCHLIST_ALERT_SCAN_INTERVAL_SECONDS)
        if _watchlist_scheduler is None:
            continue
        try:
            report = await _run_in_executor(_watchlist_scheduler.run_scan)
            if report.triggered_count:
                logger.info(f"Alert taraması: {report.triggered_count} alert tetiklendi.")
        except Exception as e:
            logger.error(f"Alert tarama döngüsünde hata: {e}")


async def paper_trading_fill_loop() -> None:
    """Periodically runs every resting LIMIT/STOP/TAKE_PROFIT order
    through `PaperTradingScheduler.scan_pending_orders`
    (paper_trading/scheduler.py) - previously instantiated at startup
    but never invoked by anything, so a resting order was accepted and
    reported as "pending" but could never actually fill."""
    while True:
        await asyncio.sleep(_PAPER_TRADING_FILL_SCAN_INTERVAL_SECONDS)
        if _paper_trading_scheduler is None:
            continue
        try:
            fills = await _run_in_executor(_paper_trading_scheduler.scan_pending_orders)
            if fills:
                logger.info(f"Paper trading: {len(fills)} bekleyen emir dolduruldu.")
        except Exception as e:
            logger.error(f"Paper trading dolum döngüsünde hata: {e}")


@app.on_event("startup")
async def startup_event() -> None:
    init_db()
    global _pipeline_service, _portfolio_service, _portfolio_analytics, _portfolio_risk
    global _portfolio_optimization, _portfolio_rebalancing, _portfolio_scenarios
    global _portfolio_recommendations, _portfolio_dashboard
    try:
        _pipeline_service = PipelineService()
    except Exception as e:
        logger.error(f"Quant pipeline baslatilamadi: {e}")
    try:
        _portfolio_service = PortfolioService()
        _portfolio_analytics = PositionAnalyticsService(portfolio_service=_portfolio_service)
        _portfolio_risk = RiskAnalyticsService(position_analytics_service=_portfolio_analytics)
        _portfolio_rebalancing = RebalancingService(position_analytics_service=_portfolio_analytics)
        # Both optimization and recommendations reuse the same live
        # Quant Research Platform pipeline for their forward-looking
        # views (requirement 4's "Reuse existing Prediction Pipeline
        # outputs", requirement 7's "Use Decision Engine outputs") -
        # `None` (views disabled) until `_pipeline_service` itself is
        # ready, exactly like every other consumer of it in this file.
        _portfolio_optimization = PortfolioOptimizationService(
            price_service=_portfolio_service.price_service, pipeline_service=_pipeline_service,
        )
        _portfolio_scenarios = ScenarioAnalysisService(position_analytics_service=_portfolio_analytics)
        _portfolio_recommendations = RecommendationEngine(
            position_analytics_service=_portfolio_analytics, risk_analytics_service=_portfolio_risk,
            rebalancing_service=_portfolio_rebalancing, pipeline_service=_pipeline_service,
        )
        _portfolio_dashboard = PortfolioDashboardService(
            portfolio_service=_portfolio_service, position_analytics_service=_portfolio_analytics,
            risk_analytics_service=_portfolio_risk, recommendation_engine=_portfolio_recommendations,
        )
    except Exception as e:
        logger.error(f"Portfolio Intelligence Platform baslatilamadi: {e}")

    global _users_repository, _users_authentication, _users_authorization, _users_sessions
    global _users_organizations, _users_teams, _users_api_keys, _users_preferences
    global _users_audit, _users_service, _users_watchlist_bridge, _watchlist_scheduler
    try:
        _users_repository = UsersRepository()
        _users_sessions = SessionService(_users_repository)
        _users_authentication = AuthenticationService(_users_repository, session_cache=_users_sessions)
        _users_authorization = AuthorizationService(_users_repository)
        _users_organizations = OrganizationService(_users_repository, _users_authorization)
        _users_teams = TeamService(_users_repository, _users_authorization)
        _users_audit = AuditService(_users_repository)
        _users_api_keys = APIKeyService(_users_repository, _users_authorization, _users_audit)
        _users_watchlist_bridge = WatchlistService()
        # Reuses _users_watchlist_bridge's own repository/connection pool
        # (same convention as portfolio_sync's watchlist_repository= above)
        # instead of opening a second one just for the scheduler.
        _watchlist_scheduler = AlertScheduler(repository=_users_watchlist_bridge.repository)
        _users_preferences = PreferencesService(
            _users_repository, portfolio_service=_portfolio_service, watchlist_service=_users_watchlist_bridge,
        )
        _users_service = UserService(_users_repository, _users_authentication)
    except Exception as e:
        logger.error(f"User & Organization Platform baslatilamadi: {e}")

    global _paper_trading_repository, _paper_trading_service, _paper_trading_scheduler
    try:
        _paper_trading_repository = PaperTradingRepository()
        feature_store_service = FeatureStoreService()
        portfolio_sync = PortfolioSyncService(
            _paper_trading_repository, _portfolio_service, watchlist_service=_users_watchlist_bridge,
            watchlist_repository=_users_watchlist_bridge.repository if _users_watchlist_bridge else None,
        )
        position_service = PositionService(_portfolio_service)
        journal_service = JournalService(_paper_trading_repository, _pipeline_service, feature_store_service=feature_store_service)
        _paper_trading_service = PaperTradingService(
            _paper_trading_repository, portfolio_sync, position_service, journal_service,
        )
        _paper_trading_scheduler = PaperTradingScheduler(_paper_trading_repository, portfolio_sync)
    except Exception as e:
        logger.error(f"Paper Trading Platform baslatilamadi: {e}")

    global _dashboard_repository, _dashboard_service, _dashboard_scheduler
    try:
        _dashboard_repository = DashboardRepository()
        dashboard_overview_service = OverviewDashboardService(_dashboard_repository)
        dashboard_engine_service = EngineDashboardService(_dashboard_repository)
        dashboard_market_service = MarketDashboardService()
        _dashboard_service = DashboardService(
            _dashboard_repository,
            overview_service=dashboard_overview_service,
            engine_dashboard_service=dashboard_engine_service,
            model_dashboard_service=ModelDashboardService(_dashboard_repository),
            portfolio_dashboard_service=(
                DashboardPortfolioService(portfolio_dashboard_service=_portfolio_dashboard, portfolio_service=_portfolio_service)
                if _portfolio_dashboard is not None else DashboardPortfolioService()
            ),
            watchlist_dashboard_service=(
                WatchlistDashboardService(watchlist_service=_users_watchlist_bridge)
                if _users_watchlist_bridge is not None else WatchlistDashboardService()
            ),
            paper_trading_dashboard_service=(
                PaperTradingDashboardService(paper_trading_repository=_paper_trading_repository)
                if _paper_trading_repository is not None else PaperTradingDashboardService()
            ),
            learning_dashboard_service=LearningDashboardService(_dashboard_repository),
            alert_dashboard_service=AlertDashboardService(_dashboard_repository),
            market_dashboard_service=dashboard_market_service,
        )
        _dashboard_scheduler = DashboardScheduler(dashboard_overview_service, dashboard_market_service, dashboard_engine_service)
    except Exception as e:
        logger.error(f"Analytics & Dashboard Platform baslatilamadi: {e}")
    asyncio.create_task(self_evolution_loop())
    asyncio.create_task(alert_scan_loop())
    asyncio.create_task(paper_trading_fill_loop())

@app.get("/ml/performance")
def get_ml_performance(days: int = 30) -> Dict[str, Any]:
    return get_performance_stats(days=days)

# ── Symbol Lists ───────────────────────────────────────────────────────────────
_DEFAULT_BIST_SYMBOLS = [
    "THYAO.IS", "GARAN.IS", "ASELS.IS", "KCHOL.IS", "SISE.IS",
    "EREGL.IS", "BIMAS.IS", "AKBNK.IS", "YKBNK.IS", "TUPRS.IS",
    "TOASO.IS", "FROTO.IS", "SAHOL.IS", "PGSUS.IS", "TAVHL.IS",
]
_DEFAULT_CRYPTO_SYMBOLS = [
    "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "AVAX-USD",
    "XRP-USD", "ADA-USD", "DOT-USD", "LINK-USD", "DOGE-USD",
]


def _symbols_from_env(env_var: str, default: List[str]) -> List[str]:
    """`env_var` as a comma-separated symbol list, falling back to
    `default` exactly (no env var set, or set empty) - matches this
    file's own existing `ALLOWED_ORIGINS` convention. Public-symbol
    coverage (/scan/bist, /scan/crypto, /symbols/bist, /symbols/crypto)
    is operator-configurable without a code change, with today's
    hardcoded lists preserved as the default."""
    raw = os.getenv(env_var, "")
    if not raw.strip():
        return default
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


BIST_SYMBOLS = _symbols_from_env("BIST_SYMBOLS", _DEFAULT_BIST_SYMBOLS)
CRYPTO_SYMBOLS = _symbols_from_env("CRYPTO_SYMBOLS", _DEFAULT_CRYPTO_SYMBOLS)
BUY_CODES  = {"STRONG_BUY", "BUY"}
SELL_CODES = {"STRONG_SELL", "SELL"}

# Thread pool for parallel yfinance calls
_executor = ThreadPoolExecutor(max_workers=16)

# Quant Research Platform pipeline — constructed once at startup (see
# startup_event) and reused across every request; None until then.
_pipeline_service: Optional[PipelineService] = None

# Portfolio Intelligence Platform — same "construct once at startup,
# reuse across every request" convention; all None until startup_event
# finishes wiring them up.
_portfolio_service: Optional[PortfolioService] = None
_portfolio_analytics: Optional[PositionAnalyticsService] = None
_portfolio_risk: Optional[RiskAnalyticsService] = None
_portfolio_optimization: Optional[PortfolioOptimizationService] = None
_portfolio_rebalancing: Optional[RebalancingService] = None
_portfolio_scenarios: Optional[ScenarioAnalysisService] = None
_portfolio_recommendations: Optional[RecommendationEngine] = None
_portfolio_dashboard: Optional[PortfolioDashboardService] = None

# User & Organization Platform — same "construct once at startup, reuse
# across every request" convention; all None until startup_event
# finishes wiring them up.
_users_repository: Optional[UsersRepository] = None
_users_authentication: Optional[AuthenticationService] = None
_users_authorization: Optional[AuthorizationService] = None
_users_sessions: Optional[SessionService] = None
_users_organizations: Optional[OrganizationService] = None
_users_teams: Optional[TeamService] = None
_users_api_keys: Optional[APIKeyService] = None
_users_preferences: Optional[PreferencesService] = None
_users_audit: Optional[AuditService] = None
_users_service: Optional[UserService] = None
_users_watchlist_bridge: Optional[WatchlistService] = None
_watchlist_scheduler: Optional[AlertScheduler] = None

# Paper Trading & Trade Journal Platform — same convention.
_paper_trading_repository: Optional[PaperTradingRepository] = None
_paper_trading_service: Optional[PaperTradingService] = None
_paper_trading_scheduler: Optional[PaperTradingScheduler] = None

# Analytics & Dashboard Platform — same convention.
_dashboard_repository: Optional[DashboardRepository] = None
_dashboard_service: Optional[DashboardService] = None
_dashboard_scheduler: Optional[DashboardScheduler] = None

# ── Firebase Auth Dependency ───────────────────────────────────────────────────
async def verify_firebase_token(
    authorization: Optional[str] = Header(default=None)
) -> Optional[str]:
    if _firebase_app is None:
        return None
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Yetkilendirme tokeni eksik.")
    token = authorization.split(" ", 1)[1]
    try:
        decoded = fb_auth.verify_id_token(token, app=_firebase_app)
        return decoded["uid"]
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Gecersiz token: {e}")

# ── Portfolio Intelligence Platform helpers ─────────────────────────────────────
async def _run_in_executor(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, func, *args)


def _authorize_portfolio_access(portfolio_obj: Portfolio, user: UsersUser) -> None:
    # Same identity (Users-platform email) and check as
    # _get_owned_portfolio_for_dashboard below - a portfolio's owner must
    # never be compared against two different identity systems (Firebase
    # uid vs. Users-platform email) depending on which endpoint is hit.
    if portfolio_obj.owner != user.email:
        raise HTTPException(status_code=403, detail="Bu portfoye erisim izniniz yok.")


def _require_portfolio_service() -> None:
    if _portfolio_service is None:
        raise HTTPException(status_code=503, detail="Portfoy servisi henuz hazir degil.")


def _map_portfolio_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PortfolioNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (InsufficientCashError, InsufficientPositionError, InvalidTransactionError)):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, InsufficientPriceDataError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, PortfolioError):
        return HTTPException(status_code=500, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))

# ── User & Organization Platform helpers ────────────────────────────────────────

def _require_users_service() -> None:
    if _users_repository is None:
        raise HTTPException(status_code=503, detail="Kullanici servisi henuz hazir degil.")


def _map_users_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (InvalidCredentialsError, InvalidTokenError)):
        return HTTPException(status_code=401, detail=str(exc))
    if isinstance(exc, (PermissionDeniedError, MembershipNotFoundError)):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, (UserNotFoundError, OrganizationNotFoundError, TeamNotFoundError,
                         APIKeyNotFoundError, InvitationNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (EmailAlreadyRegisteredError, QuotaExceededError, LastOwnerError, ValidationFailedError)):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, UserPlatformError):
        return HTTPException(status_code=500, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


async def _get_current_user(authorization: Optional[str] = Header(default=None)) -> UsersUser:
    _require_users_service()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Yetkilendirme tokeni eksik.")
    token = authorization.split(" ", 1)[1]
    try:
        user_id = decode_access_token(token)
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    user = _users_repository.get_user(user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Kullanici bulunamadi veya devre disi.")
    return user


def _device_from_request(request: Request) -> DeviceInfo:
    return DeviceInfo(
        user_agent=request.headers.get("user-agent", ""),
        ip_address=request.client.host if request.client else "",
    )

# ── Paper Trading & Trade Journal Platform helpers ──────────────────────────────

def _require_paper_trading_service() -> None:
    if _paper_trading_service is None:
        raise HTTPException(status_code=503, detail="Kagit uzerinde islem servisi henuz hazir degil.")


def _map_paper_trading_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (AccountNotFoundError, OrderNotFoundError, JournalEntryNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, OrderNotOpenError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, MarketClosedError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, (InvalidOrderError, PaperTradingValidationFailedError, InsufficientPaperCashError,
                         InsufficientPaperPositionError, InsufficientCashError, InsufficientPositionError,
                         InvalidTransactionError)):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, InsufficientPriceDataError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, (PaperTradingError, PortfolioError)):
        return HTTPException(status_code=500, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def _get_authorized_paper_account(account_id: int, user: UsersUser):
    account = _paper_trading_service.get_account(account_id)
    if account.user_id != user.id:
        raise HTTPException(status_code=403, detail="Bu kagit uzerinde islem hesabina erisim izniniz yok.")
    return account


def _get_authorized_paper_order(order_id: int, user: UsersUser) -> PaperOrder:
    order = _paper_trading_service.get_order(order_id)
    _get_authorized_paper_account(order.account_id, user)
    return order

# ── Analytics & Dashboard Platform helpers ──────────────────────────────────────

def _require_dashboard_service() -> None:
    if _dashboard_service is None:
        raise HTTPException(status_code=503, detail="Panel servisi henuz hazir degil.")


def _map_dashboard_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (PortfolioNotFoundError, AccountNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, DashboardError):
        return HTTPException(status_code=500, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def _get_owned_portfolio_for_dashboard(portfolio_id: int, user: UsersUser):
    portfolio_obj = _portfolio_service.get_portfolio(portfolio_id)
    if portfolio_obj.owner != user.email:
        raise HTTPException(status_code=403, detail="Bu portfoye erisim izniniz yok.")
    return portfolio_obj

# ── Helpers ────────────────────────────────────────────────────────────────────
def categorize(results: List[AnalysisResult]) -> ScanResult:
    top_buys = sorted(
        [r for r in results if r.decision_code in BUY_CODES],
        key=lambda x: x.score, reverse=True,
    )[:10]
    top_sells = sorted(
        [r for r in results if r.decision_code in SELL_CODES],
        key=lambda x: x.score,
    )[:10]
    neutral = [r for r in results if r.decision_code == "NEUTRAL"]
    return ScanResult(
        top_buys=top_buys, top_sells=top_sells,
        neutral=neutral, total_scanned=len(results),
    )

def _enrich_result(result: AnalysisResult, mc_data: Optional[Dict[str, Any]]) -> AnalysisResult:
    mc_model = None
    if mc_data and mc_data.get("n_simulations", 0) > 0:
        mc_model = MonteCarloResult(**mc_data)
    # Chart AI entegrasyonu (model varsa)
    chart_ai_result = None
    try:
        from ml.chart_model import predict_chart_signal, is_model_available
        if is_model_available():
            import yfinance as yf
            hist_ai = yf.Ticker(result.symbol).history(period="3mo")
            if not hist_ai.empty:
                chart_ai_result = predict_chart_signal(hist_ai)
    except Exception:
        pass
    rec_data = compute_recommendation(
        score=result.score,
        ml_confidence=result.ml_confidence,
        monte_carlo=mc_data,
        risk_level=result.risk_level,
        chart_ai=chart_ai_result,
    )
    return result.model_copy(update={
        "monte_carlo":     mc_model,
        "recommendation":  RecommendationResult(**rec_data),
    })

def _analyze_safe(symbol: str, asset_type: str) -> Optional[AnalysisResult]:
    try:
        return analyze(symbol=symbol, asset_type=asset_type)
    except Exception as e:
        logger.warning(f"Analiz hatasi {symbol}: {e}")
        return None

async def _parallel_scan(symbols: List[str], asset_type: str) -> List[AnalysisResult]:
    """Tüm sembolleri ThreadPoolExecutor ile paralel analiz et."""
    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(_executor, _analyze_safe, sym, asset_type)
        for sym in symbols
    ]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]

# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/")
def root() -> Dict[str, str]:
    return {"status": "ok", "message": "OptiTrade API v3.2"}

@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "healthy"}

@app.get("/ml/status")
def ml_status() -> Dict[str, Any]:
    return get_model_info()

# ── News ──────────────────────────────────────────────────────────────────────

@app.get("/news/{symbol}")
@limiter.limit("20/minute")
def news_for_symbol(
    request: Request,
    symbol: str,
    market: str = "AUTO",   # TR | US | CRYPTO | AUTO
    uid: Optional[str] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """Sembol için haber duygu analizini döndür. market=TR|US|CRYPTO|AUTO"""
    return get_news_summary(symbol.upper(), market=market.upper())

@app.post("/news/sector")
@limiter.limit("10/minute")
def news_for_sector(
    request: Request,
    body: Dict[str, Any],
    uid: Optional[str] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """
    Piyasa/sektöre göre birden fazla sembol için haberler.
    Body: {"symbols": ["GARAN.IS","THYAO.IS"], "market": "TR"}
    """
    symbols: List[str] = body.get("symbols", [])[:10]
    market  = body.get("market", "AUTO").upper()
    if not symbols:
        raise HTTPException(status_code=400, detail="symbols listesi gerekli")

    results: List[Dict[str, Any]] = []
    for sym in symbols:
        try:
            summary = get_news_summary(sym.upper(), market=market)
            results.append(summary)
        except Exception as e:
            logger.warning(f"Haber hatası {sym}: {e}")

    if not results:
        raise HTTPException(status_code=404, detail="Haber alınamadı")

    avg_sentiment = sum(r["sentiment_score"] for r in results) / len(results)
    total_pos = sum(r["positive_count"] for r in results)
    total_neg = sum(r["negative_count"] for r in results)
    sector_label = (
        "POSITIVE"          if avg_sentiment >  0.3 else
        "SLIGHTLY_POSITIVE" if avg_sentiment >  0.05 else
        "SLIGHTLY_NEGATIVE" if avg_sentiment > -0.3 else
        "NEGATIVE"          if avg_sentiment <= -0.3 else
        "NEUTRAL"
    )
    return {
        "symbols":          symbols,
        "market":           market,
        "sector_sentiment": round(avg_sentiment, 4),
        "sector_label":     sector_label,
        "total_positive":   total_pos,
        "total_negative":   total_neg,
        "symbol_results":   results,
    }

@app.get("/market/watchlist/{market}")
def market_watchlist(
    market: str,
    uid: Optional[str] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """Piyasa için varsayılan izleme listesi döndür."""
    from core.market_config import get_default_watchlist, get_symbols_for_market, MARKETS
    market = market.upper()
    if market not in MARKETS:
        raise HTTPException(status_code=400, detail=f"Geçerli piyasalar: {list(MARKETS.keys())}")
    return {
        "market":    market,
        "info":      MARKETS[market],
        "watchlist": get_default_watchlist(market),
        "symbols":   get_symbols_for_market(market),
    }

@app.get("/market/list")
def market_list() -> Dict[str, Any]:
    """Desteklenen piyasaları listele."""
    from core.market_config import MARKETS
    return {"markets": MARKETS}

# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Sector Intelligence Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/sectors/overview")
@limiter.limit("6/minute")
def sectors_overview(
    request: Request,
    market: str = "US",   # TR | US
    uid: Optional[str] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """
    Piyasadaki tüm sektörleri fırsat skoruna göre sıralı döndür.
    Kullanıcıya hangi sektörde ilerleyeceğini söyler.
    """
    market = market.upper()
    if market not in ("TR", "US"):
        raise HTTPException(status_code=400, detail="market: TR veya US olmalı")
    results = get_sector_overview(market=market, use_cache=True)
    return {
        "market":  market,
        "sectors": sector_overview_to_dict(results),
        "top_opportunity": {
            "sector":    results[0].sector   if results else None,
            "name_tr":   results[0].name_tr  if results else None,
            "score":     results[0].opportunity_score if results else None,
            "trend":     results[0].trend    if results else None,
            "advice":    results[0].advice   if results else None,
        } if results else None,
    }


@app.get("/sectors/{sector_key}")
@limiter.limit("10/minute")
def sector_detail(
    request: Request,
    sector_key: str,
    market: str = "US",
    uid: Optional[str] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """
    Belirli bir sektörün detaylı analizi — tüm semboller + fırsat tavsiyesi.
    """
    sector_key = sector_key.upper()
    market     = market.upper()
    if sector_key not in SECTOR_DEFINITIONS:
        raise HTTPException(
            status_code=404,
            detail=f"Bilinmeyen sektör. Geçerliler: {list(SECTOR_DEFINITIONS.keys())}"
        )
    result = analyze_sector(sector_key, market=market, use_cache=True)
    return sector_detail_to_dict(result)


@app.get("/sectors/list/all")
def sectors_list() -> Dict[str, Any]:
    """Tanımlı tüm sektörlerin listesini döndür."""
    return {
        "sectors": [
            {
                "key":         k,
                "name_tr":     v["name_tr"],
                "icon":        v.get("icon", "📊"),
                "description": v.get("description", ""),
                "risk":        v.get("risk", "MEDIUM"),
                "has_tr":      bool(v.get("tr_symbols")),
                "has_us":      bool(v.get("us_symbols")),
            }
            for k, v in SECTOR_DEFINITIONS.items()
        ]
    }

@app.post("/user/preferences")
@limiter.limit("30/minute")
def save_user_preferences(
    request: Request,
    body: Dict[str, Any],
    uid: Optional[str] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """
    Kullanıcı piyasa tercihini Firebase'e kaydet.
    Body: {"market": "TR", "uid": "..."}
    """
    user_uid = uid or body.get("uid")
    if not user_uid:
        raise HTTPException(status_code=401, detail="UID gerekli")
    market = body.get("market", "US").upper()
    from core.market_config import MARKETS
    if market not in MARKETS:
        raise HTTPException(status_code=400, detail=f"Geçersiz piyasa: {market}")
    try:
        from firebase_admin import firestore
        db = firestore.client()
        db.collection("users").document(user_uid).set(
            {"preferences": {"market": market, "updatedAt": firestore.SERVER_TIMESTAMP}},
            merge=True,
        )
        return {"status": "ok", "market": market}
    except Exception as e:
        logger.warning(f"Firebase preferences yazılamadı: {e}")
        return {"status": "ok", "market": market, "warning": "Firebase kayıt başarısız"}

# ── Session ────────────────────────────────────────────────────────────────────

@app.get("/session/info", response_model=SessionInfo)
@limiter.limit("60/minute")
def session_info(request: Request) -> SessionInfo:
    data = compute_session_score(
        rsi=50, macd=0, macd_signal_val=0,
        macd_hist=0, volume_ratio=1.0, base_score=50,
    )
    return SessionInfo(**data)

@app.get("/session/all")
def all_sessions() -> List[Dict[str, Any]]:
    return [
        {
            "code": s.code, "name": s.name,
            "start": s.start.strftime("%H:%M"),
            "end": s.end.strftime("%H:%M"),
            "volatility_mult": s.volatility_mult,
            "description": s.description,
            "currencies": s.currencies,
        }
        for s in SESSIONS
    ]

@app.post("/session/analyze", response_model=SessionInfo)
@limiter.limit("30/minute")
def session_analyze(request: Request, body: AnalysisRequest,
                    uid: Optional[str] = Depends(verify_firebase_token)) -> SessionInfo:
    result = analyze(symbol=body.symbol, potential_price=body.potential_price,
                     asset_type=body.asset_type)
    if result is None:
        raise HTTPException(status_code=404, detail=f"{body.symbol} icin veri bulunamadi.")
    ind = result.indicators
    data = compute_session_score(
        rsi=ind.rsi, macd=ind.macd, macd_signal_val=ind.macd_signal,
        macd_hist=ind.macd_histogram, volume_ratio=ind.volume_ratio,
        base_score=result.score,
    )
    return SessionInfo(**data)

# ── Price ──────────────────────────────────────────────────────────────────────

@app.get("/price/{symbol}")
@limiter.limit("60/minute")
def get_current_price(request: Request, symbol: str) -> Dict[str, Any]:
    hist = fetch_history(symbol.upper(), period="5d")
    if hist is None or hist.empty:
        raise HTTPException(status_code=404, detail=f"{symbol} fiyati bulunamadi.")
    current = float(hist["Close"].iloc[-1])
    prev    = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
    change_pct = ((current - prev) / prev) * 100 if prev > 0 else 0.0
    return {
        "symbol": symbol.upper(),
        "price": round(current, 4),
        "change_pct": round(change_pct, 2),
        "timestamp": hist.index[-1].isoformat(),
    }

# ── Analyze ────────────────────────────────────────────────────────────────────

@app.post("/analyze", response_model=AnalysisResult)
@limiter.limit("30/minute")
def analyze_symbol(request: Request, body: AnalysisRequest,
                   uid: Optional[str] = Depends(verify_firebase_token)) -> AnalysisResult:
    result = analyze(symbol=body.symbol, potential_price=body.potential_price,
                     asset_type=body.asset_type)
    if result is None:
        raise HTTPException(status_code=404, detail=f"{body.symbol} icin veri bulunamadi.")
    rec_data = compute_recommendation(
        score=result.score, ml_confidence=result.ml_confidence,
        monte_carlo=None, risk_level=result.risk_level,
    )
    return result.model_copy(update={"recommendation": RecommendationResult(**rec_data)})

@app.post("/analyze/enhanced", response_model=AnalysisResult)
@limiter.limit("10/minute")
def analyze_enhanced(request: Request, body: EnhancedAnalysisRequest,
                     uid: Optional[str] = Depends(verify_firebase_token)) -> AnalysisResult:

    # Trader check (Basitleştirilmiş mantık - Firebase'den çekilebilir)
    is_trader: bool = False
    if uid:
        try:
            from firebase_admin import firestore
            db = firestore.client()
            user = db.collection("users").document(uid).get().to_dict()
            if user and user.get("subscriptionLevel") == "TRADE":
                is_trader = True
        except: pass

    result = analyze(symbol=body.symbol, potential_price=body.potential_price,
                     asset_type=body.asset_type)
    if result is None:
        raise HTTPException(status_code=404, detail=f"{body.symbol} icin veri bulunamadi.")
    
    mc_data: Optional[Dict[str, Any]] = None
    if body.run_monte_carlo or is_trader:
        # Trader'lar için simülasyon sayısını 2 katına çıkarıyoruz
        n_sims = body.n_simulations * 2 if is_trader else body.n_simulations
        hist = fetch_history(body.symbol.upper(), period="1y")
        if hist is not None and not hist.empty:
            mc_data = run_monte_carlo(
                prices=hist["Close"],
                n_simulations=n_sims,
                n_days=body.n_days,
            )
    return _enrich_result(result, mc_data)

# ── Quant Research Platform ─────────────────────────────────────────────────────

@app.post("/quant/analyze", response_model=PipelineResponse)
@limiter.limit("10/minute")
async def quant_analyze(
    request: Request, body: QuantAnalysisRequest,
    uid: Optional[str] = Depends(verify_firebase_token),
) -> PipelineResponse:
    """Runs the new Quant Research Platform pipeline (Feature Store ->
    Technical/Fundamental/News Engines -> Decision Engine ->
    Explanation Engine -> Learning Tracker) for one symbol. Separate
    from the legacy /analyze endpoint - see that endpoint's docstring
    for the backward-compatibility guarantee this one does not carry."""
    if _pipeline_service is None:
        raise HTTPException(status_code=503, detail="Quant pipeline henüz hazır değil.")
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(_executor, _pipeline_service.run, body.symbol.upper())
    except Exception as e:
        logger.error(f"Quant pipeline hatasi ({body.symbol}): {e}")
        raise HTTPException(status_code=500, detail=f"{body.symbol} icin analiz calistirilamadi.")

@app.post("/quant/predict", response_model=MLPredictionResult)
@limiter.limit("10/minute")
async def quant_predict(
    request: Request, body: MLPredictionRequest,
    uid: Optional[str] = Depends(verify_firebase_token),
) -> MLPredictionResult:
    """Direct prediction from a single trained ML model (Model Serving
    Platform), bypassing Decision Engine aggregation - separate,
    additive endpoint; `/quant/analyze` already folds every ACTIVE
    model into its own aggregated decision (see `pipeline.service.
    PipelineService.run`), so this one exists purely for callers that
    want a specific model's raw vote and metadata instead. Backward
    compatible with every existing endpoint - nothing here changes any
    other route's request or response shape."""
    if _pipeline_service is None:
        raise HTTPException(status_code=503, detail="Quant pipeline henüz hazır değil.")
    try:
        return await _pipeline_service.model_serving.predict_async(
            body.symbol.upper(), body.label_name, body.horizon_days,
        )
    except NoActiveModelError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ModelServingError as e:
        logger.error(f"Model serving hatasi ({body.symbol}): {e}")
        raise HTTPException(status_code=500, detail=f"{body.symbol} icin ML tahmini yapilamadi.")

@app.get("/quant/model-serving/health", response_model=ServingHealthReport)
def quant_model_serving_health() -> ServingHealthReport:
    """Structured Model Serving health: per-model load status,
    inference latency, cache connectivity, loading failure count."""
    if _pipeline_service is None:
        raise HTTPException(status_code=503, detail="Quant pipeline henüz hazır değil.")
    return _pipeline_service.model_serving.health_report()

# ── Portfolio ──────────────────────────────────────────────────────────────────

@app.post("/portfolio/optimize", response_model=PortfolioOptResult)
@limiter.limit("5/minute")
def portfolio_optimize(request: Request, body: PortfolioOptRequest,
                       uid: Optional[str] = Depends(verify_firebase_token)) -> PortfolioOptResult:
    if len(body.symbols) < 2:
        raise HTTPException(status_code=400, detail="En az 2 sembol gereklidir.")
    if len(body.symbols) > 20:
        raise HTTPException(status_code=400, detail="En fazla 20 sembol desteklenmektedir.")
    price_data: Dict[str, Any] = {}
    for sym in body.symbols:
        hist = fetch_history(sym.upper(), period="1y")
        if hist is not None and not hist.empty:
            price_data[sym.upper()] = hist["Close"]
    if len(price_data) < 2:
        raise HTTPException(status_code=404, detail="Yeterli fiyat verisi bulunamadi.")
    result = optimize_portfolio(price_data, risk_tolerance=body.risk_tolerance)
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return PortfolioOptResult(**result)

# ── Portfolio Intelligence Platform ─────────────────────────────────────────────
# Additive, `/portfolios` (plural) - a structurally distinct path from
# the legacy `/portfolio/optimize` above, so there is no routing
# ambiguity and the legacy endpoint's contract is completely untouched.

@app.post("/portfolios", response_model=Portfolio)
@limiter.limit("10/minute")
async def create_portfolio(
    request: Request, body: CreatePortfolioRequest, user: UsersUser = Depends(_get_current_user),
) -> Portfolio:
    _require_portfolio_service()
    try:
        return await _run_in_executor(_portfolio_service.create_portfolio, user.email, body.name, body.base_currency)
    except PortfolioError as e:
        raise _map_portfolio_error(e)

@app.get("/portfolios", response_model=List[Portfolio])
@limiter.limit("30/minute")
async def list_portfolios(request: Request, user: UsersUser = Depends(_get_current_user)) -> List[Portfolio]:
    _require_portfolio_service()
    try:
        return await _run_in_executor(_portfolio_service.list_portfolios, user.email)
    except PortfolioError as e:
        raise _map_portfolio_error(e)

async def _get_authorized_portfolio(portfolio_id: int, user: UsersUser) -> Portfolio:
    try:
        portfolio_obj = await _run_in_executor(_portfolio_service.get_portfolio, portfolio_id)
    except PortfolioError as e:
        raise _map_portfolio_error(e)
    _authorize_portfolio_access(portfolio_obj, user)
    return portfolio_obj

@app.post("/portfolios/{portfolio_id}/deposit", response_model=Transaction)
@limiter.limit("20/minute")
async def portfolio_deposit(
    request: Request, portfolio_id: int, body: DepositRequest, user: UsersUser = Depends(_get_current_user),
) -> Transaction:
    _require_portfolio_service()
    await _get_authorized_portfolio(portfolio_id, user)
    try:
        return await _run_in_executor(
            _portfolio_service.deposit, portfolio_id, body.amount, body.currency, None, body.notes,
        )
    except PortfolioError as e:
        raise _map_portfolio_error(e)

@app.post("/portfolios/{portfolio_id}/withdraw", response_model=Transaction)
@limiter.limit("20/minute")
async def portfolio_withdraw(
    request: Request, portfolio_id: int, body: WithdrawRequest, user: UsersUser = Depends(_get_current_user),
) -> Transaction:
    _require_portfolio_service()
    await _get_authorized_portfolio(portfolio_id, user)
    try:
        return await _run_in_executor(
            _portfolio_service.withdraw, portfolio_id, body.amount, body.currency, None, body.notes,
        )
    except PortfolioError as e:
        raise _map_portfolio_error(e)

@app.post("/portfolios/{portfolio_id}/buy", response_model=Transaction)
@limiter.limit("20/minute")
async def portfolio_buy(
    request: Request, portfolio_id: int, body: TradeRequest, user: UsersUser = Depends(_get_current_user),
) -> Transaction:
    _require_portfolio_service()
    await _get_authorized_portfolio(portfolio_id, user)
    try:
        return await _run_in_executor(
            _portfolio_service.buy, portfolio_id, body.symbol, body.quantity, body.price, body.fee, body.tax,
            None, None, body.notes,
        )
    except PortfolioError as e:
        raise _map_portfolio_error(e)

@app.post("/portfolios/{portfolio_id}/sell", response_model=Transaction)
@limiter.limit("20/minute")
async def portfolio_sell(
    request: Request, portfolio_id: int, body: TradeRequest, user: UsersUser = Depends(_get_current_user),
) -> Transaction:
    _require_portfolio_service()
    await _get_authorized_portfolio(portfolio_id, user)
    try:
        return await _run_in_executor(
            _portfolio_service.sell, portfolio_id, body.symbol, body.quantity, body.price, body.fee, body.tax,
            None, None, body.notes,
        )
    except PortfolioError as e:
        raise _map_portfolio_error(e)

@app.post("/portfolios/{portfolio_id}/dividend", response_model=Transaction)
@limiter.limit("20/minute")
async def portfolio_dividend(
    request: Request, portfolio_id: int, body: DividendRequest, user: UsersUser = Depends(_get_current_user),
) -> Transaction:
    _require_portfolio_service()
    await _get_authorized_portfolio(portfolio_id, user)
    try:
        return await _run_in_executor(
            _portfolio_service.record_dividend, portfolio_id, body.symbol, body.amount, body.tax, None, None,
            body.notes,
        )
    except PortfolioError as e:
        raise _map_portfolio_error(e)

@app.get("/portfolios/{portfolio_id}/positions", response_model=List[PositionAnalytics])
@limiter.limit("30/minute")
async def portfolio_positions(
    request: Request, portfolio_id: int, user: UsersUser = Depends(_get_current_user),
) -> List[PositionAnalytics]:
    _require_portfolio_service()
    await _get_authorized_portfolio(portfolio_id, user)
    try:
        return await _run_in_executor(_portfolio_analytics.analyze_positions, portfolio_id)
    except PortfolioError as e:
        raise _map_portfolio_error(e)

@app.get("/portfolios/{portfolio_id}/risk", response_model=RiskAnalytics)
@limiter.limit("15/minute")
async def portfolio_risk(
    request: Request, portfolio_id: int, user: UsersUser = Depends(_get_current_user),
) -> RiskAnalytics:
    _require_portfolio_service()
    await _get_authorized_portfolio(portfolio_id, user)
    try:
        return await _run_in_executor(_portfolio_risk.analyze, portfolio_id, None)
    except PortfolioError as e:
        raise _map_portfolio_error(e)

@app.post("/portfolios/{portfolio_id}/optimize", response_model=OptimizationResult)
@limiter.limit("10/minute")
async def portfolio_optimize_holdings(
    request: Request, portfolio_id: int, body: OptimizeRequest, user: UsersUser = Depends(_get_current_user),
) -> OptimizationResult:
    """Portfolio-aware optimization over a caller-supplied candidate
    symbol list - distinct from the legacy, portfolio-less
    `/portfolio/optimize` above. `portfolio_id` is only used for
    authorization here; the optimization itself is symbol-based."""
    _require_portfolio_service()
    await _get_authorized_portfolio(portfolio_id, user)
    try:
        return await _run_in_executor(
            _portfolio_optimization.optimize, body.symbols, body.strategy, body.risk_tolerance,
            body.use_prediction_views,
        )
    except PortfolioError as e:
        raise _map_portfolio_error(e)

@app.post("/portfolios/{portfolio_id}/rebalance", response_model=RebalancePlan)
@limiter.limit("15/minute")
async def portfolio_rebalance(
    request: Request, portfolio_id: int, body: RebalanceRequest, user: UsersUser = Depends(_get_current_user),
) -> RebalancePlan:
    _require_portfolio_service()
    await _get_authorized_portfolio(portfolio_id, user)
    try:
        return await _run_in_executor(
            _portfolio_rebalancing.build_plan, portfolio_id, body.target_weights_pct, body.trigger,
            body.threshold_pct, None, None,
        )
    except PortfolioError as e:
        raise _map_portfolio_error(e)

@app.post("/portfolios/{portfolio_id}/scenario", response_model=ScenarioResult)
@limiter.limit("15/minute")
async def portfolio_scenario(
    request: Request, portfolio_id: int, body: ScenarioRequest, user: UsersUser = Depends(_get_current_user),
) -> ScenarioResult:
    _require_portfolio_service()
    await _get_authorized_portfolio(portfolio_id, user)
    try:
        if body.scenario_type == ScenarioType.MARKET_CRASH:
            return await _run_in_executor(
                _portfolio_scenarios.market_crash, portfolio_id, body.drop_pct or 30.0, None,
            )
        if body.scenario_type == ScenarioType.VOLATILITY_SHOCK:
            return await _run_in_executor(
                _portfolio_scenarios.volatility_shock, portfolio_id, body.volatility_multiplier or 2.0, None,
            )
        if body.scenario_type == ScenarioType.INTEREST_RATE_SHOCK:
            return await _run_in_executor(
                _portfolio_scenarios.interest_rate_shock, portfolio_id, body.rate_change_bps or 100.0, None,
            )
        if body.scenario_type == ScenarioType.MONTE_CARLO:
            return await _run_in_executor(
                _portfolio_scenarios.monte_carlo_simulation, portfolio_id, body.n_simulations, body.horizon_days, None,
            )
        raise HTTPException(status_code=400, detail=f"Desteklenmeyen senaryo tipi: {body.scenario_type.value}")
    except PortfolioError as e:
        raise _map_portfolio_error(e)

@app.post("/portfolios/{portfolio_id}/recommendations", response_model=List[Recommendation])
@limiter.limit("15/minute")
async def portfolio_recommendations(
    request: Request, portfolio_id: int, body: RecommendationsRequest,
    user: UsersUser = Depends(_get_current_user),
) -> List[Recommendation]:
    _require_portfolio_service()
    await _get_authorized_portfolio(portfolio_id, user)
    try:
        return await _run_in_executor(
            _portfolio_recommendations.generate, portfolio_id, body.target_weights_pct, None, None,
        )
    except PortfolioError as e:
        raise _map_portfolio_error(e)

@app.get("/portfolios/{portfolio_id}/dashboard", response_model=PortfolioDashboard)
@limiter.limit("15/minute")
async def portfolio_dashboard(
    request: Request, portfolio_id: int, user: UsersUser = Depends(_get_current_user),
) -> PortfolioDashboard:
    _require_portfolio_service()
    await _get_authorized_portfolio(portfolio_id, user)
    try:
        return await _run_in_executor(_portfolio_dashboard.build, portfolio_id, None)
    except PortfolioError as e:
        raise _map_portfolio_error(e)

@app.get("/portfolios/{portfolio_id}/history", response_model=List[Transaction])
@limiter.limit("30/minute")
async def portfolio_transaction_history(
    request: Request, portfolio_id: int, symbol: Optional[str] = None,
    user: UsersUser = Depends(_get_current_user),
) -> List[Transaction]:
    _require_portfolio_service()
    await _get_authorized_portfolio(portfolio_id, user)
    try:
        return await _run_in_executor(_portfolio_service.list_transactions, portfolio_id, symbol)
    except PortfolioError as e:
        raise _map_portfolio_error(e)

@app.post("/portfolios/{portfolio_id}/snapshot", response_model=PortfolioSnapshot)
@limiter.limit("10/minute")
async def portfolio_take_snapshot(
    request: Request, portfolio_id: int, user: UsersUser = Depends(_get_current_user),
) -> PortfolioSnapshot:
    _require_portfolio_service()
    await _get_authorized_portfolio(portfolio_id, user)
    try:
        return await _run_in_executor(_portfolio_service.take_snapshot, portfolio_id)
    except PortfolioError as e:
        raise _map_portfolio_error(e)

# ── Watchlist & Alert Platform ───────────────────────────────────────────────────
# Previously a fully-built, fully-tested subsystem with zero HTTP surface -
# `watchlist.WatchlistService`/`AlertScheduler` existed and worked, but
# nothing in main.py ever let a caller create a watchlist or an alert, and
# the scheduler that evaluates alerts was never invoked (see
# alert_scan_loop above). Same auth/ownership convention as the Portfolio
# Intelligence Platform (Depends(_get_current_user), owner is always the
# authenticated caller's email, ownership checked on every access).

def _require_watchlist_service() -> None:
    if _users_watchlist_bridge is None:
        raise HTTPException(status_code=503, detail="Watchlist servisi henuz hazir degil.")


def _map_watchlist_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (WatchlistNotFoundError, WatchlistItemNotFoundError, AlertNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (InvalidAlertError, InsufficientAlertDataError)):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, WatchlistError):
        return HTTPException(status_code=500, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


async def _get_authorized_watchlist(watchlist_id: int, user: UsersUser) -> Watchlist:
    try:
        watchlist_obj = await _run_in_executor(_users_watchlist_bridge.get_watchlist, watchlist_id)
    except WatchlistError as e:
        raise _map_watchlist_error(e)
    if watchlist_obj.owner != user.email:
        raise HTTPException(status_code=403, detail="Bu izleme listesine erisim izniniz yok.")
    return watchlist_obj


async def _get_authorized_alert(alert_id: int, user: UsersUser) -> Alert:
    try:
        alert_obj = await _run_in_executor(_users_watchlist_bridge.get_alert, alert_id)
    except WatchlistError as e:
        raise _map_watchlist_error(e)
    if alert_obj.owner != user.email:
        raise HTTPException(status_code=403, detail="Bu alerte erisim izniniz yok.")
    return alert_obj


@app.post("/watchlists", response_model=Watchlist)
@limiter.limit("10/minute")
async def create_watchlist(
    request: Request, body: CreateWatchlistRequest, user: UsersUser = Depends(_get_current_user),
) -> Watchlist:
    _require_watchlist_service()
    try:
        return await _run_in_executor(_users_watchlist_bridge.create_watchlist, user.email, body.name)
    except WatchlistError as e:
        raise _map_watchlist_error(e)

@app.get("/watchlists", response_model=List[Watchlist])
@limiter.limit("30/minute")
async def list_watchlists(request: Request, user: UsersUser = Depends(_get_current_user)) -> List[Watchlist]:
    _require_watchlist_service()
    try:
        return await _run_in_executor(_users_watchlist_bridge.list_watchlists, user.email)
    except WatchlistError as e:
        raise _map_watchlist_error(e)

@app.get("/watchlists/{watchlist_id}", response_model=Watchlist)
@limiter.limit("30/minute")
async def get_watchlist(
    request: Request, watchlist_id: int, user: UsersUser = Depends(_get_current_user),
) -> Watchlist:
    _require_watchlist_service()
    return await _get_authorized_watchlist(watchlist_id, user)

@app.delete("/watchlists/{watchlist_id}")
@limiter.limit("10/minute")
async def delete_watchlist(
    request: Request, watchlist_id: int, user: UsersUser = Depends(_get_current_user),
) -> Dict[str, str]:
    _require_watchlist_service()
    await _get_authorized_watchlist(watchlist_id, user)
    try:
        await _run_in_executor(_users_watchlist_bridge.delete_watchlist, watchlist_id)
    except WatchlistError as e:
        raise _map_watchlist_error(e)
    return {"status": "deleted"}

@app.get("/watchlists/{watchlist_id}/items", response_model=List[WatchlistItem])
@limiter.limit("30/minute")
async def list_watchlist_items(
    request: Request, watchlist_id: int, user: UsersUser = Depends(_get_current_user),
) -> List[WatchlistItem]:
    _require_watchlist_service()
    await _get_authorized_watchlist(watchlist_id, user)
    try:
        return await _run_in_executor(_users_watchlist_bridge.list_items, watchlist_id)
    except WatchlistError as e:
        raise _map_watchlist_error(e)

@app.post("/watchlists/{watchlist_id}/items", response_model=WatchlistItem)
@limiter.limit("20/minute")
async def add_watchlist_item(
    request: Request, watchlist_id: int, body: AddWatchlistItemRequest,
    user: UsersUser = Depends(_get_current_user),
) -> WatchlistItem:
    _require_watchlist_service()
    await _get_authorized_watchlist(watchlist_id, user)
    try:
        return await _run_in_executor(
            _users_watchlist_bridge.add_symbol, watchlist_id, body.symbol, body.is_favorite, body.folder,
            body.tags, body.notes,
        )
    except WatchlistError as e:
        raise _map_watchlist_error(e)

@app.delete("/watchlists/{watchlist_id}/items/{symbol}")
@limiter.limit("20/minute")
async def remove_watchlist_item(
    request: Request, watchlist_id: int, symbol: str, user: UsersUser = Depends(_get_current_user),
) -> Dict[str, str]:
    _require_watchlist_service()
    await _get_authorized_watchlist(watchlist_id, user)
    try:
        await _run_in_executor(_users_watchlist_bridge.remove_symbol, watchlist_id, symbol)
    except WatchlistError as e:
        raise _map_watchlist_error(e)
    return {"status": "deleted"}

@app.post("/alerts", response_model=Alert)
@limiter.limit("15/minute")
async def create_alert(
    request: Request, body: CreateAlertRequest, user: UsersUser = Depends(_get_current_user),
) -> Alert:
    _require_watchlist_service()
    if body.watchlist_id is not None:
        await _get_authorized_watchlist(body.watchlist_id, user)
    try:
        return await _run_in_executor(
            _users_watchlist_bridge.create_alert, user.email, body.category, body.alert_type, body.parameters,
            body.watchlist_id, body.symbol, body.portfolio_id, body.cooldown_minutes,
        )
    except WatchlistError as e:
        raise _map_watchlist_error(e)

@app.get("/alerts", response_model=List[Alert])
@limiter.limit("30/minute")
async def list_alerts(
    request: Request, watchlist_id: Optional[int] = None, user: UsersUser = Depends(_get_current_user),
) -> List[Alert]:
    _require_watchlist_service()
    try:
        return await _run_in_executor(_users_watchlist_bridge.list_alerts, user.email, watchlist_id)
    except WatchlistError as e:
        raise _map_watchlist_error(e)

@app.get("/alerts/{alert_id}", response_model=Alert)
@limiter.limit("30/minute")
async def get_alert(request: Request, alert_id: int, user: UsersUser = Depends(_get_current_user)) -> Alert:
    _require_watchlist_service()
    return await _get_authorized_alert(alert_id, user)

@app.patch("/alerts/{alert_id}/enabled", response_model=Alert)
@limiter.limit("20/minute")
async def set_alert_enabled(
    request: Request, alert_id: int, body: SetAlertEnabledRequest, user: UsersUser = Depends(_get_current_user),
) -> Alert:
    _require_watchlist_service()
    await _get_authorized_alert(alert_id, user)
    try:
        return await _run_in_executor(_users_watchlist_bridge.set_alert_enabled, alert_id, body.enabled)
    except WatchlistError as e:
        raise _map_watchlist_error(e)

@app.delete("/alerts/{alert_id}")
@limiter.limit("20/minute")
async def delete_alert(request: Request, alert_id: int, user: UsersUser = Depends(_get_current_user)) -> Dict[str, str]:
    _require_watchlist_service()
    await _get_authorized_alert(alert_id, user)
    try:
        await _run_in_executor(_users_watchlist_bridge.delete_alert, alert_id)
    except WatchlistError as e:
        raise _map_watchlist_error(e)
    return {"status": "deleted"}

@app.post("/alerts/scan", response_model=ScanReport)
@limiter.limit("5/minute")
async def scan_my_alerts(request: Request, user: UsersUser = Depends(_get_current_user)) -> ScanReport:
    """On-demand scan of just the caller's own alerts - the same
    AlertScheduler.run_scan the periodic alert_scan_loop calls for
    everyone, scoped to owner=user.email so a caller can't trigger
    (or learn about) anyone else's alerts."""
    if _watchlist_scheduler is None:
        raise HTTPException(status_code=503, detail="Alert scheduler henuz hazir degil.")
    return await _run_in_executor(_watchlist_scheduler.run_scan, user.email)

# ── Scan (parallel) ────────────────────────────────────────────────────────────

@app.post("/scan", response_model=ScanResult)
@limiter.limit("5/minute")
async def scan_symbols(request: Request, body: ScanRequest,
                       uid: Optional[str] = Depends(verify_firebase_token)) -> ScanResult:
    results = await _parallel_scan(body.symbols, body.asset_type)
    return categorize(results)

@app.get("/scan/bist", response_model=ScanResult)
@limiter.limit("5/minute")
async def scan_bist(request: Request,
                    uid: Optional[str] = Depends(verify_firebase_token)) -> ScanResult:
    results = await _parallel_scan(BIST_SYMBOLS, "stock")
    return categorize(results)

@app.get("/scan/crypto", response_model=ScanResult)
@limiter.limit("5/minute")
async def scan_crypto(request: Request,
                      uid: Optional[str] = Depends(verify_firebase_token)) -> ScanResult:
    results = await _parallel_scan(CRYPTO_SYMBOLS, "crypto")
    return categorize(results)

# ── Symbols ────────────────────────────────────────────────────────────────────

@app.get("/symbols/bist",   response_model=List[str])
def get_bist_symbols() -> List[str]:   return BIST_SYMBOLS

@app.get("/symbols/crypto", response_model=List[str])
def get_crypto_symbols() -> List[str]: return CRYPTO_SYMBOLS

# ── Chart ──────────────────────────────────────────────────────────────────────

@app.get("/chart/{symbol}", response_model=ChartResponse)
@limiter.limit("30/minute")
def get_chart(
    request: Request,
    symbol: str,
    period: str = Query(default="3mo", pattern="^(1mo|3mo|6mo|1y)$"),
) -> ChartResponse:
    import numpy as np
    hist = fetch_history(symbol.upper(), period=period)
    if hist is None or hist.empty:
        raise HTTPException(status_code=404, detail=f"{symbol} icin grafik verisi bulunamadi.")

    prices = hist["Close"]
    rsi_series = None
    if len(prices) >= 15:
        delta    = prices.diff()
        gain     = delta.where(delta > 0, 0.0)
        loss     = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(com=13, min_periods=14).mean()
        avg_loss = loss.ewm(com=13, min_periods=14).mean()
        rs       = avg_gain / avg_loss.replace(0, np.nan)
        rsi_series = 100 - (100 / (1 + rs))

    points: List[ChartPoint] = []
    for i, (idx, row) in enumerate(hist.iterrows()):
        rsi_val = None
        if rsi_series is not None:
            v = rsi_series.iloc[i]
            if v == v:  # NaN kontrolü
                rsi_val = float(v)
        points.append(ChartPoint(
            date=idx.strftime("%Y-%m-%d"),
            close=round(float(row["Close"]), 4),
            volume=float(row["Volume"]),
            rsi=round(rsi_val, 1) if rsi_val is not None else None,
        ))

    first_close = float(hist["Close"].iloc[0])
    last_close  = float(hist["Close"].iloc[-1])
    change_pct  = ((last_close - first_close) / first_close) * 100 if first_close > 0 else 0.0
    return ChartResponse(
        symbol=symbol.upper(), period=period, points=points,
        change_pct=round(change_pct, 2),
        high=round(float(hist["High"].max()), 4),
        low=round(float(hist["Low"].min()),  4),
    )

# ─────────────────────────────────────────────────────────────────────────────
# USER & ORGANIZATION PLATFORM ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

# ── Authentication ───────────────────────────────────────────────────────────

@app.post("/auth/register", response_model=UserResponse)
@limiter.limit("20/minute")
def auth_register(request: Request, body: RegisterRequest) -> UserResponse:
    _require_users_service()
    try:
        return UserResponse.model_validate(
            _users_service.register(body.email, body.password, body.display_name)
        )
    except UserPlatformError as e:
        raise _map_users_error(e)

@app.post("/auth/login", response_model=TokenPairResponse)
@limiter.limit("30/minute")
def auth_login(request: Request, body: LoginRequest) -> TokenPairResponse:
    _require_users_service()
    try:
        tokens = _users_authentication.login(body.email, body.password, _device_from_request(request))
        return TokenPairResponse.model_validate(tokens)
    except UserPlatformError as e:
        raise _map_users_error(e)

@app.post("/auth/refresh", response_model=TokenPairResponse)
@limiter.limit("60/minute")
def auth_refresh(request: Request, body: RefreshRequest) -> TokenPairResponse:
    _require_users_service()
    try:
        tokens = _users_authentication.refresh(body.refresh_token, _device_from_request(request))
        return TokenPairResponse.model_validate(tokens)
    except UserPlatformError as e:
        raise _map_users_error(e)

@app.post("/auth/logout")
@limiter.limit("60/minute")
def auth_logout(request: Request, body: LogoutRequest) -> Dict[str, str]:
    _require_users_service()
    _users_authentication.logout(body.refresh_token)
    return {"status": "ok"}

@app.post("/auth/password-reset/request")
@limiter.limit("5/minute")
def auth_password_reset_request(request: Request, body: PasswordResetRequestSchema) -> Dict[str, str]:
    _require_users_service()
    _users_authentication.request_password_reset(body.email)
    return {"status": "ok"}

@app.post("/auth/password-reset/confirm")
@limiter.limit("10/minute")
def auth_password_reset_confirm(request: Request, body: PasswordResetConfirmRequest) -> Dict[str, str]:
    _require_users_service()
    try:
        _users_authentication.reset_password(body.token, body.new_password)
        return {"status": "ok"}
    except UserPlatformError as e:
        raise _map_users_error(e)

# ── Current user / profile ────────────────────────────────────────────────────

@app.get("/users/me", response_model=UserResponse)
def users_me(user: UsersUser = Depends(_get_current_user)) -> UserResponse:
    return UserResponse.model_validate(user)

@app.patch("/users/me", response_model=UserResponse)
def users_update_me(body: UpdateProfileRequest, user: UsersUser = Depends(_get_current_user)) -> UserResponse:
    try:
        return UserResponse.model_validate(_users_service.update_profile(user.id, body.display_name))
    except UserPlatformError as e:
        raise _map_users_error(e)

@app.get("/users/me/login-history", response_model=List[LoginHistoryEntryResponse])
def users_login_history(user: UsersUser = Depends(_get_current_user)) -> List[LoginHistoryEntryResponse]:
    return [LoginHistoryEntryResponse.model_validate(entry) for entry in _users_repository.list_login_history(user.id)]

@app.get("/users/me/sessions", response_model=List[SessionResponse])
def users_sessions(user: UsersUser = Depends(_get_current_user)) -> List[SessionResponse]:
    return [SessionResponse.model_validate(session) for session in _users_sessions.list_active_sessions(user.id)]

# ── Preferences ────────────────────────────────────────────────────────────────

@app.get("/users/me/preferences", response_model=PreferencesResponse)
def users_get_preferences(user: UsersUser = Depends(_get_current_user)) -> PreferencesResponse:
    try:
        return PreferencesResponse.model_validate(_users_preferences.get_preferences(user.id))
    except UserPlatformError as e:
        raise _map_users_error(e)

@app.put("/users/me/preferences", response_model=PreferencesResponse)
def users_update_preferences(
    body: UpdatePreferencesRequest, user: UsersUser = Depends(_get_current_user),
) -> PreferencesResponse:
    try:
        preferences = _users_preferences.update_preferences(
            user.id, theme=body.theme, language=body.language,
            notification_settings=body.notification_settings, dashboard_layout=body.dashboard_layout,
            default_portfolio_id=body.default_portfolio_id, default_watchlist_id=body.default_watchlist_id,
        )
        return PreferencesResponse.model_validate(preferences)
    except UserPlatformError as e:
        raise _map_users_error(e)

# ── API keys ─────────────────────────────────────────────────────────────────

@app.post("/users/me/api-keys", response_model=APIKeyCreatedResponse)
def users_create_api_key(body: CreateAPIKeyRequest, user: UsersUser = Depends(_get_current_user)) -> APIKeyCreatedResponse:
    try:
        api_key, raw_key = _users_api_keys.create_api_key(
            user.id, body.name, scope=body.scope, organization_id=body.organization_id,
            expires_in_seconds=body.expires_in_seconds,
        )
        return APIKeyCreatedResponse(api_key=APIKeyResponse.model_validate(api_key), key=raw_key)
    except UserPlatformError as e:
        raise _map_users_error(e)

@app.get("/users/me/api-keys", response_model=List[APIKeyResponse])
def users_list_api_keys(user: UsersUser = Depends(_get_current_user)) -> List[APIKeyResponse]:
    return [APIKeyResponse.model_validate(key) for key in _users_api_keys.list_api_keys(user.id)]

@app.post("/users/me/api-keys/{api_key_id}/rotate", response_model=APIKeyCreatedResponse)
def users_rotate_api_key(api_key_id: int, user: UsersUser = Depends(_get_current_user)) -> APIKeyCreatedResponse:
    try:
        api_key, raw_key = _users_api_keys.rotate_api_key(user.id, api_key_id)
        return APIKeyCreatedResponse(api_key=APIKeyResponse.model_validate(api_key), key=raw_key)
    except UserPlatformError as e:
        raise _map_users_error(e)

@app.delete("/users/me/api-keys/{api_key_id}")
def users_revoke_api_key(api_key_id: int, user: UsersUser = Depends(_get_current_user)) -> Dict[str, str]:
    try:
        _users_api_keys.revoke_api_key(user.id, api_key_id)
        return {"status": "ok"}
    except UserPlatformError as e:
        raise _map_users_error(e)

@app.get("/users/me/api-keys/{api_key_id}/usage", response_model=APIKeyUsageStatsResponse)
def users_api_key_usage(api_key_id: int, user: UsersUser = Depends(_get_current_user)) -> APIKeyUsageStatsResponse:
    try:
        api_key = _users_api_keys.get_api_key(api_key_id)
        if api_key.user_id != user.id:
            raise PermissionDeniedError(f"user {user.id} does not own API key {api_key_id}")
        return APIKeyUsageStatsResponse.model_validate(_users_api_keys.get_usage_stats(api_key_id))
    except UserPlatformError as e:
        raise _map_users_error(e)

# ── Organizations ──────────────────────────────────────────────────────────────

@app.post("/organizations", response_model=OrganizationResponse)
def organizations_create(body: CreateOrganizationRequest, user: UsersUser = Depends(_get_current_user)) -> OrganizationResponse:
    quotas = OrganizationQuotas(**body.quotas.model_dump()) if body.quotas else None
    try:
        return OrganizationResponse.model_validate(
            _users_organizations.create_organization(body.name, user.id, quotas=quotas)
        )
    except UserPlatformError as e:
        raise _map_users_error(e)

@app.get("/organizations", response_model=List[OrganizationResponse])
def organizations_list(user: UsersUser = Depends(_get_current_user)) -> List[OrganizationResponse]:
    return [OrganizationResponse.model_validate(org) for org in _users_organizations.list_organizations_for_user(user.id)]

@app.get("/organizations/{organization_id}", response_model=OrganizationResponse)
def organizations_get(organization_id: int, user: UsersUser = Depends(_get_current_user)) -> OrganizationResponse:
    try:
        _users_authorization.get_role(user.id, organization_id)
        return OrganizationResponse.model_validate(_users_organizations.get_organization(organization_id))
    except UserPlatformError as e:
        raise _map_users_error(e)

@app.patch("/organizations/{organization_id}", response_model=OrganizationResponse)
def organizations_update(
    organization_id: int, body: UpdateOrganizationRequest, user: UsersUser = Depends(_get_current_user),
) -> OrganizationResponse:
    quotas = OrganizationQuotas(**body.quotas.model_dump()) if body.quotas else None
    try:
        return OrganizationResponse.model_validate(
            _users_organizations.update_organization(organization_id, user.id, name=body.name, quotas=quotas)
        )
    except UserPlatformError as e:
        raise _map_users_error(e)

@app.delete("/organizations/{organization_id}")
def organizations_delete(organization_id: int, user: UsersUser = Depends(_get_current_user)) -> Dict[str, str]:
    try:
        _users_organizations.delete_organization(organization_id, user.id)
        return {"status": "ok"}
    except UserPlatformError as e:
        raise _map_users_error(e)

@app.get("/organizations/{organization_id}/usage", response_model=ResourceUsageResponse)
def organizations_usage(organization_id: int, user: UsersUser = Depends(_get_current_user)) -> ResourceUsageResponse:
    try:
        _users_authorization.get_role(user.id, organization_id)
        organization = _users_organizations.get_organization(organization_id)
        usage = _users_organizations.get_resource_usage(
            organization_id, portfolio_service=_portfolio_service, watchlist_service=_users_watchlist_bridge,
        )
        return ResourceUsageResponse(usage=usage, quotas=organization.quotas)
    except UserPlatformError as e:
        raise _map_users_error(e)

@app.get("/organizations/{organization_id}/members", response_model=List[MembershipResponse])
def organizations_list_members(organization_id: int, user: UsersUser = Depends(_get_current_user)) -> List[MembershipResponse]:
    try:
        _users_authorization.get_role(user.id, organization_id)
        return [MembershipResponse.model_validate(m) for m in _users_organizations.list_members(organization_id)]
    except UserPlatformError as e:
        raise _map_users_error(e)

@app.patch("/organizations/{organization_id}/members/{target_user_id}/role", response_model=MembershipResponse)
def organizations_change_member_role(
    organization_id: int, target_user_id: int, body: ChangeRoleRequest, user: UsersUser = Depends(_get_current_user),
) -> MembershipResponse:
    try:
        return MembershipResponse.model_validate(
            _users_organizations.change_member_role(organization_id, user.id, target_user_id, body.role)
        )
    except UserPlatformError as e:
        raise _map_users_error(e)

@app.delete("/organizations/{organization_id}/members/{target_user_id}")
def organizations_remove_member(
    organization_id: int, target_user_id: int, user: UsersUser = Depends(_get_current_user),
) -> Dict[str, str]:
    try:
        _users_organizations.remove_member(organization_id, user.id, target_user_id)
        return {"status": "ok"}
    except UserPlatformError as e:
        raise _map_users_error(e)

# ── Invitations ────────────────────────────────────────────────────────────────

@app.post("/organizations/{organization_id}/invitations", response_model=InvitationCreatedResponse)
def organizations_invite_member(
    organization_id: int, body: InviteMemberRequest, user: UsersUser = Depends(_get_current_user),
) -> InvitationCreatedResponse:
    try:
        invitation, token = _users_organizations.invite_member(organization_id, user.id, body.email, body.role, body.team_id)
        return InvitationCreatedResponse(invitation=InvitationResponse.model_validate(invitation), token=token)
    except UserPlatformError as e:
        raise _map_users_error(e)

@app.get("/organizations/{organization_id}/invitations", response_model=List[InvitationResponse])
def organizations_list_invitations(
    organization_id: int, user: UsersUser = Depends(_get_current_user),
) -> List[InvitationResponse]:
    try:
        return [
            InvitationResponse.model_validate(inv)
            for inv in _users_organizations.list_invitations(organization_id, user.id)
        ]
    except UserPlatformError as e:
        raise _map_users_error(e)

@app.delete("/organizations/{organization_id}/invitations/{invitation_id}")
def organizations_revoke_invitation(
    organization_id: int, invitation_id: int, user: UsersUser = Depends(_get_current_user),
) -> Dict[str, str]:
    try:
        _users_organizations.revoke_invitation(organization_id, user.id, invitation_id)
        return {"status": "ok"}
    except UserPlatformError as e:
        raise _map_users_error(e)

@app.post("/organizations/invitations/accept", response_model=MembershipResponse)
def organizations_accept_invitation(
    body: AcceptInvitationRequest, user: UsersUser = Depends(_get_current_user),
) -> MembershipResponse:
    try:
        return MembershipResponse.model_validate(_users_organizations.accept_invitation(body.token, user.id))
    except UserPlatformError as e:
        raise _map_users_error(e)

# ── Teams ──────────────────────────────────────────────────────────────────────

@app.post("/organizations/{organization_id}/teams", response_model=TeamResponse)
def organizations_create_team(
    organization_id: int, body: CreateTeamRequest, user: UsersUser = Depends(_get_current_user),
) -> TeamResponse:
    try:
        return TeamResponse.model_validate(_users_teams.create_team(organization_id, user.id, body.name))
    except UserPlatformError as e:
        raise _map_users_error(e)

@app.get("/organizations/{organization_id}/teams", response_model=List[TeamResponse])
def organizations_list_teams(organization_id: int, user: UsersUser = Depends(_get_current_user)) -> List[TeamResponse]:
    try:
        _users_authorization.get_role(user.id, organization_id)
        return [TeamResponse.model_validate(team) for team in _users_teams.list_teams(organization_id)]
    except UserPlatformError as e:
        raise _map_users_error(e)

@app.delete("/organizations/{organization_id}/teams/{team_id}")
def organizations_delete_team(
    organization_id: int, team_id: int, user: UsersUser = Depends(_get_current_user),
) -> Dict[str, str]:
    try:
        _users_teams.delete_team(organization_id, user.id, team_id)
        return {"status": "ok"}
    except UserPlatformError as e:
        raise _map_users_error(e)

@app.post("/organizations/{organization_id}/teams/{team_id}/members", response_model=TeamMembershipResponse)
def organizations_add_team_member(
    organization_id: int, team_id: int, body: AddTeamMemberRequest, user: UsersUser = Depends(_get_current_user),
) -> TeamMembershipResponse:
    try:
        return TeamMembershipResponse.model_validate(
            _users_teams.add_member(organization_id, user.id, team_id, body.user_id)
        )
    except UserPlatformError as e:
        raise _map_users_error(e)

@app.delete("/organizations/{organization_id}/teams/{team_id}/members/{target_user_id}")
def organizations_remove_team_member(
    organization_id: int, team_id: int, target_user_id: int, user: UsersUser = Depends(_get_current_user),
) -> Dict[str, str]:
    try:
        _users_teams.remove_member(organization_id, user.id, team_id, target_user_id)
        return {"status": "ok"}
    except UserPlatformError as e:
        raise _map_users_error(e)

@app.get("/organizations/{organization_id}/teams/{team_id}/members", response_model=List[TeamMembershipResponse])
def organizations_list_team_members(
    organization_id: int, team_id: int, user: UsersUser = Depends(_get_current_user),
) -> List[TeamMembershipResponse]:
    try:
        _users_authorization.get_role(user.id, organization_id)
        return [TeamMembershipResponse.model_validate(m) for m in _users_teams.list_members(team_id)]
    except UserPlatformError as e:
        raise _map_users_error(e)

# ── Audit log ────────────────────────────────────────────────────────────────

@app.get("/organizations/{organization_id}/audit-log", response_model=List[AuditLogEntryResponse])
def organizations_audit_log(organization_id: int, user: UsersUser = Depends(_get_current_user)) -> List[AuditLogEntryResponse]:
    try:
        _users_authorization.check_permission(user.id, organization_id, UsersPermission.MANAGE_MEMBERS)
        return [AuditLogEntryResponse.model_validate(e) for e in _users_audit.list_for_organization(organization_id)]
    except UserPlatformError as e:
        raise _map_users_error(e)

# ─────────────────────────────────────────────────────────────────────────────
# PAPER TRADING & TRADE JOURNAL PLATFORM ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

# ── Accounts ─────────────────────────────────────────────────────────────────

@app.post("/paper-trading/accounts", response_model=AccountResponse)
async def paper_trading_create_account(
    body: CreateAccountRequest, user: UsersUser = Depends(_get_current_user),
) -> AccountResponse:
    _require_paper_trading_service()
    try:
        account = await _run_in_executor(
            _paper_trading_service.ensure_account, user.id, user.email, body.name, body.starting_balance,
        )
        return AccountResponse.model_validate(account)
    except PaperTradingError as e:
        raise _map_paper_trading_error(e)

@app.get("/paper-trading/accounts", response_model=List[AccountResponse])
async def paper_trading_list_accounts(user: UsersUser = Depends(_get_current_user)) -> List[AccountResponse]:
    _require_paper_trading_service()
    accounts = await _run_in_executor(_paper_trading_service.list_accounts, user.id)
    return [AccountResponse.model_validate(account) for account in accounts]

@app.get("/paper-trading/accounts/{account_id}", response_model=AccountResponse)
async def paper_trading_get_account(account_id: int, user: UsersUser = Depends(_get_current_user)) -> AccountResponse:
    _require_paper_trading_service()
    try:
        account = await _run_in_executor(_get_authorized_paper_account, account_id, user)
        return AccountResponse.model_validate(account)
    except PaperTradingError as e:
        raise _map_paper_trading_error(e)

# ── Orders ───────────────────────────────────────────────────────────────────

@app.post("/paper-trading/accounts/{account_id}/orders", response_model=OrderResponse)
async def paper_trading_place_order(
    account_id: int, body: PlaceOrderRequest, user: UsersUser = Depends(_get_current_user),
) -> OrderResponse:
    _require_paper_trading_service()
    try:
        await _run_in_executor(_get_authorized_paper_account, account_id, user)
        order = await _run_in_executor(
            _paper_trading_service.place_order, account_id, user.email, body.symbol, body.side, body.order_type,
            body.quantity, body.limit_price, body.stop_price, body.notes,
        )
        return OrderResponse.model_validate(order)
    except PaperTradingError as e:
        raise _map_paper_trading_error(e)
    except (InsufficientCashError, InsufficientPositionError, InsufficientPriceDataError, InvalidTransactionError) as e:
        raise _map_paper_trading_error(e)

@app.get("/paper-trading/accounts/{account_id}/orders", response_model=List[OrderResponse])
async def paper_trading_list_orders(
    account_id: int, status: Optional[PaperOrderStatus] = None, user: UsersUser = Depends(_get_current_user),
) -> List[OrderResponse]:
    _require_paper_trading_service()
    try:
        await _run_in_executor(_get_authorized_paper_account, account_id, user)
        orders = await _run_in_executor(_paper_trading_service.list_orders, account_id, status)
        return [OrderResponse.model_validate(order) for order in orders]
    except PaperTradingError as e:
        raise _map_paper_trading_error(e)

@app.get("/paper-trading/orders/{order_id}", response_model=OrderResponse)
async def paper_trading_get_order(order_id: int, user: UsersUser = Depends(_get_current_user)) -> OrderResponse:
    _require_paper_trading_service()
    try:
        order = await _run_in_executor(_get_authorized_paper_order, order_id, user)
        return OrderResponse.model_validate(order)
    except PaperTradingError as e:
        raise _map_paper_trading_error(e)

@app.patch("/paper-trading/orders/{order_id}", response_model=OrderResponse)
async def paper_trading_modify_order(
    order_id: int, body: ModifyOrderRequest, user: UsersUser = Depends(_get_current_user),
) -> OrderResponse:
    _require_paper_trading_service()
    try:
        await _run_in_executor(_get_authorized_paper_order, order_id, user)
        order = await _run_in_executor(
            _paper_trading_service.modify_order, order_id, body.quantity, body.limit_price, body.stop_price,
        )
        return OrderResponse.model_validate(order)
    except PaperTradingError as e:
        raise _map_paper_trading_error(e)

@app.delete("/paper-trading/orders/{order_id}", response_model=OrderResponse)
async def paper_trading_cancel_order(order_id: int, user: UsersUser = Depends(_get_current_user)) -> OrderResponse:
    _require_paper_trading_service()
    try:
        await _run_in_executor(_get_authorized_paper_order, order_id, user)
        order = await _run_in_executor(_paper_trading_service.cancel_order, order_id)
        return OrderResponse.model_validate(order)
    except PaperTradingError as e:
        raise _map_paper_trading_error(e)

# ── Positions ──────────────────────────────────────────────────────────────────

@app.get("/paper-trading/accounts/{account_id}/positions", response_model=List[PositionAnalytics])
async def paper_trading_positions(account_id: int, user: UsersUser = Depends(_get_current_user)) -> List[PositionAnalytics]:
    _require_paper_trading_service()
    try:
        await _run_in_executor(_get_authorized_paper_account, account_id, user)
        return await _run_in_executor(_paper_trading_service.get_positions, account_id)
    except PaperTradingError as e:
        raise _map_paper_trading_error(e)

@app.get("/paper-trading/accounts/{account_id}/cash")
async def paper_trading_cash_balance(account_id: int, user: UsersUser = Depends(_get_current_user)) -> Dict[str, float]:
    _require_paper_trading_service()
    try:
        await _run_in_executor(_get_authorized_paper_account, account_id, user)
        cash = await _run_in_executor(_paper_trading_service.get_cash_balance, account_id)
        return {"cash_balance": cash}
    except PaperTradingError as e:
        raise _map_paper_trading_error(e)

@app.get("/paper-trading/accounts/{account_id}/total-value")
async def paper_trading_total_value(account_id: int, user: UsersUser = Depends(_get_current_user)) -> Dict[str, float]:
    _require_paper_trading_service()
    try:
        await _run_in_executor(_get_authorized_paper_account, account_id, user)
        total_value = await _run_in_executor(_paper_trading_service.get_total_value, account_id)
        return {"total_value": total_value}
    except PaperTradingError as e:
        raise _map_paper_trading_error(e)

# ── Trade journal ──────────────────────────────────────────────────────────────

@app.get("/paper-trading/orders/{order_id}/journal", response_model=JournalEntryResponse)
async def paper_trading_journal_for_order(order_id: int, user: UsersUser = Depends(_get_current_user)) -> JournalEntryResponse:
    _require_paper_trading_service()
    try:
        await _run_in_executor(_get_authorized_paper_order, order_id, user)
        entry = await _run_in_executor(_paper_trading_service.get_journal_entry_by_order, order_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"no journal entry recorded for order {order_id}")
        return JournalEntryResponse.model_validate(entry)
    except PaperTradingError as e:
        raise _map_paper_trading_error(e)

@app.get("/paper-trading/accounts/{account_id}/journal", response_model=List[JournalEntryResponse])
async def paper_trading_list_journal_entries(
    account_id: int, user: UsersUser = Depends(_get_current_user),
) -> List[JournalEntryResponse]:
    _require_paper_trading_service()
    try:
        await _run_in_executor(_get_authorized_paper_account, account_id, user)
        entries = await _run_in_executor(_paper_trading_service.list_journal_entries, account_id)
        return [JournalEntryResponse.model_validate(entry) for entry in entries]
    except PaperTradingError as e:
        raise _map_paper_trading_error(e)

def _get_authorized_journal_entry(entry_id: int, user: UsersUser):
    entry = _paper_trading_service.get_journal_entry(entry_id)
    _get_authorized_paper_account(entry.account_id, user)
    return entry

@app.patch("/paper-trading/journal/{entry_id}/notes", response_model=JournalEntryResponse)
async def paper_trading_update_journal_notes(
    entry_id: int, body: UpdateJournalNotesRequest, user: UsersUser = Depends(_get_current_user),
) -> JournalEntryResponse:
    _require_paper_trading_service()
    try:
        await _run_in_executor(_get_authorized_journal_entry, entry_id, user)
        entry = await _run_in_executor(_paper_trading_service.update_journal_notes, entry_id, body.notes)
        return JournalEntryResponse.model_validate(entry)
    except PaperTradingError as e:
        raise _map_paper_trading_error(e)

@app.post("/paper-trading/journal/{entry_id}/tags", response_model=JournalEntryResponse)
async def paper_trading_add_journal_tags(
    entry_id: int, body: AddJournalTagsRequest, user: UsersUser = Depends(_get_current_user),
) -> JournalEntryResponse:
    _require_paper_trading_service()
    try:
        await _run_in_executor(_get_authorized_journal_entry, entry_id, user)
        entry = await _run_in_executor(_paper_trading_service.add_journal_tags, entry_id, body.tags)
        return JournalEntryResponse.model_validate(entry)
    except PaperTradingError as e:
        raise _map_paper_trading_error(e)

@app.post("/paper-trading/journal/{entry_id}/screenshots", response_model=ScreenshotResponse)
async def paper_trading_add_journal_screenshot(
    entry_id: int, body: AddScreenshotRequest, user: UsersUser = Depends(_get_current_user),
) -> ScreenshotResponse:
    _require_paper_trading_service()
    try:
        await _run_in_executor(_get_authorized_journal_entry, entry_id, user)
        screenshot = await _run_in_executor(
            _paper_trading_service.add_journal_screenshot, entry_id, body.url, body.caption,
        )
        return ScreenshotResponse.model_validate(screenshot)
    except PaperTradingError as e:
        raise _map_paper_trading_error(e)

# ── Analytics / reports ────────────────────────────────────────────────────────

@app.get("/paper-trading/accounts/{account_id}/analytics", response_model=AnalyticsSummary)
async def paper_trading_analytics(
    account_id: int, symbol: Optional[str] = None, user: UsersUser = Depends(_get_current_user),
) -> AnalyticsSummary:
    _require_paper_trading_service()
    try:
        await _run_in_executor(_get_authorized_paper_account, account_id, user)
        return await _run_in_executor(_paper_trading_service.get_analytics_summary, account_id, symbol)
    except PaperTradingError as e:
        raise _map_paper_trading_error(e)

@app.get("/paper-trading/accounts/{account_id}/trades", response_model=List[ClosedTrade])
async def paper_trading_closed_trades(
    account_id: int, symbol: Optional[str] = None, user: UsersUser = Depends(_get_current_user),
) -> List[ClosedTrade]:
    _require_paper_trading_service()
    try:
        await _run_in_executor(_get_authorized_paper_account, account_id, user)
        return await _run_in_executor(_paper_trading_service.get_closed_trades, account_id, symbol)
    except PaperTradingError as e:
        raise _map_paper_trading_error(e)

@app.get("/paper-trading/accounts/{account_id}/equity-curve", response_model=List[EquityPoint])
async def paper_trading_equity_curve(account_id: int, user: UsersUser = Depends(_get_current_user)) -> List[EquityPoint]:
    _require_paper_trading_service()
    try:
        await _run_in_executor(_get_authorized_paper_account, account_id, user)
        return await _run_in_executor(_paper_trading_service.get_equity_curve, account_id)
    except PaperTradingError as e:
        raise _map_paper_trading_error(e)

@app.get("/paper-trading/accounts/{account_id}/monthly-performance", response_model=List[MonthlyPerformance])
async def paper_trading_monthly_performance(
    account_id: int, user: UsersUser = Depends(_get_current_user),
) -> List[MonthlyPerformance]:
    _require_paper_trading_service()
    try:
        await _run_in_executor(_get_authorized_paper_account, account_id, user)
        return await _run_in_executor(_paper_trading_service.get_monthly_performance, account_id)
    except PaperTradingError as e:
        raise _map_paper_trading_error(e)

@app.get("/paper-trading/accounts/{account_id}/reports/{period}", response_model=TradeReport)
async def paper_trading_report(
    account_id: int, period: ReportPeriod, user: UsersUser = Depends(_get_current_user),
) -> TradeReport:
    _require_paper_trading_service()
    try:
        await _run_in_executor(_get_authorized_paper_account, account_id, user)
        return await _run_in_executor(_paper_trading_service.generate_report, account_id, period, None)
    except PaperTradingError as e:
        raise _map_paper_trading_error(e)

# ─────────────────────────────────────────────────────────────────────────────
# ANALYTICS & DASHBOARD PLATFORM ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/dashboard/overview", response_model=OverviewMetrics)
async def dashboard_overview(user: UsersUser = Depends(_get_current_user)) -> OverviewMetrics:
    _require_dashboard_service()
    try:
        return await _run_in_executor(_dashboard_service.get_overview)
    except DashboardError as e:
        raise _map_dashboard_error(e)

@app.get("/dashboard/engines", response_model=EngineDashboardView)
async def dashboard_engines(
    symbol: Optional[str] = None, regime_symbols: Optional[List[str]] = Query(default=None),
    user: UsersUser = Depends(_get_current_user),
) -> EngineDashboardView:
    _require_dashboard_service()
    try:
        return await _run_in_executor(_dashboard_service.get_engine_dashboard, symbol, regime_symbols)
    except DashboardError as e:
        raise _map_dashboard_error(e)

@app.get("/dashboard/ml", response_model=MLDashboardView)
async def dashboard_ml(
    model_ids: Optional[List[str]] = Query(default=None), user: UsersUser = Depends(_get_current_user),
) -> MLDashboardView:
    _require_dashboard_service()
    try:
        return await _run_in_executor(_dashboard_service.get_model_dashboard, model_ids)
    except DashboardError as e:
        raise _map_dashboard_error(e)

@app.get("/dashboard/portfolios/{portfolio_id}", response_model=PortfolioDashboardExtended)
async def dashboard_portfolio(portfolio_id: int, user: UsersUser = Depends(_get_current_user)) -> PortfolioDashboardExtended:
    _require_dashboard_service()
    _require_portfolio_service()
    try:
        await _run_in_executor(_get_owned_portfolio_for_dashboard, portfolio_id, user)
        return await _run_in_executor(_dashboard_service.get_portfolio_dashboard, portfolio_id)
    except PortfolioError as e:
        raise _map_dashboard_error(e)
    except DashboardError as e:
        raise _map_dashboard_error(e)

@app.get("/dashboard/watchlists", response_model=WatchlistDashboardView)
async def dashboard_watchlists(user: UsersUser = Depends(_get_current_user)) -> WatchlistDashboardView:
    _require_dashboard_service()
    try:
        return await _run_in_executor(_dashboard_service.get_watchlist_dashboard, user.email)
    except DashboardError as e:
        raise _map_dashboard_error(e)

@app.get("/dashboard/paper-trading/{account_id}", response_model=PaperTradingDashboardView)
async def dashboard_paper_trading(account_id: int, user: UsersUser = Depends(_get_current_user)) -> PaperTradingDashboardView:
    _require_dashboard_service()
    _require_paper_trading_service()
    try:
        await _run_in_executor(_get_authorized_paper_account, account_id, user)
        return await _run_in_executor(_dashboard_service.get_paper_trading_dashboard, account_id)
    except DashboardError as e:
        raise _map_dashboard_error(e)
    except PaperTradingError as e:
        raise _map_paper_trading_error(e)

@app.get("/dashboard/learning", response_model=LearningDashboardView)
async def dashboard_learning(
    window: RollingWindow = RollingWindow.THIRTY_DAY, user: UsersUser = Depends(_get_current_user),
) -> LearningDashboardView:
    _require_dashboard_service()
    try:
        return await _run_in_executor(_dashboard_service.get_learning_dashboard, window)
    except DashboardError as e:
        raise _map_dashboard_error(e)

@app.get("/dashboard/alerts", response_model=AlertDashboardView)
async def dashboard_alerts(user: UsersUser = Depends(_get_current_user)) -> AlertDashboardView:
    _require_dashboard_service()
    try:
        return await _run_in_executor(_dashboard_service.get_alert_dashboard, user.email)
    except DashboardError as e:
        raise _map_dashboard_error(e)

@app.get("/dashboard/market", response_model=MarketDashboardView)
async def dashboard_market(
    symbols: Optional[List[str]] = Query(default=None), market: str = "US",
    user: UsersUser = Depends(_get_current_user),
) -> MarketDashboardView:
    _require_dashboard_service()
    try:
        return await _run_in_executor(_dashboard_service.get_market_dashboard, symbols, market)
    except DashboardError as e:
        raise _map_dashboard_error(e)

@app.get("/dashboard/reports/{period}", response_model=None)
async def dashboard_report(
    period: DashboardReportPeriod, format: ReportFormat = ReportFormat.JSON,
    user: UsersUser = Depends(_get_current_user),
) -> Union[DashboardReport, PlainTextResponse]:
    _require_dashboard_service()
    try:
        report = await _run_in_executor(_dashboard_service.generate_report, period, None)
        if format == ReportFormat.CSV:
            return PlainTextResponse(content=_dashboard_service.report_service.to_csv(report), media_type="text/csv")
        return report
    except DashboardError as e:
        raise _map_dashboard_error(e)
